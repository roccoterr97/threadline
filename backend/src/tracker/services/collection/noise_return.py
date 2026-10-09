"""Bringing back what the assistant threw away, when the owner shows it matters.

The collection writer asks two questions while it stores threads: did the owner
write something new in a thread the assistant dropped, and is somebody the
assistant dropped now in a conversation of their own again? The rules are in
:mod:`tracker.domain.noise_return`; this module reads what they need and writes
the people back.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection, Iterable
from uuid import UUID

from tracker.domain.enums import Direction, Relevance, ReviewKind
from tracker.domain.models import Conversation, Message, Person, ReviewItem
from tracker.domain.noise_return import (
    PersonRuling,
    ThreadRuling,
    person_ruled_out_by_assistant,
    thread_comes_back,
)
from tracker.repositories import Repositories
from tracker.services.collection.models import RawConversation
from tracker.shared.logging import get_logger

_log = get_logger(__name__)


def thread_returns(
    raw: RawConversation,
    stored: Conversation | None,
    known: dict[tuple[UUID, str], Message],
) -> bool:
    """Say whether the owner's new message sends a dropped thread back to be judged.

    Args:
        raw: The collected thread.
        stored: The row already stored for the thread, when there is one.
        known: The stored messages, by thread and source identifier.

    Returns:
        ``True`` when the assistant had dropped the thread and the owner has
        written in it since.
    """
    if stored is None:
        return False
    return thread_comes_back(
        _ruling_of(stored),
        owner_wrote_again=_owner_wrote_again(raw, stored, known),
    )


def _ruling_of(conversation: Conversation) -> ThreadRuling:
    """Describe a stored thread for the rules."""
    return ThreadRuling(conversation.relevance, conversation.relevance_decided_by)


def _owner_wrote_again(
    raw: RawConversation,
    stored: Conversation,
    known: dict[tuple[UUID, str], Message],
) -> bool:
    """Say whether a collected thread holds an owner message the database lacks.

    A message counts as new when its identifier is not stored and it is later
    than the owner's latest stored message: a late-found older message from
    the owner is not news.

    Args:
        raw: The collected thread.
        stored: The row already stored for the thread.
        known: The stored messages, by thread and source identifier.

    Returns:
        ``True`` when the owner wrote something that was not stored before.
    """
    latest = stored.last_outbound_at
    return any(
        message.direction is Direction.OUTBOUND
        and (stored.id, message.source_message_id) not in known
        and (latest is None or message.sent_at > latest)
        for message in raw.messages
    )


class NoiseReturn:
    """Puts people the assistant dropped back to "unsure" when news arrives."""

    def __init__(self, repositories: Repositories) -> None:
        """Bind the service to the repositories it reads and writes.

        Args:
            repositories: The repository container.
        """
        self._repositories = repositories

    def restore_people(self, person_ids: Collection[UUID]) -> int:
        """Send every hidden person the assistant is behind back to "unsure".

        Must run before the new threads are stored, so the rules see the
        threads as the assistant left them.

        Args:
            person_ids: The people who have news: the owner wrote to them, or
                they started a new conversation.

        Returns:
            How many people were changed.
        """
        hidden = [
            person
            for person in self._repositories.people.list_by_ids(sorted(person_ids))
            if person.relevance is Relevance.NOISE
        ]
        if not hidden:
            return 0
        evidence = self._evidence(hidden)
        restored = [
            person for person in hidden if person_ruled_out_by_assistant(evidence[person.id])
        ]
        self._repositories.people.bulk_upsert(
            [person.model_copy(update={"relevance": Relevance.UNSURE}) for person in restored]
        )
        if restored:
            _log.info("people_returned_from_noise", people=len(restored))
        return len(restored)

    def _evidence(self, hidden: list[Person]) -> dict[UUID, PersonRuling]:
        """Read what shows who hid each person, in three requests for all of them."""
        ids = [person.id for person in hidden]
        threads: dict[UUID, list[ThreadRuling]] = defaultdict(list)
        for conversation in self._repositories.conversations.list_for_people(ids):
            if conversation.person_id is not None:
                threads[conversation.person_id].append(_ruling_of(conversation))
        answered = _people_with_answers(self._repositories.review_items.list_for_people(ids))
        corrected = {
            item.person_id for item in self._repositories.person_overrides.list_for_people(ids)
        }
        return {
            person.id: PersonRuling(
                relevance=person.relevance,
                threads=tuple(threads[person.id]),
                owner_answered=person.id in answered,
                owner_corrected=person.id in corrected,
            )
            for person in hidden
        }


def _people_with_answers(items: Iterable[ReviewItem]) -> set[UUID]:
    """The people the owner answered a relevance question about."""
    return {
        item.person_id
        for item in items
        if item.kind is ReviewKind.RELEVANCE and item.answer is not None and item.person_id
    }
