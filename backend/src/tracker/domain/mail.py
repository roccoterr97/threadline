"""One mailbox message, whichever kind of mailbox it came from.

Microsoft Graph and a standard (IMAP) mailbox describe a message very
differently. Each reader maps its own source onto :class:`MailMessage`, so the
mail collector's grouping, noise rules and writing are the same code for both.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class MailMessage:
    """One mailbox message as a reader saw it.

    Attributes:
        message_id: The reader's identifier for the message, stable for this
            mailbox across runs.
        conversation_id: The reader's identifier for the thread.
        subject: The subject line, empty when there is none.
        sent_at: When the message was sent, in UTC.
        sender_address: The sender's address, lower-cased.
        sender_name: The sender's display name.
        recipients: The ``To`` recipients, as ``(address, name)`` pairs.
        has_list_unsubscribe: Whether the message carried the bulk-sender header.
        body: The plain-text body, or ``None`` after the metadata pass.
        reply_to: The Reply-To entries, as ``(address, name)`` pairs. Shared
            senders such as calendars put the real person here.
        is_calendar_message: Whether it is an invitation, update, cancellation
            or reply to one.
        from_owner: Whether the mailbox itself files the message as sent by the
            owner (it sits in the Sent folder), whatever address it went from.
    """

    message_id: str
    conversation_id: str
    subject: str
    sent_at: datetime
    sender_address: str
    sender_name: str
    recipients: tuple[tuple[str, str], ...]
    has_list_unsubscribe: bool
    body: str | None = None
    reply_to: tuple[tuple[str, str], ...] = ()
    is_calendar_message: bool = False
    from_owner: bool = False
