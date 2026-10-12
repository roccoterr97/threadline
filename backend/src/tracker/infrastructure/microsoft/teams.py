"""Read-only Teams chat reader on Microsoft Graph.

It reads the signed-in person's one-to-one and group chats with their members,
then each chat's messages newest first, stopping at the start of the window.
Only what people wrote is returned: system events, deleted messages and
messages from bots or apps are skipped, and HTML bodies become plain text.

``/chats/getAllMessages`` is never used: it needs application permissions and
is billed by Microsoft. Everything here needs the delegated ``Chat.Read`` only,
plus ``User.Read`` to learn who signed in.
"""

from __future__ import annotations

from contextlib import aclosing
from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Any, Final, Self
from urllib.parse import quote

import httpx

from tracker.infrastructure.imap.html_text import html_to_text
from tracker.infrastructure.microsoft.graph_session import (
    VALUE,
    AccessTokenProvider,
    GraphSession,
    parse_timestamp,
)
from tracker.shared.constants.collection import (
    MICROSOFT_GRAPH_URL,
    TEAMS_CHAT_PAGE_SIZE,
    TEAMS_CHAT_TYPES,
    TEAMS_MESSAGE_PAGE_SIZE,
    TEAMS_PERSON_MESSAGE_TYPE,
)

#: What the owner runs to sign in to Teams again.
_REDO_COMMAND: Final[str] = "uv run tracker setup teams"

#: Graph answers 403 when the signed-in account may not read chats at all
#: (no Teams for this account, or a policy against the application).
_REFUSED_STATUSES: Final[frozenset[int]] = frozenset(
    {httpx.codes.UNAUTHORIZED, httpx.codes.FORBIDDEN}
)

#: The chat's last message, when the listing was asked to include it.
_PREVIEW: Final[str] = "lastMessagePreview"

#: Characters of a chat identifier written into a URL path as they are. Chat
#: identifiers look like ``19:abc@thread.v2``; everything that could change the
#: address (``/``, ``?``, ``#``, ``%``…) is encoded.
_IDENTIFIER_SAFE_CHARACTERS: Final[str] = ":@."


@dataclass(frozen=True, slots=True)
class TeamsMember:
    """Somebody in a chat.

    Attributes:
        user_id: Their directory identifier.
        name: Their display name, possibly empty.
        email: Their address, lower-cased; empty when Graph does not give one.
    """

    user_id: str
    name: str
    email: str


@dataclass(frozen=True, slots=True)
class TeamsChat:
    """One chat, without its messages.

    Attributes:
        chat_id: Graph's identifier for the chat.
        topic: Its name, empty when nobody gave it one.
        members: Everybody in it, the signed-in person included.
        has_messages: ``False`` only when Graph said nobody has written yet.
        last_message_at: When its newest message was written, when Graph says.
    """

    chat_id: str
    topic: str
    members: tuple[TeamsMember, ...]
    has_messages: bool
    last_message_at: datetime | None

    def touched_since(self, start: datetime) -> bool:
        """Whether the chat may hold a message written since a moment."""
        if not self.has_messages:
            return False
        return self.last_message_at is None or self.last_message_at >= start


@dataclass(frozen=True, slots=True)
class TeamsMessage:
    """One message a person wrote in a chat.

    Attributes:
        message_id: Graph's identifier, unique within the chat.
        sent_at: When it was written, in UTC.
        sender_id: The writer's directory identifier.
        sender_name: The writer's display name, possibly empty.
        text: The body as plain text, possibly empty.
    """

    message_id: str
    sent_at: datetime
    sender_id: str
    sender_name: str
    text: str


