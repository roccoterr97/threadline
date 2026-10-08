"""Joining two records that turned out to be one person.

The matcher never merges on a guess: when an e-mail address and a name could
belong to the same human it asks, and the answer waits in the review list.
This is what happens once the owner answers **yes**.

Until the answer is acted on, the same person keeps two rows on the dashboard
with two different statuses, which is exactly the confusion the question was
raised to remove.

Which record survives is not arbitrary: the one carrying a real name wins over
the one named after an address, because that is the name the owner will
recognise. Everything the other record holds — its identities, its threads, the
owner's notes, and its correction if the survivor has none — moves across
before it is removed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from uuid import UUID, uuid4

from tracker.domain.enums import ReviewAnswer, ReviewKind
from tracker.domain.identity import is_shown_as_address
from tracker.domain.models import Person, PersonOverride, PersonState, ReviewItem
from tracker.repositories import Repositories
from tracker.shared.logging import get_logger

_log = get_logger(__name__)

# A "same person?" question is about two different records.
_PAIR_SIZE = 2


@dataclass(frozen=True, slots=True)
class MergeReport:
    """What a run of the merger changed."""

    merged: int = 0
    identities_moved: int = 0
    conversations_moved: int = 0
    skipped: int = 0
    questions_closed: int = 0


class PersonMerger:
    """Applies the owner's "yes, same person" answers."""

    def __init__(self, repositories: Repositories) -> None:
        """Bind the merger to the database.

        Args:
            repositories: The repository container.
        """
        self._repositories = repositories

    def apply_answers(self) -> MergeReport:
        """Merge every pair the owner has confirmed.

        Returns:
            What was changed.
        """
        questions = self._same_person_questions()
        report = MergeReport()
        merged_into: dict[UUID, UUID] = {}
        for item in _confirmed_pairs(questions):
            report = self._apply_one(item, merged_into, report)
        if report.merged:
            # A merge points questions at the record that survived, so what
            # was read before it no longer says which ones name one record twice.
            questions = self._same_person_questions()
        report = replace(report, questions_closed=self._close_settled_questions(questions))
        _log.info(
            "people_merged",
            merged=report.merged,
            identities_moved=report.identities_moved,
            conversations_moved=report.conversations_moved,
            skipped=report.skipped,
            questions_closed=report.questions_closed,
        )
        return report

    def _same_person_questions(self) -> list[ReviewItem]:
        """Every "same person?" question, answered or not, as stored right now."""
        return self._repositories.review_items.list_by_kind(ReviewKind.SAME_PERSON)

    def _close_settled_questions(self, questions: Sequence[ReviewItem]) -> int:
        """Remove unanswered "same person?" questions a merge made pointless.

        A merge points every question at the surviving record. One still
        waiting for an answer then either asks whether somebody is the same
        person as themselves, or repeats a question about the same two records
        that is already on file. Either would sit in the review list for ever,
        or ask the owner twice. It is removed rather than marked "yes", because
        the owner never gave that answer; answered ones stay as the record of
        the owner's decision.

        Args:
            questions: The "same person?" questions, read after the last merge.

        Returns:
            How many questions were removed.
        """
        # Answered questions first, so a repeat is the unanswered copy.
        ordered = sorted(questions, key=lambda item: item.answer is None)
        seen: set[frozenset[UUID]] = set()
        pointless: list[UUID] = []
        for item in ordered:
            pair = frozenset(person for person in (item.person_id, item.other_person_id) if person)
            if item.answer is None and (len(pair) < _PAIR_SIZE or pair in seen):
                pointless.append(item.id)
            seen.add(pair)
        return self._repositories.review_items.delete_by_ids(pointless)

    def _apply_one(
        self,
        item: ReviewItem,
        merged_into: dict[UUID, UUID],
        report: MergeReport,
    ) -> MergeReport:
        """Merge the two people one answered question names.

        The questions were read before this run merged anything, so a record
        an earlier answer absorbed is followed to the record it became: "b is
        a" and then "c is b" must end with all three as one.

        Args:
            item: The answered question.
            merged_into: Absorbed record -> survivor, for merges made this run.
                Updated with the merge made here.
            report: The tally so far.

        Returns:
            The tally including this question.
        """
        wanted = {
            _current(person_id, merged_into)
            for person_id in (item.person_id, item.other_person_id)
            if person_id
        }
        if len(wanted) < 2:  # noqa: PLR2004 - a pair names two records
            # An earlier merge left the question naming the survivor twice.
            # Every answer ever given stays in the list, so asking the
            # database about each of them again would cost one request per
            # old answer, every day, to learn nothing.
            return replace(report, skipped=report.skipped + 1)
        people = self._repositories.people.list_by_ids(list(wanted))
        if len(people) != 2:  # noqa: PLR2004 - one of them is already gone
            return MergeReport(
                report.merged,
                report.identities_moved,
                report.conversations_moved,
                report.skipped + 1,
            )
        survivor, absorbed = _order(people[0], people[1])
        identities, conversations = self.join(survivor, absorbed)
        merged_into[absorbed.id] = survivor.id
        return MergeReport(
            report.merged + 1,
            report.identities_moved + identities,
            report.conversations_moved + conversations,
            report.skipped,
        )

    def join(self, survivor: Person, absorbed: Person) -> tuple[int, int]:
        """Fold one record into another; the survivor keeps its name.

        Args:
            survivor: The record that stays.
            absorbed: The record whose addresses, threads, assessment,
                correction, notes and questions move across before it is
                removed.

        Returns:
            How many identities and how many threads moved.
        """
        identities = self._move_identities(survivor, absorbed)
        conversations = self._move_conversations(survivor, absorbed)
        self._move_state_and_correction(survivor, absorbed)
        self._move_notes(survivor, absorbed)
        self._repoint_questions(survivor, absorbed)
        self._repositories.people.delete_by_ids([absorbed.id])
        _log.info("person_merged", kept=str(survivor.id), removed=str(absorbed.id))
        return identities, conversations

    def _move_identities(self, survivor: Person, absorbed: Person) -> int:
        """Point the absorbed record's addresses and profiles at the survivor."""
        identities = self._repositories.person_identities.list_for_person(absorbed.id)
        if not identities:
            return 0
        self._repositories.person_identities.bulk_upsert(
            [identity.model_copy(update={"person_id": survivor.id}) for identity in identities]
        )
        return len(identities)

    def _move_conversations(self, survivor: Person, absorbed: Person) -> int:
        """Point the absorbed record's threads at the survivor.

        This must happen before the record is removed: the database sets a
        thread's person to nothing when its person disappears, which would
        orphan the conversation instead of moving it.
        """
        threads = self._repositories.conversations.list_for_person(absorbed.id)
        if not threads:
            return 0
        self._repositories.conversations.bulk_upsert(
            [thread.model_copy(update={"person_id": survivor.id}) for thread in threads]
        )
        return len(threads)

    def _move_state_and_correction(self, survivor: Person, absorbed: Person) -> None:
        """Keep the survivor's assessment and correction, or take the other's.

        Only one of each may exist per person, so nothing is overwritten: the
        absorbed record's values are taken only where the survivor has none.

        The copy gets a new primary key. The absorbed record's own row still
        exists at this point (the database removes it only when the record
        itself goes, at the end of :meth:`join`), so reusing its key would
        collide with it.
        """
        if not self._repositories.person_states.list_for_people([survivor.id]):
            states = self._repositories.person_states.list_for_people([absorbed.id])
            self._repositories.person_states.bulk_upsert(
                [_moved_to(state, survivor) for state in states]
            )
        if not self._repositories.person_overrides.list_for_people([survivor.id]):
            overrides = self._repositories.person_overrides.list_for_people([absorbed.id])
            self._repositories.person_overrides.bulk_upsert(
                [_moved_to(override, survivor) for override in overrides]
            )

    def _move_notes(self, survivor: Person, absorbed: Person) -> None:
        """Give the survivor the notes the owner typed on the absorbed record.

        A person can have any number of notes, so every one of them moves and
        the survivor keeps its own. This must happen before the record is
        removed: the database deletes a person's notes with the person.
        """
        self._repositories.person_notes.move_to_person(absorbed.id, survivor.id)

    def _repoint_questions(self, survivor: Person, absorbed: Person) -> None:
        """Keep the owner's answers by moving them onto the surviving record.

        A question still naming the absorbed record, on either side, would be
        removed with it, and the owner's answer would be lost. A settled "same person?" ends up
        naming the survivor on both sides: the database requires the question
        to name a second person, and a question about one record and itself is
        exactly what a finished merge means. A later run sees one record
        named twice and leaves it alone, without asking the database about it.
        """
        items = self._repositories.review_items.list_naming_people([absorbed.id])
        if not items:
            return
        self._repositories.review_items.bulk_upsert(
            [
                item.model_copy(
                    update={
                        "person_id": _swap(item.person_id, absorbed, survivor),
                        "other_person_id": _swap(item.other_person_id, absorbed, survivor),
                    }
                )
                for item in items
            ]
        )


