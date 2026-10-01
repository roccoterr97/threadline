"""Pick the people who still need judging and write their dossiers to disk.

A dossier holds names, dates, directions and message text — nothing else. This
module never reads :func:`~tracker.shared.config.get_settings`, so no key, token
or address of the owner's can reach a batch file by accident.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID

from tracker.domain.enums import Direction, Relevance, ReviewAnswer, ReviewKind
from tracker.domain.models import (
    Conversation,
    Message,
    Person,
    PersonOverride,
    PersonState,
    ReviewItem,
)
from tracker.domain.relevance import (
    PersonEvidence,
    PreDecision,
    ThreadEvidence,
    decide_thread,
    exchange_count,
    needs_assessment,
    owner_has_replied,
)
from tracker.repositories import Repositories
from tracker.schemas.assessment import (
    AssessmentBatch,
    DossierAssessment,
    DossierMessage,
    DossierOverride,
    DossierThread,
    PersonDossier,
)
from tracker.shared.clock import Clock
from tracker.shared.constants.assessment import (
    BATCH_DIRECTORY,
    BATCH_SIZE,
    MAX_MESSAGE_CHARACTERS,
    MESSAGES_PER_THREAD,
)
from tracker.shared.constants.pagination import DEFAULT_PAGE_SIZE
from tracker.shared.logging import get_logger

#: Relevance values a person may still be sent to the assistant with.
_CANDIDATE_RELEVANCE = (Relevance.RELEVANT, Relevance.UNSURE)

_ANSWER_SENTENCES = {
    ReviewAnswer.YES: "The owner confirmed this person is relevant to what they are tracking.",
    ReviewAnswer.NO: "The owner said this person is not relevant to what they are tracking.",
}

_log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ExportResult:
    """What one export produced."""

    batch_paths: tuple[Path, ...]
    people: int


@dataclass(frozen=True, slots=True)
class _PersonFacts:
    """Everything one person's dossier is built from."""

    person: Person
    threads: tuple[Conversation, ...]
    messages: dict[UUID, tuple[Message, ...]]
    state: PersonState | None
    override: PersonOverride | None
    review_items: tuple[ReviewItem, ...]


