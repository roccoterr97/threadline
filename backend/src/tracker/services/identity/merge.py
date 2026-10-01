"""Joining two records that turned out to be one person.

The matcher never merges on a guess: when an e-mail address and a name could
belong to the same human it asks, and the answer waits in the review list.
This is what happens once the owner answers **yes**.

Until the answer is acted on, the same person keeps two rows on the dashboard
with two different statuses, which is exactly the confusion the question was
raised to remove.

Which record survives is not arbitrary: the one carrying a real name wins over
the one named after an address, because that is the name the owner will
recognise. Everything the other record holds — its identities, its threads, and
its correction if the survivor has none — moves across before it is removed.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from tracker.domain.enums import ReviewAnswer, ReviewKind
from tracker.domain.identity import is_shown_as_address
from tracker.domain.models import Person, ReviewItem
from tracker.repositories import Repositories
from tracker.shared.logging import get_logger

_log = get_logger(__name__)


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
        report = MergeReport()
        for item in self._confirmed_pairs():
            report = self._apply_one(item, report)
        report = replace(report, questions_closed=self._close_settled_questions())
        _log.info(
            "people_merged",
            merged=report.merged,
            identities_moved=report.identities_moved,
            conversations_moved=report.conversations_moved,
            skipped=report.skipped,
            questions_closed=report.questions_closed,
        )
        return report

    def _close_settled_questions(self) -> int:
        """Remove unanswered "same person?" questions that name one record twice.

        A merge points every question at the surviving record. One still
        waiting for an answer then asks whether somebody is the same person as
        themselves, and would sit in the review list for ever. It is removed
        rather than marked "yes", because the owner never gave that answer;
        answered ones stay as the record of the owner's decision.
        """
        settled = [
            item.id
            for item in self._repositories.review_items.list_by_kind(ReviewKind.SAME_PERSON)
            if item.answer is None
            and item.person_id is not None
            and item.person_id == item.other_person_id
        ]
        return self._repositories.review_items.delete_by_ids(settled)

    def _confirmed_pairs(self) -> list[ReviewItem]:
        """The answered "same person?" questions still naming two records."""
        return [
            item
            for item in self._repositories.review_items.list_by_kind(ReviewKind.SAME_PERSON)
            if item.answer is ReviewAnswer.YES
            and item.person_id is not None
            and item.other_person_id is not None
        ]

    def _apply_one(self, item: ReviewItem, report: MergeReport) -> MergeReport:
        """Merge the two people one answered question names."""
        people = self._repositories.people.list_by_ids(
            [person_id for person_id in (item.person_id, item.other_person_id) if person_id]
        )
        if len(people) != 2:  # noqa: PLR2004 - one of them is already gone
            return MergeReport(
                report.merged,
                report.identities_moved,
                report.conversations_moved,
                report.skipped + 1,
            )
        identities, conversations = self.join(*_order(people[0], people[1]))
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
                correction and questions move across before it is removed.

        Returns:
            How many identities and how many threads moved.
        """
        identities = self._move_identities(survivor, absorbed)
        conversations = self._move_conversations(survivor, absorbed)
        self._move_state_and_correction(survivor, absorbed)
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
        """
        if not self._repositories.person_states.list_for_people([survivor.id]):
            for state in self._repositories.person_states.list_for_people([absorbed.id]):
                self._repositories.person_states.bulk_upsert(
                    [state.model_copy(update={"person_id": survivor.id})]
                )
        if not self._repositories.person_overrides.list_for_people([survivor.id]):
            for override in self._repositories.person_overrides.list_for_people([absorbed.id]):
                self._repositories.person_overrides.bulk_upsert(
                    [override.model_copy(update={"person_id": survivor.id})]
                )

    def _repoint_questions(self, survivor: Person, absorbed: Person) -> None:
        """Keep the owner's answers by moving them onto the surviving record.

        A question still naming the absorbed record would be removed with it,
        and the owner's answer would be lost. A settled "same person?" ends up
        naming the survivor on both sides: the database requires the question
        to name a second person, and a question about one record and itself is
        exactly what a finished merge means. A later run sees one person where
        it expects two and leaves it alone.
        """
        items = self._repositories.review_items.list_for_people([absorbed.id])
        if not items:
            return
        self._repositories.review_items.bulk_upsert(
            [
                item.model_copy(
                    update={
                        "person_id": survivor.id,
                        "other_person_id": survivor.id
                        if item.other_person_id in (absorbed.id, survivor.id)
                        else item.other_person_id,
                    }
                )
                for item in items
            ]
        )


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
