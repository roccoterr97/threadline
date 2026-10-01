"""A meeting that has taken place, or the owner's "yes", sends a person back to be judged."""

from __future__ import annotations

from pathlib import Path

from tests.assessment_world import (
    make_answer,
    make_message,
    make_person,
    make_state,
    make_thread,
    moment,
    seed,
)
from tracker.domain.enums import Channel, Direction, Relevance, ReviewAnswer
from tracker.domain.models import Conversation, Person, ReviewItem
from tracker.repositories import Repositories
from tracker.schemas.assessment import PersonDossier, parse_batch
from tracker.services.assessment.exporter import AssessmentExporter
from tracker.shared.clock import FixedClock

#: The clock of every test here reads 18 September, 07:00.
ASSESSED = moment(15)


def _meeting(person: Person, *, meeting_day: int) -> Conversation:
    """A calendar thread whose invitation arrived on the 12th."""
    return make_thread(
        person,
        source="meeting-1",
        channel=Channel.CALENDAR,
        relevance=Relevance.RELEVANT,
        last_inbound=moment(12),
        subject="Intro call",
        meeting_at=moment(meeting_day, hour=14),
    )


def _seed_assessed(
    repositories: Repositories,
    person: Person,
    threads: list[Conversation],
    *,
    review_items: list[ReviewItem] | None = None,
) -> None:
    """Seed a person assessed on the 15th, whose threads last moved on the 12th."""
    seed(
        repositories,
        people=[person],
        threads=threads,
        messages=[
            make_message(
                thread,
                direction=Direction.INBOUND,
                sent_at=moment(12),
                body="Invitation",
                source=f"message-{index}",
            )
            for index, thread in enumerate(threads)
        ],
        states=[make_state(person, assessed_through=moment(12), assessed_at=ASSESSED)],
        review_items=review_items,
    )


def _export(repositories: Repositories, clock: FixedClock, tmp_path: Path) -> list[PersonDossier]:
    result = AssessmentExporter(repositories, clock, tmp_path).export()
    if not result.batch_paths:
        return []
    return list(parse_batch(result.batch_paths[0].read_text(encoding="utf-8")).people)


def test_a_meeting_that_took_place_since_the_last_assessment_sends_the_person_back(
    repositories: Repositories,
    clock: FixedClock,
    tmp_path: Path,
) -> None:
    person = make_person()
    _seed_assessed(repositories, person, [_meeting(person, meeting_day=17)])

    assert len(_export(repositories, clock, tmp_path)) == 1


def test_a_meeting_still_to_come_does_not_send_the_person_back(
    repositories: Repositories,
    clock: FixedClock,
    tmp_path: Path,
) -> None:
    person = make_person()
    _seed_assessed(repositories, person, [_meeting(person, meeting_day=20)])

    assert _export(repositories, clock, tmp_path) == []


def test_a_meeting_the_last_assessment_already_followed_does_not_send_the_person_back(
    repositories: Repositories,
    clock: FixedClock,
    tmp_path: Path,
) -> None:
    person = make_person()
    _seed_assessed(repositories, person, [_meeting(person, meeting_day=14)])

    assert _export(repositories, clock, tmp_path) == []


def test_a_yes_given_after_the_last_assessment_sends_the_person_back(
    repositories: Repositories,
    clock: FixedClock,
    tmp_path: Path,
) -> None:
    person = make_person()
    thread = make_thread(person, last_inbound=moment(12))
    _seed_assessed(
        repositories,
        person,
        [thread],
        review_items=[make_answer(person, thread, answer=ReviewAnswer.YES, answered_at=moment(17))],
    )

    assert len(_export(repositories, clock, tmp_path)) == 1


def test_a_yes_the_last_assessment_already_saw_changes_nothing(
    repositories: Repositories,
    clock: FixedClock,
    tmp_path: Path,
) -> None:
    person = make_person()
    thread = make_thread(person, last_inbound=moment(12))
    _seed_assessed(
        repositories,
        person,
        [thread],
        review_items=[make_answer(person, thread, answer=ReviewAnswer.YES, answered_at=moment(13))],
    )

    assert _export(repositories, clock, tmp_path) == []


def test_the_dossier_carries_the_start_on_its_own_meeting_only(
    repositories: Repositories,
    clock: FixedClock,
    tmp_path: Path,
) -> None:
    person = make_person()
    chat = make_thread(person, last_inbound=moment(12))
    meeting = _meeting(person, meeting_day=16)
    _seed_assessed(repositories, person, [chat, meeting])

    threads = {
        thread.conversation_id: thread
        for thread in _export(repositories, clock, tmp_path)[0].threads
    }

    assert threads[meeting.id].meeting_at == moment(16, hour=14)
    assert threads[chat.id].meeting_at is None
