"""Reading the owner's chats with a saved login, read-only.

Only two kinds of request are ever made: the chat list and a chat's history.
Neither marks anything as read, and the client has updates switched off, so it
receives nothing it was not asked for.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Final

from telethon import TelegramClient, types

from tracker.domain.telegram import (
    ChatKind,
    MediaKind,
    TelegramAccount,
    TelegramChat,
    TelegramMessage,
)
from tracker.infrastructure.telegram.connection import (
    LOGIN_ENDED,
    build_client,
    disconnect,
    reading_errors,
)
from tracker.shared.constants.telegram import TELEGRAM_MAX_CHATS
from tracker.shared.errors import SourceAuthError

#: What a message carried, by the Telethon property that holds it, most
#: specific first: a voice message is also a document, a GIF also a video.
_MEDIA_PROPERTIES: Final[tuple[tuple[str, MediaKind], ...]] = (
    ("voice", MediaKind.VOICE),
    ("video_note", MediaKind.VIDEO_NOTE),
    ("gif", MediaKind.GIF),
    ("sticker", MediaKind.STICKER),
    ("video", MediaKind.VIDEO),
    ("audio", MediaKind.AUDIO),
    ("photo", MediaKind.PHOTO),
    ("venue", MediaKind.LOCATION),
    ("geo", MediaKind.LOCATION),
    ("contact", MediaKind.CONTACT),
    ("poll", MediaKind.POLL),
    ("document", MediaKind.FILE),
)


class TelethonReader:
    """Reads chats and messages through one connected, logged-in client."""

    def __init__(self, client: TelegramClient) -> None:
        """Bind the reader to a connected client.

        Args:
            client: A client already connected with a working login.
        """
        self._client = client
        # Telegram needs the chat object it listed, not just a number, to
        # read a chat's history; each one is kept as the list is read.
        self._peers: dict[int, Any] = {}

    async def account_name(self) -> str:
        """The logged-in account's own name; proves the saved login still works."""
        with reading_errors():
            me = await self._client.get_me()
        return _person_name(me)

    async def chats_since(self, since: datetime) -> Sequence[TelegramChat]:
        """Every chat whose newest message was sent at or after a moment, newest first.

        Telegram lists pinned chats first and every other chat newest first,
        so the list is read only until the first unpinned chat older than
        ``since``.
        """
        chats: list[TelegramChat] = []
        with reading_errors():
            async for dialog in self._client.iter_dialogs(limit=TELEGRAM_MAX_CHATS):
                last = dialog.date
                if last is None or last < since:
                    if dialog.pinned:
                        continue
                    break
                self._peers[dialog.entity.id] = dialog.entity
                chats.append(_chat_of(dialog.entity, last))
        return chats

    async def recent_messages(self, chat: TelegramChat, limit: int) -> Sequence[TelegramMessage]:
        """The newest messages of one chat, at most ``limit``, newest first."""
        peer = self._peers.get(chat.chat_id, chat.chat_id)
        with reading_errors():
            found = [raw async for raw in self._client.iter_messages(peer, limit=limit)]
        return [message for raw in found if (message := _message_of(raw)) is not None]


@asynccontextmanager
async def open_telegram(
    account: TelegramAccount,
    make_client: Callable[[TelegramAccount], TelegramClient] | None = None,
) -> AsyncIterator[TelethonReader]:
    """Connect with the saved login for one collection, and disconnect afterwards.

    Args:
        account: The owner's application and saved login.
        make_client: Builds the client; replaced in tests.

    Yields:
        A reader on the owner's account.

    Raises:
        ConfigurationError: If the saved login cannot be read.
        SourceAuthError: If Telegram no longer accepts the saved login.
        SourceUnavailableError: If Telegram could not be reached.
    """
    client = (make_client or _client_for)(account)
    try:
        with reading_errors():
            await client.connect()
            authorised = await client.is_user_authorized()
        if not authorised:
            raise SourceAuthError(LOGIN_ENDED)
        yield TelethonReader(client)
    finally:
        await disconnect(client)


def _client_for(account: TelegramAccount) -> TelegramClient:
    """Build the real client for the owner's account."""
    return build_client(account.app, account.session.get_secret_value())


def _chat_of(entity: Any, last_message_at: datetime) -> TelegramChat:  # noqa: ANN401 - untyped Telethon
    """Turn a person, a group or a channel Telegram listed into a plain record."""
    if isinstance(entity, types.User):
        return TelegramChat(
            chat_id=entity.id,
            kind=ChatKind.PERSON,
            first_name=entity.first_name or "",
            last_name=entity.last_name or "",
            username=entity.username,
            is_bot=bool(entity.bot),
            is_self=bool(entity.is_self),
            is_deleted=bool(entity.deleted),
            is_support=bool(entity.support),
            last_message_at=last_message_at,
        )
    broadcast = isinstance(entity, types.Channel) and not entity.megagroup
    kind = ChatKind.CHANNEL if broadcast else ChatKind.GROUP
    return TelegramChat(chat_id=entity.id, kind=kind, last_message_at=last_message_at)


def _message_of(raw: Any) -> TelegramMessage | None:  # noqa: ANN401 - untyped Telethon
    """Turn one Telethon message into a plain record, or ``None`` for one to leave out.

    A phone call is kept as a mark, since it is contact; every other service
    notice ("joined Telegram", a pinned message) and an empty message is left out.
    """
    action = getattr(raw, "action", None)
    if action is not None:
        if not isinstance(action, types.MessageActionPhoneCall):
            return None
        return TelegramMessage(raw.id, raw.date, outgoing=bool(raw.out), media=MediaKind.CALL)
    text = raw.message or ""
    media = _media_of(raw)
    if not text and media is None:
        return None
    return TelegramMessage(raw.id, raw.date, outgoing=bool(raw.out), text=text, media=media)


def _media_of(raw: Any) -> MediaKind | None:  # noqa: ANN401 - untyped Telethon
    """What a message carried besides its text; a link preview counts as text alone."""
    media = raw.media
    if media is None or isinstance(media, types.MessageMediaWebPage):
        return None
    return next(
        (kind for name, kind in _MEDIA_PROPERTIES if getattr(raw, name, None) is not None),
        MediaKind.OTHER,
    )


def _person_name(user: Any) -> str:  # noqa: ANN401 - untyped Telethon
    """A user's first and last name, else their username, else their number."""
    name = " ".join(part for part in (user.first_name, user.last_name) if part)
    return name or (f"@{user.username}" if user.username else str(user.id))