def _swap(person_id: UUID | None, absorbed: Person, survivor: Person) -> UUID | None:
    """Replace the absorbed record's identifier with the survivor's."""
    return survivor.id if person_id == absorbed.id else person_id


def _current(person_id: UUID, merged_into: dict[UUID, UUID]) -> UUID:
    """Follow a record through the merges made this run to the one that holds it now."""
    while person_id in merged_into:
        person_id = merged_into[person_id]
    return person_id


def _moved_to[RowT: (PersonState, PersonOverride)](row: RowT, survivor: Person) -> RowT:
    """Copy one per-person row onto the survivor under a fresh primary key."""
    return row.model_copy(update={"id": uuid4(), "person_id": survivor.id})


def _confirmed_pairs(questions: Sequence[ReviewItem]) -> list[ReviewItem]:
    """The "same person?" questions the owner answered yes to.

    Args:
        questions: Every "same person?" question.

    Returns:
        The confirmed ones, including those an earlier run already acted on.
    """
    return [
        item
        for item in questions
        if item.answer is ReviewAnswer.YES
        and item.person_id is not None
        and item.other_person_id is not None
    ]


def _order(first: Person, second: Person) -> tuple[Person, Person]:
    """Decide which record survives a merge.

    A record showing a real name beats one named after an e-mail address:
    that is the name the owner recognises. Otherwise the older record wins, so
    the outcome does not depend on the order rows came back in.

    Args:
        first: One of the two records.
        second: The other.

    Returns:
        The survivor and the record to absorb, in that order.
    """
    first_is_address = is_shown_as_address(first.full_name)
    second_is_address = is_shown_as_address(second.full_name)
    if first_is_address != second_is_address:
        return (second, first) if first_is_address else (first, second)
    if first.created_at and second.created_at and first.created_at != second.created_at:
        return (first, second) if first.created_at < second.created_at else (second, first)
    return (first, second) if str(first.id) < str(second.id) else (second, first)
