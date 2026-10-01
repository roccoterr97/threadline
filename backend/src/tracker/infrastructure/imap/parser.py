"""Reading what an IMAP server sends back: FETCH answers, headers and bodies.

Everything here is untrusted input from somebody's inbox. Nothing raises on a
malformed message: a header that cannot be decoded becomes empty or keeps its
readable part, an unknown character set falls back to UTF-8 with replacement
characters, and a body is cut to a fixed length.
"""

from __future__ import annotations

import email
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email import policy
from email.errors import MessageError
from email.headerregistry import AddressHeader, DateHeader
from email.message import EmailMessage, Message
from email.parser import BytesHeaderParser
from email.utils import getaddresses
from typing import Final

from tracker.infrastructure.imap.html_text import html_to_text

#: Where one FETCH answer starts: ``<sequence number> (``.
_RECORD_START: Final[re.Pattern[bytes]] = re.compile(rb"^\d+ \(")
_UID: Final[re.Pattern[bytes]] = re.compile(rb"\bUID (\d+)")
_GMAIL_THREAD: Final[re.Pattern[bytes]] = re.compile(rb"\bX-GM-THRID (\d+)")
_GMAIL_MESSAGE: Final[re.Pattern[bytes]] = re.compile(rb"\bX-GM-MSGID (\d+)")
_INTERNAL_DATE: Final[re.Pattern[bytes]] = re.compile(rb'\bINTERNALDATE "([^"]+)"')

#: How IMAP writes an arrival time: ``17-Jul-1996 02:44:25 -0700``.
_INTERNAL_DATE_FORMAT: Final[str] = "%d-%b-%Y %H:%M:%S %z"

#: One message identifier, as it appears in Message-ID, In-Reply-To and References.
_MESSAGE_ID: Final[re.Pattern[str]] = re.compile(r"<[^<>\s]+>")

#: Errors the standard library's e-mail parsing can raise on hostile input.
_PARSE_ERRORS: Final[tuple[type[Exception], ...]] = (
    MessageError,
    ValueError,
    IndexError,
    TypeError,
    AttributeError,
)

#: imaplib hands each fetched message over as an (envelope, literal) pair.
_PAIR: Final[int] = 2

_PLAIN: Final[str] = "plain"
_HTML: Final[str] = "html"
_FALLBACK_CHARSET: Final[str] = "utf-8"


@dataclass(frozen=True, slots=True)
class FetchRecord:
    """One message's part of a FETCH answer.

    Attributes:
        uid: The message's UID in the folder it was fetched from.
        internal_date: When the server received it, in UTC, when asked for.
        gmail_thread_id: Gmail's thread identifier, when the server offers it.
        gmail_message_id: Gmail's message identifier, when the server offers it.
        literal: The fetched headers or message, as raw bytes.
    """

    uid: int
    internal_date: datetime | None
    gmail_thread_id: str | None
    gmail_message_id: str | None
    literal: bytes


@dataclass(frozen=True, slots=True)
class HeaderFacts:
    """What the collector needs from one message's headers.

    Attributes:
        message_id: The Message-ID, empty when there is none.
        in_reply_to: The first identifier in In-Reply-To, empty when none.
        references: The identifiers in References, oldest first.
        subject: The decoded subject, empty when there is none.
        sent_at: The Date header in UTC, or ``None`` when it cannot be read.
        sender: The From address (lower-cased) and display name.
        recipients: The To entries, as ``(address, name)`` pairs.
        reply_to: The Reply-To entries, as ``(address, name)`` pairs.
        has_list_unsubscribe: Whether a List-Unsubscribe header is present.
    """

    message_id: str = ""
    in_reply_to: str = ""
    references: tuple[str, ...] = ()
    subject: str = ""
    sent_at: datetime | None = None
    sender: tuple[str, str] = ("", "")
    recipients: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    reply_to: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    has_list_unsubscribe: bool = False


def parse_fetch(data: Sequence[object]) -> list[FetchRecord]:
    """Split a FETCH answer into one record per message.

    imaplib returns each message as a ``(envelope, literal)`` pair, followed by
    a closing piece that may carry items the server sent after the literal.

    Args:
        data: The data part of ``uid("FETCH", …)``'s answer.

    Returns:
        One record per message that carried a UID.
    """
    pieces: list[tuple[bytes, bytes]] = []
    for item in data:
        if isinstance(item, tuple) and len(item) == _PAIR:
            envelope, literal = item
            if isinstance(envelope, bytes) and isinstance(literal, bytes):
                pieces.append((envelope, literal))
        elif isinstance(item, bytes) and _RECORD_START.match(item):
            pieces.append((item, b""))
        elif isinstance(item, bytes) and pieces:
            envelope, literal = pieces[-1]
            pieces[-1] = (envelope + b" " + item, literal)
    return [record for piece in pieces if (record := _record(*piece)) is not None]


