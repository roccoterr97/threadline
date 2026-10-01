"""Turning a snapshot row into a message.

LinkedIn's archive carries no message identifier, so one is derived here: the
SHA-256 of the conversation identifier, the timestamp, the sender's profile link
and the text. The same row always yields the same identifier, which is what lets
a second run recognise a message it has already stored.

The trade-off is written down in the plan: if LinkedIn ever edits the stored
text of an old message, its hash changes and the message looks new. Accepted —
a duplicate is visible, a silently dropped message is not.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from tracker.shared.logging import get_logger

#: Column names as the snapshot spells them.
CONVERSATION_ID_FIELD: Final[str] = "CONVERSATION ID"
CONVERSATION_TITLE_FIELD: Final[str] = "CONVERSATION TITLE"
FROM_FIELD: Final[str] = "FROM"
SENDER_PROFILE_FIELD: Final[str] = "SENDER PROFILE URL"
TO_FIELD: Final[str] = "TO"
RECIPIENT_PROFILES_FIELD: Final[str] = "RECIPIENT PROFILE URLS"
DATE_FIELD: Final[str] = "DATE"
SUBJECT_FIELD: Final[str] = "SUBJECT"
CONTENT_FIELD: Final[str] = "CONTENT"
FOLDER_FIELD: Final[str] = "FOLDER"

#: Timestamp format the snapshot uses, always in UTC.
DATE_FORMAT: Final[str] = "%Y-%m-%d %H:%M:%S"

#: Suffix the snapshot appends to every timestamp.
DATE_SUFFIX: Final[str] = " UTC"

#: Separators LinkedIn uses inside the recipient columns.
_LIST_SEPARATORS: Final[str] = ",;|"

_log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SnapshotMessage:
    """One archived LinkedIn message, with a derived identifier.

    Attributes:
        message_id: SHA-256 of the fields that make the row unique.
        conversation_id: LinkedIn's identifier for the thread.
        conversation_title: The thread's title, as LinkedIn shows it.
        sent_at: When the message was sent, in UTC.
        sender_profile_url: The sender's profile link, normalised.
        sender_name: The sender's display name.
        recipient_profile_urls: The recipients' profile links, normalised.
        recipient_names: The recipients' display names.
        subject: The message subject, empty when there is none.
        content: The message text.
        folder: The snapshot folder the row came from.
    """

    message_id: str
    conversation_id: str
    conversation_title: str
    sent_at: datetime
    sender_profile_url: str
    sender_name: str
    recipient_profile_urls: tuple[str, ...]
    recipient_names: tuple[str, ...]
    subject: str
    content: str
    folder: str


def parse_rows(rows: Iterable[dict[str, str]]) -> Iterator[SnapshotMessage]:
    """Turn raw snapshot rows into messages, skipping the unusable ones.

    Args:
        rows: Raw rows as the client read them.

    Yields:
        One message per row that carries a thread, a date and a sender.
    """
    skipped = 0
    for row in rows:
        message = parse_row(row)
        if message is None:
            skipped += 1
            continue
        yield message
    if skipped:
        _log.warning("linkedin_rows_skipped", rows=skipped)


def parse_row(row: dict[str, str]) -> SnapshotMessage | None:
    """Turn one snapshot row into a message.

    Args:
        row: A raw row.

    Returns:
        The message, or ``None`` when the row has no thread identifier or no
        readable date — either makes it impossible to store safely.
    """
    conversation_id = row.get(CONVERSATION_ID_FIELD, "").strip()
    sent_at = parse_timestamp(row.get(DATE_FIELD, ""))
    if not conversation_id or sent_at is None:
        return None
    sender_profile_url = normalise_profile_url(row.get(SENDER_PROFILE_FIELD, ""))
    content = row.get(CONTENT_FIELD, "")
    return SnapshotMessage(
        message_id=build_message_id(conversation_id, sent_at, sender_profile_url, content),
        conversation_id=conversation_id,
        conversation_title=row.get(CONVERSATION_TITLE_FIELD, "").strip(),
        sent_at=sent_at,
        sender_profile_url=sender_profile_url,
        sender_name=row.get(FROM_FIELD, "").strip(),
        recipient_profile_urls=tuple(
            normalise_profile_url(value)
            for value in _split_list(row.get(RECIPIENT_PROFILES_FIELD, ""))
        ),
        recipient_names=tuple(_split_list(row.get(TO_FIELD, ""))),
        subject=row.get(SUBJECT_FIELD, "").strip(),
        content=content,
        folder=row.get(FOLDER_FIELD, "").strip(),
    )


def build_message_id(
    conversation_id: str,
    sent_at: datetime,
    sender_profile_url: str,
    content: str,
) -> str:
    """Derive the stable identifier of one archived message.

    Args:
        conversation_id: LinkedIn's identifier for the thread.
        sent_at: When the message was sent.
        sender_profile_url: The sender's normalised profile link.
        content: The message text.

    Returns:
        The SHA-256 digest, as lower-case hexadecimal.
    """
    parts = (
        conversation_id,
        sent_at.astimezone(UTC).isoformat(),
        sender_profile_url,
        content,
    )
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def parse_timestamp(raw: str) -> datetime | None:
    """Read a snapshot timestamp.

    Args:
        raw: A value such as ``2026-09-18 07:14:22 UTC``.

    Returns:
        The instant in UTC, or ``None`` when the value cannot be read.
    """
    cleaned = raw.strip()
    if cleaned.upper().endswith(DATE_SUFFIX.strip()):
        cleaned = cleaned[: -len(DATE_SUFFIX.strip())].strip()
    try:
        return datetime.strptime(cleaned, DATE_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        return None


def normalise_profile_url(raw: str) -> str:
    """Reduce a profile link to a comparable form.

    Args:
        raw: A profile link, possibly with a scheme, a ``www.`` host, a trailing
            slash or a query string.

    Returns:
        The lower-case link without scheme, host prefix, query or trailing
        slash, so two spellings of one profile compare equal.
    """
    cleaned = raw.strip().lower()
    if not cleaned:
        return ""
    cleaned = cleaned.split("?", maxsplit=1)[0].split("#", maxsplit=1)[0]
    for prefix in ("https://", "http://"):
        cleaned = cleaned.removeprefix(prefix)
    cleaned = cleaned.removeprefix("www.")
    return cleaned.rstrip("/")


def _split_list(raw: str) -> list[str]:
    """Split one of the snapshot's list-shaped columns."""
    value = raw
    for separator in _LIST_SEPARATORS[1:]:
        value = value.replace(separator, _LIST_SEPARATORS[0])
    return [part.strip() for part in value.split(_LIST_SEPARATORS[0]) if part.strip()]
