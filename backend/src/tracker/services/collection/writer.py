"""Writing collected threads to the database, idempotently.

Every write is an upsert on a natural key, and the primary key a row already has
is reused, so running a collector twice leaves exactly the same rows behind.

This is also where the privacy rule is applied for the last time before anything
is stored: a thread judged noise is written with no subject and its messages
with no body, leaving only an identifier, the dates and the decision.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final
from uuid import UUID

from tracker.domain.enums import Channel, Direction, Relevance, RelevanceDecidedBy
from tracker.domain.models import Conversation, Message
from tracker.repositories import Repositories
from tracker.services.collection.models import RawConversation
from tracker.shared.logging import get_logger

_log = get_logger(__name__)

#: Deciders whose answer is richer than the obvious-noise rules', so a later
#: collection run never overwrites it.
DECIDED_BEYOND_RULES: Final[frozenset[RelevanceDecidedBy]] = frozenset(
    {RelevanceDecidedBy.OWNER, RelevanceDecidedBy.AI}
)


@dataclass(frozen=True, slots=True)
class WriteCounts:
    """How much of what was collected was new.

    Attributes:
        conversations_new: Threads stored for the first time.
        messages_found: Messages offered to the database.
        messages_new: Messages stored for the first time.
    """

    conversations_new: int = 0
    messages_found: int = 0
    messages_new: int = 0


class ConversationWriter:
    """Stores collected threads and their messages."""

    def __init__(self, repositories: Repositories) -> None:
        """Bind the writer to the repositories it writes through.

        Args:
            repositories: The repository container.
        """
        self._repositories = repositories

    def write(
        self,
        channel: Channel,
        conversations: Sequence[RawConversation],
        person_by_identity: dict[tuple[Channel, str], UUID],
    ) -> WriteCounts:
        """Write threads and messages, reusing the keys they already have.

        Args:
            channel: The channel every thread belongs to.
            conversations: The collected threads.
            person_by_identity: Who each participant is, from the matcher.

        Returns:
            How many rows were new.
        """
        if not conversations:
            return WriteCounts()
        existing = {
            conversation.source_conversation_id: conversation
            for conversation in self._repositories.conversations.list_by_sources(
                channel, [item.source_conversation_id for item in conversations]
            )
        }
        records = [
            _conversation_of(raw, existing.get(raw.source_conversation_id), person_by_identity)
            for raw in conversations
        ]
        self._repositories.conversations.bulk_upsert(records)
        counts = self._write_messages(conversations, records)
        _log.info(
            "conversations_written",
            channel=channel.value,
            conversations=len(records),
            new_conversations=len(records) - len(existing),
            new_messages=counts.messages_new,
        )
        return WriteCounts(
            conversations_new=len(records) - len(existing),
            messages_found=counts.messages_found,
            messages_new=counts.messages_new,
        )

    def _write_messages(
        self,
        conversations: Sequence[RawConversation],
        records: Sequence[Conversation],
    ) -> WriteCounts:
        """Write every thread's messages in one batch.

        Args:
            conversations: The collected threads.
            records: The conversation rows, in the same order.

        Returns:
            How many messages were offered and how many were new.
        """
        known = {
            (message.conversation_id, message.source_message_id): message
            for message in self._repositories.messages.list_for_conversations(
                [record.id for record in records]
            )
        }
        messages: list[Message] = []
        for raw, record in zip(conversations, records, strict=True):
            messages.extend(_messages_of(raw, record, known))
        self._repositories.messages.bulk_upsert(messages)
        new = sum(
            1
            for message in messages
            if (message.conversation_id, message.source_message_id) not in known
        )
        return WriteCounts(messages_found=len(messages), messages_new=new)


def _conversation_of(
    raw: RawConversation,
    existing: Conversation | None,
    person_by_identity: dict[tuple[Channel, str], UUID],
) -> Conversation:
    """Build the conversation row for one collected thread.

    Args:
        raw: The collected thread.
        existing: The row already stored, when there is one.
        person_by_identity: Who each participant is.

    Returns:
        The row to write. A noise thread carries no subject: the model drops it.
        The dates never shrink against the stored row: a thread rebuilt from
        the collection window alone (a noise thread is) may not hold its
        oldest or its owner's messages, which must not move or erase them.
    """
    relevance, decided_by = _decision(existing, raw)
    sent_times = [message.sent_at for message in raw.messages]
    conversation = Conversation(
        person_id=_person_of(raw, person_by_identity, relevance),
        channel=raw.channel,
        source_conversation_id=raw.source_conversation_id,
        subject=raw.subject,
        relevance=relevance,
        relevance_decided_by=decided_by,
        first_message_at=min(sent_times, default=None),
        last_message_at=max(sent_times, default=None),
        last_inbound_at=_latest(raw, Direction.INBOUND),
        last_outbound_at=_latest(raw, Direction.OUTBOUND),
        meeting_at=raw.meeting_at,
    )
    if existing is not None:
        conversation.id = existing.id
        _keep_known_dates(conversation, existing)
    return conversation


def _keep_known_dates(conversation: Conversation, existing: Conversation) -> None:
    """Keep the earliest first and the latest last dates the stored row knows."""
    conversation.first_message_at = _earliest(
        conversation.first_message_at, existing.first_message_at
    )
    conversation.last_message_at = _latest_of(
        conversation.last_message_at, existing.last_message_at
    )
    conversation.last_inbound_at = _latest_of(
        conversation.last_inbound_at, existing.last_inbound_at
    )
    conversation.last_outbound_at = _latest_of(
        conversation.last_outbound_at, existing.last_outbound_at
    )


def _decision(
    existing: Conversation | None,
    raw: RawConversation,
) -> tuple[Relevance, RelevanceDecidedBy | None]:
    """Work out the relevance to store and who decided it.

    The prefilter only ever says "obviously machine traffic" or "no opinion", so
    it must never overwrite the richer answer the assessment or the owner has
    already given.

    Args:
        existing: The row already stored, when there is one.
        raw: The collected thread.

    Returns:
        The relevance and the decider to write.
    """
    if existing is not None and existing.relevance_decided_by in DECIDED_BEYOND_RULES:
        return existing.relevance, existing.relevance_decided_by
    if raw.relevance is Relevance.NOISE:
        return Relevance.NOISE, RelevanceDecidedBy.RULE
    return raw.relevance, None


def _person_of(
    raw: RawConversation,
    person_by_identity: dict[tuple[Channel, str], UUID],
    relevance: Relevance,
) -> UUID | None:
    """Pick the person a thread is filed under.

    A group thread is filed under its first other participant and refined after
    the MVP; a noise thread is filed under nobody, so machine senders never
    appear in the people list.
    """
    if relevance is Relevance.NOISE:
        return None
    for participant in raw.participants:
        person_id = person_by_identity.get(participant.key)
        if person_id is not None:
            return person_id
    return None


def _earliest(found: datetime | None, stored: datetime | None) -> datetime | None:
    """The earlier of two moments, either of which may be unknown."""
    return min((moment for moment in (found, stored) if moment is not None), default=None)


def _latest_of(found: datetime | None, stored: datetime | None) -> datetime | None:
    """The later of two moments, either of which may be unknown."""
    return max((moment for moment in (found, stored) if moment is not None), default=None)


def _latest(raw: RawConversation, direction: Direction) -> datetime | None:
    """Return the most recent moment a message went in one direction."""
    return max(
        (message.sent_at for message in raw.messages if message.direction is direction),
        default=None,
    )


def _messages_of(
    raw: RawConversation,
    record: Conversation,
    known: dict[tuple[UUID, str], Message],
) -> list[Message]:
    """Build the message rows of one thread.

    Args:
        raw: The collected thread.
        record: The conversation row the messages hang from.
        known: The messages already stored, by thread and source identifier.

    Returns:
        The rows to write; a noise thread's messages carry no body. A thread
        that keeps text never trades a stored body for none or an empty one:
        a run that did not read the text (or could not find the message
        again) cannot know it is gone.
    """
    keeps_text = record.relevance is not Relevance.NOISE
    rows: list[Message] = []
    for message in raw.messages:
        stored = known.get((record.id, message.source_message_id))
        body = message.body if keeps_text else None
        if keeps_text and not body and stored is not None and stored.body:
            body = stored.body
        row = Message(
            conversation_id=record.id,
            source_message_id=message.source_message_id,
            direction=message.direction,
            sent_at=message.sent_at,
            sender_identifier=message.sender_identifier,
            body=body,
        )
        if stored is not None:
            row.id = stored.id
        rows.append(row)
    return rows