def _record(envelope: bytes, literal: bytes) -> FetchRecord | None:
    """Read the items of one message's envelope."""
    uid = _UID.search(envelope)
    if uid is None:
        return None
    thread = _GMAIL_THREAD.search(envelope)
    message = _GMAIL_MESSAGE.search(envelope)
    arrived = _INTERNAL_DATE.search(envelope)
    return FetchRecord(
        uid=int(uid.group(1)),
        internal_date=_internal_date(arrived.group(1)) if arrived else None,
        gmail_thread_id=thread.group(1).decode() if thread else None,
        gmail_message_id=message.group(1).decode() if message else None,
        literal=literal,
    )


def _internal_date(raw: bytes) -> datetime | None:
    """Read an INTERNALDATE value as a UTC moment."""
    try:
        moment = datetime.strptime(raw.decode("ascii").strip(), _INTERNAL_DATE_FORMAT)
    except (UnicodeDecodeError, ValueError):
        return None
    return moment.astimezone(UTC)


def parse_headers(raw: bytes) -> HeaderFacts:
    """Read the headers the metadata pass fetched.

    Args:
        raw: The header block, as the server sent it.

    Returns:
        The facts, with anything unreadable left empty.
    """
    headers = BytesHeaderParser(policy=policy.default).parsebytes(raw)
    references = _MESSAGE_ID.findall(_text(headers, "References"))
    replying_to = _MESSAGE_ID.findall(_text(headers, "In-Reply-To"))
    own = _MESSAGE_ID.findall(_text(headers, "Message-ID"))
    senders = _addresses(headers, "From")
    return HeaderFacts(
        message_id=own[0] if own else "",
        in_reply_to=replying_to[0] if replying_to else "",
        references=tuple(references),
        subject=" ".join(_text(headers, "Subject").split()),
        sent_at=_sent_at(headers),
        sender=senders[0] if senders else ("", ""),
        recipients=_addresses(headers, "To"),
        reply_to=_addresses(headers, "Reply-To"),
        has_list_unsubscribe=headers.get("List-Unsubscribe") is not None,
    )


def _text(headers: Message, name: str) -> str:
    """One header's decoded text, empty when absent or unreadable."""
    try:
        value = headers.get(name)
    except _PARSE_ERRORS:
        return ""
    return _clean(str(value)) if value is not None else ""


def _addresses(headers: Message, name: str) -> tuple[tuple[str, str], ...]:
    """An address header's entries, as lower-case addresses and display names."""
    try:
        value = headers.get(name)
        if value is None:
            return ()
        if isinstance(value, AddressHeader):
            pairs = [(entry.addr_spec, entry.display_name) for entry in value.addresses]
        else:
            pairs = [(address, display) for display, address in getaddresses([str(value)])]
    except _PARSE_ERRORS:
        return ()
    return tuple(
        (_clean(address).strip().lower(), _clean(display).strip())
        for address, display in pairs
        if "@" in address
    )


def _sent_at(headers: Message) -> datetime | None:
    """The Date header as a UTC moment, or ``None`` when it cannot be read."""
    try:
        value = headers.get("Date")
    except _PARSE_ERRORS:
        return None
    if not isinstance(value, DateHeader) or value.datetime is None:
        return None
    moment = value.datetime
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _clean(text: str) -> str:
    """Replace characters that cannot be stored, such as undecodable bytes."""
    return text.encode("utf-8", "replace").decode("utf-8")


def extract_body(raw: bytes, limit: int) -> str:
    """The readable text of a message, preferring its plain-text part.

    Attachments are never read. A message with only an HTML part has its HTML
    turned into text.

    Args:
        raw: The whole message, or its first bytes.
        limit: Most characters kept.

    Returns:
        The body text, cut to ``limit`` characters; empty when there is none.
    """
    try:
        message = email.message_from_bytes(raw, policy=policy.default)
        part = _body_part(message)
    except _PARSE_ERRORS:
        return ""
    if part is None:
        return ""
    text = _part_text(part)
    if part.get_content_subtype() == _HTML:
        text = html_to_text(text)
    return text.strip()[:limit]


def _body_part(message: Message) -> EmailMessage | None:
    """The part holding the body: plain text first, HTML second, never an attachment."""
    if not isinstance(message, EmailMessage):
        return None
    part = message.get_body(preferencelist=(_PLAIN, _HTML))
    return part if isinstance(part, EmailMessage) else None


def _part_text(part: EmailMessage) -> str:
    """Decode one text part, falling back to UTF-8 for an unknown character set."""
    try:
        content = part.get_content()
    except LookupError:
        content = None
    except _PARSE_ERRORS:
        return ""
    if isinstance(content, str):
        return _clean(content)
    payload = part.get_payload(decode=True)
    if isinstance(payload, bytes):
        return payload.decode(_FALLBACK_CHARSET, "replace")
    return ""
