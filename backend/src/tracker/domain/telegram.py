"""What reading Telegram involves, as plain values and rules.

The Telegram reader (``infrastructure/telegram``) turns Telegram's own objects
into these records; the collector and the set-up work on them and never see
the library behind the reader. The rules here decide which chats are a
conversation with a real person and how a message is written down.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final

from pydantic import SecretStr

from tracker.shared.constants.telegram import TELEGRAM_SERVICE_USER_ID

#: How a username is written in front of a name-less contact.
_USERNAME_MARK: Final[str] = "@"


class ChatKind(StrEnum):
    """What is on the other side of a Telegram chat."""

    PERSON = "person"
    GROUP = "group"
    CHANNEL = "channel"


class MediaKind(StrEnum):
    """What a message carried instead of, or beside, its text.

    Each value is the word written in its place, such as ``[photo]``: the
    content itself is never read.
    """

    PHOTO = "photo"
    VIDEO = "video"
    VOICE = "voice message"
    VIDEO_NOTE = "video message"
    AUDIO = "audio"
    STICKER = "sticker"
    GIF = "GIF"
    FILE = "file"
    LOCATION = "location"
    CONTACT = "contact"
    POLL = "poll"
    CALL = "call"
    OTHER = "attachment"


class TelegramLoginProblem(StrEnum):
    """Why a Telegram login did not go through, as far as the set-up must tell apart."""

    #: Telegram refused the api_id and api_hash.
    APP_REFUSED = "app_refused"
    #: Telegram refused the phone number, or it has no Telegram account.
    PHONE_REFUSED = "phone_refused"
    #: The code typed was not the one Telegram sent.
    CODE_WRONG = "code_wrong"
    #: The code is too old, or was used already.
    CODE_EXPIRED = "code_expired"
    #: The two-step verification password was wrong.
    PASSWORD_WRONG = "password_wrong"
    #: Telegram asked for a pause after too many tries.
    TOO_MANY_TRIES = "too_many_tries"


@dataclass(frozen=True, slots=True)
class TelegramApp:
    """The owner's own Telegram application, from my.telegram.org.

    Attributes:
        api_id: The application's number.
        api_hash: The application's key; never shown or logged.
    """

    api_id: int
    api_hash: SecretStr


@dataclass(frozen=True, slots=True)
class TelegramAccount:
    """What reading the owner's Telegram needs.

    Attributes:
        app: The owner's application.
        session: The saved login. It is full access to the account: never
            shown, logged or put in an error message.
    """

    app: TelegramApp
    session: SecretStr


@dataclass(frozen=True, slots=True)
class TelegramLogin:
    """What a finished login hands back.

    Attributes:
        session: The saved login, to keep as a secret.
        account_name: The account's own name, to say who is logged in.
    """

    session: SecretStr
    account_name: str


@dataclass(frozen=True, slots=True)
class TelegramChat:
    """One chat in the owner's list, without its messages.

    Attributes:
        chat_id: Telegram's number for the other side; for a person, their
            user id, which never changes.
        kind: A person, a group or a channel.
        first_name: The person's first name, as the owner's Telegram shows it.
        last_name: Their last name, often empty.
        username: Their public ``@name`` without the ``@``, when they have one.
        is_bot: Whether the other side is a bot.
        is_self: Whether it is the owner's own Saved Messages.
        is_deleted: Whether the account was deleted.
        is_support: Whether it is Telegram's own support or notices account.
        last_message_at: When the newest message in it was sent.
    """

    chat_id: int
    kind: ChatKind
    first_name: str = ""
    last_name: str = ""
    username: str | None = None
    is_bot: bool = False
    is_self: bool = False
    is_deleted: bool = False
    is_support: bool = False
    last_message_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class TelegramMessage:
    """One message of a private chat.

    Attributes:
        message_id: Telegram's number for it, unique within the chat.
        sent_at: When it was sent, in UTC.
        outgoing: Whether the owner sent it.
        text: Its text, or a photo's caption; empty when there is none.
        media: What it carried besides text, if anything.
    """

    message_id: int
    sent_at: datetime
    outgoing: bool
    text: str = ""
    media: MediaKind | None = None


def is_person_chat(chat: TelegramChat) -> bool:
    """Whether a chat is a one-to-one conversation with a real person.

    Groups, channels, bots, Telegram's own notices, the owner's Saved Messages
    and deleted accounts are never a conversation to follow.

    Args:
        chat: The chat.

    Returns:
        ``True`` only for a private chat with a living human account.
    """
    if chat.kind is not ChatKind.PERSON:
        return False
    if chat.is_bot or chat.is_self or chat.is_deleted or chat.is_support:
        return False
    return chat.chat_id != TELEGRAM_SERVICE_USER_ID


def display_name(chat: TelegramChat) -> str:
    """The name to file a person under: their name, else their ``@username``.

    Args:
        chat: A private chat.

    Returns:
        "First Last", "@username", or an empty string when neither is known.
    """
    name = " ".join(part.strip() for part in (chat.first_name, chat.last_name) if part.strip())
    if name:
        return name
    return f"{_USERNAME_MARK}{chat.username}" if chat.username else ""


def message_body(message: TelegramMessage) -> str:
    """Write a message down as text: what it carried in brackets, then its text.

    Args:
        message: The message.

    Returns:
        "[photo] caption", "[voice message]", or the text alone.
    """
    if message.media is None:
        return message.text
    mark = f"[{message.media.value}]"
    return f"{mark} {message.text}" if message.text else mark
