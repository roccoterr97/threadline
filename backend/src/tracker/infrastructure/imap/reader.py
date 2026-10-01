"""The mail collector's reader for any standard mailbox, over IMAP.

It reads the inbox and the Sent folder in the collector's two passes: headers
of every message in the window first, bodies only for the threads the
obvious-noise rules kept. Messages in the Sent folder are the owner's own, so
their direction is right even when they went from an address the owner never
listed.

Identifiers are opaque: Gmail's own message and thread numbers where the server
offers them, otherwise a hash of the Message-ID and of the thread's first
message. No subject or address ever ends up in an identifier, because a noise
thread keeps nothing but its identifier.
"""

from __future__ import annotations

import asyncio
import hashlib
import threading
from collections import defaultdict
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import batched
from types import TracebackType
from typing import Final, Self

from tracker.domain.mail import MailMessage
from tracker.infrastructure.imap.parser import (
    FetchRecord,
    HeaderFacts,
    extract_body,
    parse_headers,
)
from tracker.infrastructure.imap.session import Folder, ImapSession, quote
from tracker.infrastructure.imap.threads import MESSAGE_KEY, ThreadFacts, thread_keys
from tracker.shared.constants.mailbox import (
    GMAIL_EXTENSION_CAPABILITY,
    IMAP_BODY_BATCH_SIZE,
    IMAP_FETCH_BATCH_SIZE,
    IMAP_INBOX,
    IMAP_MAX_FETCH_BYTES,
    IMAP_MAX_MESSAGES_PER_FOLDER,
    IMAP_METADATA_HEADERS,
    IMAP_MONTHS,
    IMAP_SENT_ATTRIBUTE,
    IMAP_SENT_FOLDER_NAMES,
    IMAP_SINCE_SLACK_DAYS,
    MAX_BODY_CHARACTERS,
)
from tracker.shared.logging import get_logger

#: Characters of a hash kept in an identifier: 128 bits, far beyond any collision.
_HASH_CHARACTERS: Final[int] = 32

_GMAIL_PREFIX: Final[str] = "gmail-"
_IMAP_PREFIX: Final[str] = "imap-"
_NO_SELECT: Final[str] = "\\noselect"

_METADATA_ITEMS: Final[str] = (
    f"(UID INTERNALDATE BODY.PEEK[HEADER.FIELDS ({' '.join(IMAP_METADATA_HEADERS)})])"
)
_GMAIL_METADATA_ITEMS: Final[str] = (
    "(UID INTERNALDATE X-GM-THRID X-GM-MSGID "
    f"BODY.PEEK[HEADER.FIELDS ({' '.join(IMAP_METADATA_HEADERS)})])"
)
_BODY_ITEMS: Final[str] = f"(UID BODY.PEEK[]<0.{IMAP_MAX_FETCH_BYTES}>)"

_log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class MailboxSurvey:
    """What a quick look at the mailbox found, for the set-up and the doctor.

    Attributes:
        inbox_messages: Messages the inbox received inside the window.
        sent_folder: The Sent folder's name, or ``None`` when none was found.
    """

    inbox_messages: int
    sent_folder: str | None


@dataclass(frozen=True, slots=True)
class _Seen:
    """One message found in a folder, before it is placed in a thread."""

    folder: str
    in_sent: bool
    record: FetchRecord
    headers: HeaderFacts


@dataclass(frozen=True, slots=True)
class _Location:
    """Where a message can be fetched again."""

    folder: str
    uid: int