class AssessmentExporter:
    """Writes the batch files the assistant reads."""

    def __init__(
        self,
        repositories: Repositories,
        clock: Clock,
        directory: Path = BATCH_DIRECTORY,
    ) -> None:
        """Bind the exporter to its dependencies.

        Args:
            repositories: The repository container.
            clock: The clock that stamps the batch and names its file.
            directory: Where batch files are written.
        """
        self._repositories = repositories
        self._clock = clock
        self._directory = directory

    def export(self, *, limit: int | None = None) -> ExportResult:
        """Write one batch file per group of people still needing a verdict.

        Args:
            limit: At most this many people. ``None`` exports everyone who
                qualifies.

        Returns:
            The files written and how many people they describe.
        """
        due = self._people_due()
        if limit is not None:
            due = due[:limit]
        paths = self._write_batches([_build_dossier(facts) for facts in due])
        _log.info("assessment_exported", people=len(due), batches=len(paths))
        return ExportResult(batch_paths=paths, people=len(due))

    def pending_people(self) -> int:
        """Count the people who would be exported right now.

        Returns:
            How many people still need a verdict.
        """
        return len(self._people_due())

    def _people_due(self) -> list[_PersonFacts]:
        """Read every candidate and keep those the rules cannot settle alone."""
        now = self._clock.now()
        return [facts for facts in self._collect_facts() if _still_needs_assessment(facts, now)]

    def _collect_facts(self) -> tuple[_PersonFacts, ...]:
        """Read every candidate person and everything known about them.

        Five requests in total, whatever the number of people: the assessment
        must not grow a query per person.

        Returns:
            One entry per candidate, threads already stripped of settled noise.
        """
        people = self._candidates()
        person_ids = [person.id for person in people]
        if not person_ids:
            return ()
        conversations = _group(
            self._repositories.conversations.list_for_people(person_ids),
            lambda conversation: conversation.person_id,
        )
        review_items = _group(
            self._repositories.review_items.list_for_people(person_ids),
            lambda item: item.person_id,
        )
        messages = _group(
            self._repositories.messages.list_for_conversations(
                [conversation.id for group in conversations.values() for conversation in group]
            ),
            lambda message: message.conversation_id,
        )
        states = {
            state.person_id: state
            for state in self._repositories.person_states.list_for_people(person_ids)
        }
        overrides = {
            override.person_id: override
            for override in self._repositories.person_overrides.list_for_people(person_ids)
        }
        return tuple(
            _assemble(
                person=person,
                conversations=conversations.get(person.id, []),
                messages=messages,
                state=states.get(person.id),
                override=overrides.get(person.id),
                review_items=review_items.get(person.id, []),
            )
            for person in people
        )

    def _candidates(self) -> tuple[Person, ...]:
        """List everyone who has not been ruled out as noise."""
        return tuple(
            person for relevance in _CANDIDATE_RELEVANCE for person in self._all_pages(relevance)
        )

    def _all_pages(self, relevance: Relevance) -> Iterator[Person]:
        """Read every page of people with one relevance value."""
        offset = 0
        while True:
            page = self._repositories.people.list_by_relevance(
                relevance, limit=DEFAULT_PAGE_SIZE, offset=offset
            )
            yield from page
            if len(page) < DEFAULT_PAGE_SIZE:
                return
            offset += DEFAULT_PAGE_SIZE

    def _write_batches(self, dossiers: Sequence[PersonDossier]) -> tuple[Path, ...]:
        """Write the dossiers to disk, :data:`BATCH_SIZE` people per file."""
        if not dossiers:
            return ()
        self._directory.mkdir(parents=True, exist_ok=True)
        generated_at = self._clock.now()
        stamp = generated_at.strftime("%Y%m%d-%H%M%S")
        paths: list[Path] = []
        for index, start in enumerate(range(0, len(dossiers), BATCH_SIZE), start=1):
            batch = AssessmentBatch(
                batch_id=f"batch-{stamp}-{index:02d}",
                generated_at=generated_at,
                people=tuple(dossiers[start : start + BATCH_SIZE]),
            )
            path = self._directory / f"{batch.batch_id}.json"
            path.write_text(batch.model_dump_json(indent=2), encoding="utf-8")
            paths.append(path)
        return tuple(paths)


def _assemble(
    *,
    person: Person,
    conversations: Sequence[Conversation],
    messages: dict[UUID, list[Message]],
    state: PersonState | None,
    override: PersonOverride | None,
    review_items: Sequence[ReviewItem],
) -> _PersonFacts:
    """Gather one person's records, dropping the threads already settled as noise."""
    answers = _answers_by_conversation(review_items)
    live = tuple(
        conversation
        for conversation in conversations
        if decide_thread(
            ThreadEvidence(
                relevance=conversation.relevance,
                decided_by=conversation.relevance_decided_by,
                owner_answer=answers.get(conversation.id),
            )
        )
        is not PreDecision.SETTLED_NOISE
    )
    return _PersonFacts(
        person=person,
        threads=live,
        messages={
            conversation.id: tuple(sorted(messages.get(conversation.id, []), key=_sent_at))
            for conversation in live
        },
        state=state,
        override=override,
        review_items=tuple(review_items),
    )


def _still_needs_assessment(facts: _PersonFacts, now: datetime) -> bool:
    """Apply the rules that decide whether a person goes to the assistant.

    Args:
        facts: Everything known about the person.
        now: The current moment, which decides which meetings are over.
    """
    evidence = PersonEvidence(
        relevance=facts.person.relevance,
        answered_not_relevant=_answered_not_relevant(facts.review_items),
        last_message_at=_latest(thread.last_message_at for thread in facts.threads),
        assessed_through=facts.state.assessed_through if facts.state else None,
        assessed_at=facts.state.assessed_at if facts.state else None,
        last_meeting_started_at=_latest(
            thread.meeting_at
            for thread in facts.threads
            if thread.meeting_at is not None and thread.meeting_at <= now
        ),
        last_confirmed_at=_latest(
            item.answered_at for item in facts.review_items if _is_confirmation(item)
        ),
    )
    return bool(facts.threads) and needs_assessment(evidence)


