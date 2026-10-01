"""What the mail collector needs from a mailbox, whichever kind it is.

Microsoft Graph and a standard (IMAP) mailbox both satisfy
:class:`MailboxReader`. The collector opens each configured mailbox through a
:class:`MailboxSource` and never learns which kind it is talking to.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from tracker.domain.mail import MailMessage
from tracker.shared.constants.mailbox import MailSource


class MailboxReader(Protocol):
    """Reads one mailbox, read-only, in the collector's two passes."""

    async def list_messages_since(self, since: datetime) -> list[MailMessage]:
        """Read the metadata of every message received since a moment, without bodies."""
        ...

    async def list_thread(self, conversation_id: str) -> list[MailMessage]:
        """Read the metadata of every message in one thread, however old."""
        ...

    async def fetch_body(self, message_id: str) -> str:
        """Read one message's body as plain text."""
        ...

    async def fetch_bodies(self, message_ids: Sequence[str]) -> list[str]:
        """Read several messages' bodies as plain text, in the order asked.

        The reader decides how: Graph asks for them side by side, IMAP sends one
        command for all those in a folder.
        """
        ...


#: Opens a mailbox for the length of one collection and closes it afterwards.
MailboxOpener = Callable[[], AbstractAsyncContextManager[MailboxReader]]


@dataclass(frozen=True, slots=True)
class MailboxSource:
    """One configured mailbox, ready to be opened.

    Attributes:
        kind: Which kind of mailbox it is, for the logs.
        open: Opens a reader on it, signed in.
    """

    kind: MailSource
    open: MailboxOpener