class TeamsChats:
    """Reads the signed-in person's Teams chats over Microsoft Graph."""

    def __init__(self, tokens: AccessTokenProvider) -> None:
        """Bind the reader to a key supplier.

        Args:
            tokens: Supplies a valid Teams access key before every call.
        """
        self._graph = GraphSession(
            tokens,
            what="Teams",
            redo_command=_REDO_COMMAND,
            refused_statuses=_REFUSED_STATUSES,
        )

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

    async def signed_in_user(self) -> TeamsMember:
        """Read who signed in.

        Returns:
            Their identifier, name and address (``mail``, else the sign-in name).
        """
        payload = await self._graph.get(
            f"{MICROSOFT_GRAPH_URL}/me",
            {"$select": "id,displayName,mail,userPrincipalName"},
        )
        address = payload.get("mail") or payload.get("userPrincipalName") or ""
        return TeamsMember(
            user_id=str(payload.get("id") or ""),
            name=str(payload.get("displayName") or "").strip(),
            email=str(address).strip().lower(),
        )

    async def list_chats(self) -> list[TeamsChat]:
        """Read every one-to-one and group chat, with its members.

        Returns:
            The chats; meeting chats are left out.

        Raises:
            SourceAuthError: If Microsoft refused the key.
            SourceUnavailableError: If Graph could not be reached or the
                listing never ends.
        """
        chats: list[TeamsChat] = []
        pages = self._graph.pages(
            f"{MICROSOFT_GRAPH_URL}/me/chats",
            {"$expand": f"members,{_PREVIEW}", "$top": TEAMS_CHAT_PAGE_SIZE},
        )
        async for payload in pages:
            chats.extend(
                chat
                for item in payload.get(VALUE) or []
                if isinstance(item, dict) and (chat := _parse_chat(item)) is not None
            )
        return chats

    async def messages_since(self, chat_id: str, start: datetime) -> list[TeamsMessage]:
        """Read one chat's messages written since a moment, newest first.

        Paging stops at the first message older than ``start``, so a long chat
        costs one page when nothing new was written in it.

        Args:
            chat_id: Graph's identifier for the chat.
            start: The start of the window, in UTC.

        Returns:
            The messages people wrote inside the window, newest first.
        """
        found: list[TeamsMessage] = []
        pages = self._graph.pages(
            f"{MICROSOFT_GRAPH_URL}/chats/{quote(chat_id, safe=_IDENTIFIER_SAFE_CHARACTERS)}"
            "/messages",
            {"$top": TEAMS_MESSAGE_PAGE_SIZE, "$orderby": "createdDateTime desc"},
        )
        async with aclosing(pages) as listing:
            async for payload in listing:
                reached_start = _collect_page(payload, start, found)
                if reached_start:
                    break
        return found


def _collect_page(payload: dict[str, Any], start: datetime, found: list[TeamsMessage]) -> bool:
    """Add one page's messages written since ``start``.

    Returns:
        Whether a message older than ``start`` was met, so no later page is needed.
    """
    for item in payload.get(VALUE) or []:
        if not isinstance(item, dict):
            continue
        written = parse_timestamp(item.get("createdDateTime"))
        if written is None:
            continue
        if written < start:
            return True
        message = _parse_message(item, written)
        if message is not None:
            found.append(message)
    return False


def _parse_chat(item: dict[str, Any]) -> TeamsChat | None:
    """Turn one Graph chat into a record, or ``None`` for a kind that is not read."""
    chat_id = str(item.get("id") or "")
    if not chat_id or item.get("chatType") not in TEAMS_CHAT_TYPES:
        return None
    preview = item.get(_PREVIEW)
    last_message_at = (
        parse_timestamp(preview.get("createdDateTime")) if isinstance(preview, dict) else None
    )
    return TeamsChat(
        chat_id=chat_id,
        topic=str(item.get("topic") or "").strip(),
        members=tuple(
            member
            for entry in item.get("members") or []
            if isinstance(entry, dict) and (member := _parse_member(entry)) is not None
        ),
        # Graph sends the preview as null for a chat nobody has written in yet.
        has_messages=not (_PREVIEW in item and preview is None),
        last_message_at=last_message_at,
    )


def _parse_member(entry: dict[str, Any]) -> TeamsMember | None:
    """Turn one chat member into a record, or ``None`` when it names nobody."""
    user_id = str(entry.get("userId") or "")
    if not user_id:
        return None
    return TeamsMember(
        user_id=user_id,
        name=str(entry.get("displayName") or "").strip(),
        email=str(entry.get("email") or "").strip().lower(),
    )


def _parse_message(item: dict[str, Any], written: datetime) -> TeamsMessage | None:
    """Turn one Graph chat message into a record, or ``None`` when no person wrote it.

    System events, deleted messages and messages from a bot or an app (which
    have no user behind them) are left out.
    """
    message_id = str(item.get("id") or "")
    if (
        not message_id
        or item.get("messageType") != TEAMS_PERSON_MESSAGE_TYPE
        or item.get("deletedDateTime")
    ):
        return None
    sender = item.get("from")
    user = sender.get("user") if isinstance(sender, dict) else None
    if not isinstance(user, dict) or not user.get("id"):
        return None
    return TeamsMessage(
        message_id=message_id,
        sent_at=written,
        sender_id=str(user["id"]),
        sender_name=str(user.get("displayName") or "").strip(),
        text=_plain_text(item.get("body")),
    )


def _plain_text(body: Any) -> str:  # noqa: ANN401 - raw Graph payload
    """Read a message body as plain text, converting HTML."""
    if not isinstance(body, dict):
        return ""
    content = str(body.get("content") or "")
    if str(body.get("contentType") or "").lower() == "html":
        return html_to_text(content)
    return content.strip()