def _build_dossier(facts: _PersonFacts) -> PersonDossier:
    """Describe one person for the assistant."""
    return PersonDossier(
        person_id=facts.person.id,
        full_name=facts.person.full_name,
        known_person_type=facts.person.person_type,
        known_role_title=facts.person.role_title,
        owner_answers=_answer_sentences(facts.review_items),
        owner_override=_to_dossier_override(facts.override),
        previous_assessment=_to_dossier_assessment(facts.state),
        threads=tuple(_build_thread(facts, thread) for thread in facts.threads),
    )


def _build_thread(facts: _PersonFacts, conversation: Conversation) -> DossierThread:
    """Describe one thread, oldest message first and the newest ones kept."""
    messages = facts.messages.get(conversation.id, ())
    evidence = ThreadEvidence(
        relevance=conversation.relevance,
        decided_by=conversation.relevance_decided_by,
        inbound_count=sum(1 for message in messages if message.direction is Direction.INBOUND),
        outbound_count=sum(1 for message in messages if message.direction is Direction.OUTBOUND),
    )
    return DossierThread(
        conversation_id=conversation.id,
        channel=conversation.channel,
        subject=conversation.subject,
        relevance=conversation.relevance,
        owner_has_replied=owner_has_replied(evidence),
        exchange_count=exchange_count(evidence),
        meeting_at=conversation.meeting_at,
        messages=tuple(
            DossierMessage(
                sent_at=message.sent_at,
                direction=message.direction,
                text=_shorten(message.body),
            )
            for message in messages[-MESSAGES_PER_THREAD:]
        ),
    )


def _sent_at(message: Message) -> datetime:
    """Sort key putting the oldest message first."""
    return message.sent_at


def _group[ItemT](
    items: Iterable[ItemT],
    key: Callable[[ItemT], UUID | None],
) -> dict[UUID, list[ItemT]]:
    """Bucket items by a key, dropping the ones whose key is missing."""
    grouped: dict[UUID, list[ItemT]] = defaultdict(list)
    for item in items:
        identifier = key(item)
        if identifier is not None:
            grouped[identifier].append(item)
    return grouped


def _latest(moments: Iterable[datetime | None]) -> datetime | None:
    """Return the most recent moment, or ``None`` when there is none."""
    known = [moment for moment in moments if moment is not None]
    return max(known) if known else None


def _shorten(text: str | None) -> str | None:
    """Cut a message body down to the length a dossier carries."""
    if text is None:
        return None
    return text[:MAX_MESSAGE_CHARACTERS]


def _answers_by_conversation(items: Iterable[ReviewItem]) -> dict[UUID, ReviewAnswer]:
    """Map each answered relevance question to the thread it was about."""
    return {
        item.conversation_id: item.answer
        for item in items
        if item.kind is ReviewKind.RELEVANCE
        and item.conversation_id is not None
        and item.answer is not None
    }


def _answered_not_relevant(items: Iterable[ReviewItem]) -> bool:
    """Say whether the owner has already ruled this person out."""
    return any(
        item.kind is ReviewKind.RELEVANCE and item.answer is ReviewAnswer.NO for item in items
    )


def _is_confirmation(item: ReviewItem) -> bool:
    """Say whether a review item is the owner saying "yes, part of my search"."""
    return item.kind is ReviewKind.RELEVANCE and item.answer is ReviewAnswer.YES


def _answer_sentences(items: Iterable[ReviewItem]) -> tuple[str, ...]:
    """Turn the owner's answers into plain sentences the assistant can read."""
    answers = {item.answer for item in items if item.answer is not None}
    return tuple(_ANSWER_SENTENCES[answer] for answer in sorted(answers))


def _to_dossier_override(override: PersonOverride | None) -> DossierOverride | None:
    """Copy an override into the dossier's shape."""
    if override is None:
        return None
    return DossierOverride(
        status=override.status,
        waiting_on=override.waiting_on,
        next_action=override.next_action,
        due_date=override.due_date,
        person_type=override.person_type,
        note=override.note,
    )


def _to_dossier_assessment(state: PersonState | None) -> DossierAssessment | None:
    """Copy the previous assessment into the dossier's shape."""
    if state is None:
        return None
    return DossierAssessment(
        status=state.status,
        waiting_on=state.waiting_on,
        next_action=state.next_action,
        due_date=state.due_date,
        summary=state.summary,
        signal=state.signal,
        confidence=state.confidence,
        assessed_at=state.assessed_at,
    )