class ImapMailbox:
    """Reads one standard mailbox, read-only, for the mail collector."""

    def __init__(self, session: ImapSession) -> None:
        """Bind the reader to a session that is not open yet.

        Args:
            session: The read-only IMAP session.
        """
        self._session = session
        self._gmail = False
        self._folders: tuple[tuple[str, bool], ...] = ()
        self._sent_folder: str | None = None
        self._locations: dict[str, _Location] = {}
        self._members: dict[str, dict[str, MailMessage]] = {}
        self._thread_search: dict[str, tuple[str, ...]] = {}
        # An IMAP connection carries one command at a time and remembers which
        # folder is open, so callers asking for many things at once take turns.
        self._turn = asyncio.Lock()
        # A cancelled wait cannot stop the thread it started; this keeps the
        # next command, or the sign-out, off the connection until it is done.
        self._line = threading.Lock()

    async def __aenter__(self) -> Self:
        """Sign in and find the inbox and the Sent folder."""
        await self._alone(self._open)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Sign out."""
        await self._alone(self._session.close)

    async def list_messages_since(self, since: datetime) -> list[MailMessage]:
        """Read the headers of every message the inbox and Sent folder received since a moment.

        Args:
            since: Start of the window, in UTC.

        Returns:
            One entry per message, without bodies; only the newest
            :data:`IMAP_MAX_MESSAGES_PER_FOLDER` of a folder when it holds more.

        Raises:
            SourceUnavailableError: If the server could not be reached.
        """
        return await self._alone(lambda: self._list_since(since))

    async def list_thread(self, conversation_id: str) -> list[MailMessage]:
        """Read the headers of every message in one thread, however old.

        Args:
            conversation_id: An identifier this reader returned earlier in the run.

        Returns:
            The thread's messages, without bodies; empty for an unknown thread.
        """
        return await self._alone(lambda: self._list_thread(conversation_id))

    async def fetch_body(self, message_id: str) -> str:
        """Read one message's body as plain text, attachments left unread.

        Args:
            message_id: An identifier this reader returned earlier in the run.

        Returns:
            The body text, empty when the message cannot be found again.
        """
        [body] = await self.fetch_bodies([message_id])
        return body

    async def fetch_bodies(self, message_ids: Sequence[str]) -> list[str]:
        """Read several messages' bodies as plain text, with one command per folder.

        Args:
            message_ids: Identifiers this reader returned earlier in the run.

        Returns:
            One body per identifier, in the order asked; empty for a message
            that cannot be found again.
        """
        return await self._alone(lambda: self._bodies(message_ids))

    async def survey(self, since: datetime) -> MailboxSurvey:
        """Count the inbox's messages in a window and name the Sent folder.

        Args:
            since: Start of the window, in UTC.

        Returns:
            What was found.
        """
        return await self._alone(lambda: self._survey(since))

    async def _alone[ResultT](self, work: Callable[[], ResultT]) -> ResultT:
        """Run one piece of work on the connection, off the event loop, never two at once.

        Args:
            work: What to do on the connection.

        Returns:
            Whatever the work returned.
        """
        async with self._turn:
            return await asyncio.to_thread(self._on_the_line, work)

    def _on_the_line[ResultT](self, work: Callable[[], ResultT]) -> ResultT:
        """Do the work once the connection is free."""
        with self._line:
            return work()

    def _open(self) -> None:
        """Sign in, then decide which folders are read."""
        self._session.open()
        self._gmail = GMAIL_EXTENSION_CAPABILITY in self._session.capabilities()
        self._sent_folder = find_sent_folder(self._session.folders())
        folders = [(IMAP_INBOX, False)]
        if self._sent_folder is not None:
            folders.append((self._sent_folder, True))
        self._folders = tuple(folders)
        _log.info("imap_opened", gmail=self._gmail, sent_folder_found=self._sent_folder is not None)

    def _survey(self, since: datetime) -> MailboxSurvey:
        """Count the inbox's messages in the window."""
        self._session.examine(IMAP_INBOX)
        count = len(self._session.search("SINCE", imap_date(since)))
        return MailboxSurvey(inbox_messages=count, sent_folder=self._sent_folder)

    def _list_since(self, since: datetime) -> list[MailMessage]:
        """Read the window's headers from every folder."""
        seen: list[_Seen] = []
        for folder, in_sent in self._folders:
            for found in self._read_folder(folder, in_sent, _since_search(since)):
                arrived = found.record.internal_date
                if arrived is None or arrived >= since:
                    seen.append(found)
        return self._place(seen)

    def _list_thread(self, conversation_id: str) -> list[MailMessage]:
        """Search every folder for the thread, and add what the window already saw."""
        members = self._members.setdefault(conversation_id, {})
        criteria = self._thread_search.get(conversation_id)
        if criteria is not None:
            seen = [
                found
                for folder, in_sent in self._folders
                for found in self._read_folder(folder, in_sent, criteria)
            ]
            for message in self._place(seen):
                if message.conversation_id == conversation_id:
                    members.setdefault(message.message_id, message)
        return list(members.values())

    def _bodies(self, message_ids: Sequence[str]) -> list[str]:
        """Fetch and decode several messages' bodies, folder by folder."""
        locations = [self._locations.get(message_id) for message_id in message_ids]
        uids_by_folder: dict[str, set[int]] = defaultdict(set)
        for location in locations:
            if location is not None:
                uids_by_folder[location.folder].add(location.uid)
        # The folder that is already open is read first: it costs no EXAMINE.
        open_folder = self._session.open_folder
        found: dict[_Location, str] = {}
        for folder in sorted(uids_by_folder, key=lambda name: name != open_folder):
            found.update(self._folder_bodies(folder, sorted(uids_by_folder[folder])))
        return [found.get(location, "") if location is not None else "" for location in locations]

    def _folder_bodies(self, folder: str, uids: Sequence[int]) -> dict[_Location, str]:
        """Fetch and decode the bodies of some messages of one folder."""
        self._session.examine(folder)
        # A server answers in the order it likes and may add a line about a
        # message's flags; only an answer carrying a message, matched by its
        # UID, is that message's body.
        return {
            _Location(folder, record.uid): extract_body(record.literal, MAX_BODY_CHARACTERS)
            for record in self._fetch(uids, _BODY_ITEMS, IMAP_BODY_BATCH_SIZE)
            if record.literal
        }

    def _read_folder(self, folder: str, in_sent: bool, criteria: tuple[str, ...]) -> list[_Seen]:
        """Search one folder and fetch the headers of what matched."""
        self._session.examine(folder)
        uids = _newest(self._session.search(*criteria), in_sent=in_sent)
        items = _GMAIL_METADATA_ITEMS if self._gmail else _METADATA_ITEMS
        return [
            _Seen(folder, in_sent, record, parse_headers(record.literal))
            for record in self._fetch(uids, items, IMAP_FETCH_BATCH_SIZE)
        ]

    def _fetch(self, uids: Sequence[int], items: str, per_command: int) -> Iterator[FetchRecord]:
        """Fetch items for messages of the open folder, a bounded number per command."""
        for batch in batched(uids, per_command):
            yield from self._session.fetch(batch, items)

    def _place(self, seen: list[_Seen]) -> list[MailMessage]:
        """Give each message its identifiers and thread, and remember where it is."""
        unique = _deduplicated(seen)
        keys = thread_keys([_thread_facts(found) for found in unique])
        placed: list[MailMessage] = []
        for found, key in zip(unique, keys, strict=True):
            message = self._message(found, key)
            if message is None:
                continue
            self._locations.setdefault(
                message.message_id, _Location(found.folder, found.record.uid)
            )
            self._members.setdefault(message.conversation_id, {}).setdefault(
                message.message_id, message
            )
            placed.append(message)
        return placed

    def _message(self, found: _Seen, key: str) -> MailMessage | None:
        """Turn one message's headers into the collector's record."""
        headers = found.headers
        sent_at = headers.sent_at or found.record.internal_date
        if sent_at is None:
            return None
        address, name = headers.sender
        return MailMessage(
            message_id=_message_id(found),
            conversation_id=self._conversation_id(found, key),
            subject=headers.subject,
            sent_at=sent_at,
            sender_address=address,
            sender_name=name,
            recipients=headers.recipients,
            has_list_unsubscribe=headers.has_list_unsubscribe,
            reply_to=headers.reply_to,
            from_owner=found.in_sent,
        )

    def _conversation_id(self, found: _Seen, key: str) -> str:
        """The thread's identifier, remembering how to search for the whole thread."""
        thread = found.record.gmail_thread_id
        if self._gmail and thread:
            identifier = _GMAIL_PREFIX + thread
            self._thread_search.setdefault(identifier, ("X-GM-THRID", thread))
            return identifier
        identifier = _IMAP_PREFIX + _digest(key)
        if key.startswith(MESSAGE_KEY):
            root = quote(key.removeprefix(MESSAGE_KEY))
            self._thread_search.setdefault(
                identifier,
                ("OR", "OR", "HEADER", "Message-ID", root, "HEADER", "References", root)
                + ("HEADER", "In-Reply-To", root),
            )
        return identifier


