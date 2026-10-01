"""The shape a collected thread travels in, whatever source it came from.

LinkedIn rows and Graph messages look nothing alike, so each collector maps its
own source onto these records. Everything downstream — the person matcher, the
writer, the command line — works on these and knows nothing about either source.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

from tracker.domain.enums import Channel, Direction, Relevance

#: What a collection command prints for a source the owner never set up. The
#: daily recipe looks for exactly this line and then records nothing for it.
NOT_CONFIGURED_LINE: Final[str] = "not configured — skipped"


@dataclass(frozen=True, slots=True)
class RawParticipant:
    """Somebody other than the owner who took part in a thread.

    Attributes:
        channel: Where the identifier is used.
        identifier: A LinkedIn profile link or an e-mail address.
        display_name: The name the source spelled for them.
        organisation_name: The company, when a shared sender names only the
            company behind a message (see :mod:`tracker.domain.relay`).
    """

    channel: Channel
    identifier: str
    display_name: str
    organisation_name: str | None = None

    @property
    def key(self) -> tuple[Channel, str]:
        """The natural key this participant is looked up by."""
        return (self.channel, self.identifier)


@dataclass(frozen=True, slots=True)
class RawMessage:
    """One collected message.

    Attributes:
        source_message_id: The identifier that makes the message unique in its
            thread — Graph's own for e-mail, a derived hash for LinkedIn.
        sent_at: When it was sent, in UTC.
        direction: Whether the owner wrote it.
        sender_identifier: The sender's address or profile link.
        body: The text, or ``None`` when the thread is noise and keeps none.
    """

    source_message_id: str
    sent_at: datetime
    direction: Direction
    sender_identifier: str | None
    body: str | None


@dataclass(frozen=True, slots=True)
class RawConversation:
    """One collected thread, with the obvious-noise rules already applied.

    Attributes:
        channel: Where the thread lives.
        source_conversation_id: The identifier its source gave it.
        subject: The thread's subject; dropped on write when it is noise.
        relevance: What the prefilter decided.
        participants: Everybody in the thread except the owner.
        messages: The thread's messages, in no particular order.
        meeting_at: For a calendar meeting, when it starts; ``None`` otherwise
            and for a cancelled one.
    """

    channel: Channel
    source_conversation_id: str
    subject: str | None
    relevance: Relevance
    participants: tuple[RawParticipant, ...] = ()
    messages: tuple[RawMessage, ...] = ()
    meeting_at: datetime | None = None

    @property
    def is_noise(self) -> bool:
        """Whether the thread keeps no text."""
        return self.relevance is Relevance.NOISE


@dataclass(frozen=True, slots=True)
class CollectionReport:
    """What one collection run found and wrote.

    Counts only: never a subject, never a body, never an address.

    Attributes:
        not_configured: The owner never set this source up, so nothing was
            read. That is not a failure, and the run does not count it as one.
    """

    channel: Channel
    conversations_found: int = 0
    conversations_new: int = 0
    conversations_noise: int = 0
    messages_found: int = 0
    messages_new: int = 0
    people_new: int = 0
    review_items_new: int = 0
    folders_seen: tuple[str, ...] = field(default_factory=tuple)
    not_configured: bool = False

    def as_lines(self) -> tuple[str, ...]:
        """Render the report for the command line.

        Returns:
            One short line per number, in reading order, or the "not
            configured" line when the source was skipped.
        """
        if self.not_configured:
            return (f"channel: {self.channel.value}", NOT_CONFIGURED_LINE)
        return (
            f"channel: {self.channel.value}",
            f"conversations found: {self.conversations_found}"
            f" (new: {self.conversations_new}, noise: {self.conversations_noise})",
            f"messages found: {self.messages_found} (new: {self.messages_new})",
            f"people added: {self.people_new}",
            f"questions to review added: {self.review_items_new}",
        )


#: The second half of a collection. A collector's ``read`` makes every request
#: to the outside source and hands back this step, which makes every database
#: write and reports the counts. Keeping the halves apart lets several sources
#: be read at the same time while they are still stored one after another.
SaveStep = Callable[[], CollectionReport]
