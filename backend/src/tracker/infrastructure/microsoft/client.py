"""Read-only mailbox reader on Microsoft Graph.

The reader works in two passes, so text Threadline will never keep is never
fetched in the first place:

1. **Metadata pass** — identifiers, dates, senders and the ``List-Unsubscribe``
   header for every message in the window. No bodies.
2. **Body pass** — bodies, as plain text, only for the threads the obvious-noise
   rules kept.

Sent Items is included: the owner's own replies give every thread its direction
and are the strongest evidence a conversation is real. Junk, Deleted Items,
Drafts and Outbox are skipped.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, Final, Self
from urllib.parse import quote

from tracker.domain.calendar import CalendarEvent, MeetingResponse
from tracker.domain.mail import MailMessage
from tracker.infrastructure.microsoft.graph_session import (
    VALUE,
    AccessTokenProvider,
    GraphSession,
    parse_timestamp,
)
from tracker.shared.concurrency import gather_all
from tracker.shared.constants.collection import (
    CALENDAR_FIELDS,
    GRAPH_CALENDAR_MESSAGE_TYPE,
    GRAPH_CALENDAR_RESCUE_FOLDER,
    GRAPH_EXCLUDED_FOLDERS,
    GRAPH_PAGE_SIZE,
    LIST_UNSUBSCRIBE_HEADER,
    MICROSOFT_GRAPH_URL,
    UTC_TIME_PREFERENCE,
)

#: Fields the metadata pass asks for. Deliberately no ``body``.
METADATA_FIELDS: Final[str] = (
    "id,conversationId,subject,receivedDateTime,sentDateTime,"
    "from,sender,replyTo,toRecipients,parentFolderId,internetMessageHeaders"
)

#: Fields the body pass asks for.
BODY_FIELDS: Final[str] = "id,body"

#: Asks Graph for plain text rather than HTML.
PLAIN_TEXT_PREFERENCE: Final[str] = 'outlook.body-content-type="text"'

#: Characters of a message identifier written into a URL path as they are.
#: ``=`` pads Graph's identifiers and is legal inside a path segment; everything
#: else that could change the address (``/``, ``?``, ``#``, ``%``…) is encoded.
_IDENTIFIER_SAFE_CHARACTERS: Final[str] = "="

#: Graph writes event times with seven decimals; ``YYYY-MM-DDTHH:MM:SS`` is enough.
_GRAPH_SECONDS_PRECISION: Final[int] = 19

#: What the owner runs to sign in to the mailbox again.
_REDO_COMMAND: Final[str] = "tracker microsoft login"


#: The owner's answer to an invitation, as Graph spells it; anything else is no answer.
_GRAPH_RESPONSES: Final[dict[str, MeetingResponse]] = {
    "accepted": MeetingResponse.ACCEPTED,
    "tentativelyAccepted": MeetingResponse.TENTATIVE,
    "declined": MeetingResponse.DECLINED,
    "organizer": MeetingResponse.ORGANIZER,
}


class GraphMailbox:
    """Reads the owner's mailbox over Microsoft Graph."""

    def __init__(self, tokens: AccessTokenProvider) -> None:
        """Bind the reader to a key supplier.

        Args:
            tokens: Supplies a valid access key before every call.
        """
        self._graph = GraphSession(tokens, what="mailbox", redo_command=_REDO_COMMAND)
        self._excluded_folder_ids: frozenset[str] | None = None
        self._rescue_folder_id: str | None = None

    async def __aenter__(self) -> Self:
        """Open the connection pool."""
        await self._graph.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the connection pool."""
        await self._graph.__aexit__(exc_type, exc_value, traceback)

    @property
    def window_capped(self) -> bool:
        """Always ``False``: a listing too long to finish fails instead of being cut short."""
        return False

    async def list_messages_since(self, since: datetime) -> list[MailMessage]:
        """Read the metadata of every message received since a moment.

        Args:
            since: Start of the window, in UTC.

        Returns:
            One entry per message outside the skipped folders, without bodies.
        """
        await self._excluded_folders()
        moment = _graph_moment(since)
        entries = await self._follow(
            f"{MICROSOFT_GRAPH_URL}/me/messages",
            {
                "$select": METADATA_FIELDS,
                "$filter": f"receivedDateTime ge {moment}",
                "$orderby": "receivedDateTime desc",
                "$top": GRAPH_PAGE_SIZE,
            },
        )
        return [message for message, folder_id in entries if self._readable(message, folder_id)]

    async def list_thread(self, conversation_id: str) -> list[MailMessage]:
        """Read the metadata of every message in one thread, however old.

        A status cannot be judged from half a conversation, so a thread the
        window touched is read whole.

        Args:
            conversation_id: Graph's identifier for the thread.

        Returns:
            The thread's messages, without bodies.
        """
        await self._excluded_folders()
        escaped = conversation_id.replace("'", "''")
        entries = await self._follow(
            f"{MICROSOFT_GRAPH_URL}/me/messages",
            {
                "$select": METADATA_FIELDS,
                "$filter": f"conversationId eq '{escaped}'",
                "$top": GRAPH_PAGE_SIZE,
            },
        )
        return [message for message, folder_id in entries if self._readable(message, folder_id)]

    async def list_events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        """Read the calendar between two moments, occurrences expanded.

        Args:
            start: Start of the range, in UTC.
            end: End of the range, in UTC.

        Returns:
            One entry per event or occurrence, without descriptions.

        Raises:
            SourceUnavailableError: If the listing never ends.
        """
        params: dict[str, Any] = {
            "startDateTime": _graph_moment(start),
            "endDateTime": _graph_moment(end),
            "$select": CALENDAR_FIELDS,
            "$top": GRAPH_PAGE_SIZE,
        }
        events: list[CalendarEvent] = []
        pages = self._graph.pages(
            f"{MICROSOFT_GRAPH_URL}/me/calendarView",
            params,
            headers={"Prefer": UTC_TIME_PREFERENCE},
        )
        async for payload in pages:
            events.extend(
                event
                for item in payload.get(VALUE) or []
                if isinstance(item, dict) and (event := _parse_event(item)) is not None
            )
        return events

    async def fetch_body(self, message_id: str) -> str:
        """Read one message's body as plain text.

        Args:
            message_id: Graph's identifier for the message.

        Returns:
            The body text, empty when the message has none.
        """
        payload = await self._graph.get(
            f"{MICROSOFT_GRAPH_URL}/me/messages/{_path_segment(message_id)}",
            {"$select": BODY_FIELDS},
            headers={"Prefer": PLAIN_TEXT_PREFERENCE},
        )
        body = payload.get("body")
        if not isinstance(body, dict):
            return ""
        return str(body.get("content", ""))

    async def fetch_bodies(self, message_ids: Sequence[str]) -> list[str]:
        """Read several messages' bodies as plain text, side by side.

        Args:
            message_ids: Graph's identifiers for the messages.

        Returns:
            One body per identifier, in the order asked.
        """
        return await gather_all(self.fetch_body(message_id) for message_id in message_ids)

    def _readable(self, message: MailMessage, folder_id: str) -> bool:
        """Whether a message is read at all.

        Everything outside the skipped folders is, and so is calendar mail that
        Outlook tidied into Deleted Items once the owner answered it.
        """
        if folder_id not in (self._excluded_folder_ids or frozenset()):
            return True
        return message.is_calendar_message and folder_id == self._rescue_folder_id

    async def _excluded_folders(self) -> frozenset[str]:
        """Resolve the identifiers of the folders that are never read.

        Returns:
            The identifiers, empty when the mailbox has none of those folders.
        """
        if self._excluded_folder_ids is not None:
            return self._excluded_folder_ids
        identifiers: set[str] = set()
        for name in GRAPH_EXCLUDED_FOLDERS:
            payload = await self._graph.get(
                f"{MICROSOFT_GRAPH_URL}/me/mailFolders/{name}",
                {"$select": "id"},
                allow_missing=True,
            )
            folder_id = payload.get("id")
            if isinstance(folder_id, str) and folder_id:
                identifiers.add(folder_id)
                if name == GRAPH_CALENDAR_RESCUE_FOLDER:
                    self._rescue_folder_id = folder_id
        self._excluded_folder_ids = frozenset(identifiers)
        return self._excluded_folder_ids

    async def _follow(
        self,
        url: str,
        params: dict[str, Any],
    ) -> list[tuple[MailMessage, str]]:
        """Read every page of a listing, following ``@odata.nextLink``.

        Args:
            url: The first page's address.
            params: Query parameters for the first page only; Graph repeats them
                inside each ``@odata.nextLink``.

        Returns:
            Each message with the identifier of the folder it sits in.

        Raises:
            SourceUnavailableError: If the listing never ends.
        """
        collected: list[tuple[MailMessage, str]] = []
        async for payload in self._graph.pages(url, params):
            collected.extend(_parse_page(payload))
        return collected


def _parse_page(payload: dict[str, Any]) -> list[tuple[MailMessage, str]]:
    """Turn one page of Graph messages into records.

    Args:
        payload: The decoded page.

    Returns:
        Each readable message with the identifier of its folder.
    """
    parsed: list[tuple[MailMessage, str]] = []
    for item in payload.get(VALUE) or []:
        if not isinstance(item, dict):
            continue
        message = _parse_message(item)
        if message is not None:
            parsed.append((message, str(item.get("parentFolderId", ""))))
    return parsed


def _parse_message(item: dict[str, Any]) -> MailMessage | None:
    """Turn one Graph message into a record.

    Args:
        item: One entry of a Graph page.

    Returns:
        The message, or ``None`` when it has no identifier or no readable date.
    """
    message_id = str(item.get("id", ""))
    sent_at = parse_timestamp(item.get("sentDateTime") or item.get("receivedDateTime"))
    if not message_id or sent_at is None:
        return None
    address, name = _mailbox_of(item.get("from") or item.get("sender"))
    return MailMessage(
        message_id=message_id,
        conversation_id=str(item.get("conversationId", "")) or message_id,
        subject=str(item.get("subject") or "").strip(),
        sent_at=sent_at,
        sender_address=address,
        sender_name=name,
        recipients=tuple(_mailbox_of(recipient) for recipient in item.get("toRecipients") or []),
        has_list_unsubscribe=_has_unsubscribe_header(item.get("internetMessageHeaders")),
        body=None,
        reply_to=tuple(_mailbox_of(entry) for entry in item.get("replyTo") or []),
        is_calendar_message=str(item.get("@odata.type", "")).startswith(
            GRAPH_CALENDAR_MESSAGE_TYPE
        ),
    )


def _parse_event(item: dict[str, Any]) -> CalendarEvent | None:
    """Turn one Graph calendar event into a record.

    Args:
        item: One entry of a ``calendarView`` page.

    Returns:
        The event, or ``None`` when it has no identifier or unreadable times.
    """
    event_id = str(item.get("id", ""))
    start = _event_time(item.get("start"))
    end = _event_time(item.get("end"))
    changed_at = parse_timestamp(item.get("lastModifiedDateTime") or item.get("createdDateTime"))
    if not event_id or start is None or end is None or changed_at is None:
        return None
    response = item.get("responseStatus")
    answer = str(response.get("response", "")) if isinstance(response, dict) else ""
    return CalendarEvent(
        event_id=event_id,
        ical_uid=str(item.get("iCalUId") or event_id),
        revision=changed_at.isoformat(),
        subject=str(item.get("subject") or "").strip(),
        start=start,
        end=end,
        organizer=_mailbox_of(item.get("organizer")),
        attendees=tuple(_mailbox_of(entry) for entry in item.get("attendees") or []),
        is_cancelled=bool(item.get("isCancelled")),
        is_organizer=bool(item.get("isOrganizer")),
        response=_GRAPH_RESPONSES.get(answer, MeetingResponse.NOT_ANSWERED),
        changed_at=changed_at,
    )


def _event_time(value: Any) -> datetime | None:  # noqa: ANN401 - raw Graph payload
    """Read a ``{"dateTime": …, "timeZone": "UTC"}`` object as a UTC moment."""
    if not isinstance(value, dict):
        return None
    raw = str(value.get("dateTime", ""))
    try:
        moment = datetime.fromisoformat(raw[:_GRAPH_SECONDS_PRECISION])
    except ValueError:
        return None
    return moment.replace(tzinfo=UTC)


def _path_segment(identifier: str) -> str:
    """Encode an identifier so it stays one segment of a URL path.

    The identifier comes from the mailbox, so it is never trusted to be free of
    characters that would point the request at another address.

    Args:
        identifier: The identifier as Graph returned it.

    Returns:
        The identifier, percent-encoded.
    """
    return quote(identifier, safe=_IDENTIFIER_SAFE_CHARACTERS)


def _graph_moment(moment: datetime) -> str:
    """Write a moment the way Graph filters and ranges expect it."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _mailbox_of(value: Any) -> tuple[str, str]:  # noqa: ANN401 - raw Graph payload
    """Read an address and a display name out of a Graph mailbox object.

    Args:
        value: A ``{"emailAddress": {"address": …, "name": …}}`` object.

    Returns:
        The lower-case address and the display name, both possibly empty.
    """
    if not isinstance(value, dict):
        return "", ""
    mailbox = value.get("emailAddress")
    if not isinstance(mailbox, dict):
        return "", ""
    return str(mailbox.get("address", "")).strip().lower(), str(mailbox.get("name", "")).strip()


def _has_unsubscribe_header(headers: Any) -> bool:  # noqa: ANN401 - raw Graph payload
    """Decide whether a message carried the bulk-sender header.

    Args:
        headers: The ``internetMessageHeaders`` collection, if Graph sent one.

    Returns:
        ``True`` when a ``List-Unsubscribe`` header is present.
    """
    if not isinstance(headers, Iterable) or isinstance(headers, str | bytes):
        return False
    wanted = LIST_UNSUBSCRIBE_HEADER.lower()
    return any(
        isinstance(header, dict) and str(header.get("name", "")).strip().lower() == wanted
        for header in headers
    )