def _newest(uids: list[int], *, in_sent: bool) -> list[int]:
    """Keep only the newest messages a search found, when it found too many.

    UIDs grow as mail arrives, so the highest ones are the newest. Reading the
    newest few thousand beats giving up on the whole folder.

    Args:
        uids: The matching UIDs, in ascending order.
        in_sent: Whether they are from the Sent folder; only logged.

    Returns:
        At most :data:`IMAP_MAX_MESSAGES_PER_FOLDER` UIDs, the highest ones.
    """
    if len(uids) <= IMAP_MAX_MESSAGES_PER_FOLDER:
        return uids
    _log.warning(
        "imap_folder_capped",
        in_sent=in_sent,
        matched=len(uids),
        read=IMAP_MAX_MESSAGES_PER_FOLDER,
    )
    return uids[-IMAP_MAX_MESSAGES_PER_FOLDER:]


def find_sent_folder(folders: list[Folder]) -> str | None:
    """Find the folder the owner's sent mail is kept in.

    The server's own marker wins, because it names the folder in any language
    (Gmail: "[Gmail]/Sent Mail", "[Gmail]/Gesendet"…); the usual names are the
    fallback for servers that do not mark it.

    Args:
        folders: Every folder of the mailbox.

    Returns:
        The folder's name as the server spells it, or ``None`` when none fits.
    """
    selectable = [folder for folder in folders if _NO_SELECT not in folder.attributes]
    marked = next(
        (folder.name for folder in selectable if IMAP_SENT_ATTRIBUTE in folder.attributes), None
    )
    if marked is not None:
        return marked
    by_name = {folder.name.lower(): folder.name for folder in selectable}
    return next(
        (by_name[name.lower()] for name in IMAP_SENT_FOLDER_NAMES if name.lower() in by_name),
        None,
    )


def _since_search(since: datetime) -> tuple[str, str]:
    """The SEARCH keys for a window, a day wide of its start.

    The server compares dates in its own time zone, so the search starts a day
    earlier; the caller keeps only what arrived at or after ``since``.
    """
    return ("SINCE", imap_date(since - timedelta(days=IMAP_SINCE_SLACK_DAYS)))


def imap_date(moment: datetime) -> str:
    """Write a day the way IMAP searches expect it, whatever the machine's language.

    Args:
        moment: Any moment; its UTC day is used.

    Returns:
        A date such as ``29-Sep-2026``.
    """
    day = moment.astimezone(UTC)
    return f"{day.day}-{IMAP_MONTHS[day.month - 1]}-{day.year}"


def _deduplicated(seen: list[_Seen]) -> list[_Seen]:
    """Keep one copy of a message found in two folders, preferring the Sent one."""
    chosen: dict[str, _Seen] = {}
    for found in seen:
        identifier = _message_id(found)
        if identifier not in chosen or found.in_sent:
            chosen[identifier] = found
    return list(chosen.values())


def _message_id(found: _Seen) -> str:
    """An opaque identifier for a message, the same on every run."""
    gmail = found.record.gmail_message_id
    if gmail:
        return _GMAIL_PREFIX + gmail
    own = found.headers.message_id or _stand_in(found)
    return _IMAP_PREFIX + _digest(own)


def _thread_facts(found: _Seen) -> ThreadFacts:
    """What places a message in a thread."""
    headers = found.headers
    return ThreadFacts(
        message_id=headers.message_id,
        in_reply_to=headers.in_reply_to,
        references=headers.references,
        subject=headers.subject,
        stand_in=_stand_in(found),
    )


def _stand_in(found: _Seen) -> str:
    """A key for a message that has no Message-ID: its folder, number and arrival."""
    arrived = found.record.internal_date.isoformat() if found.record.internal_date else ""
    return f"{found.folder}\n{found.record.uid}\n{arrived}"


def _digest(value: str) -> str:
    """A short, stable hash of a value."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:_HASH_CHARACTERS]
