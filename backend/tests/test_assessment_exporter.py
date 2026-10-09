"""Export picks the right people and tells the assistant only what it should know."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.assessment_world import (
    make_answer,
    make_message,
    make_override,
    make_person,
    make_state,
    make_thread,
    moment,
    seed,
)
from tests.conftest import TEST_ENCRYPTION_KEY, FakeSupabaseClient, as_client
from tracker.cli.main import build_cli
from tracker.domain.enums import (
    ContactStatus,
    Direction,
    Relevance,
    ReviewAnswer,
    ReviewKind,
    WaitingOn,
)
from tracker.domain.models import ReviewItem
from tracker.repositories import Repositories
from tracker.schemas.assessment import parse_batch
from tracker.services.assessment.exporter import AssessmentExporter
from tracker.shared.clock import FixedClock
from tracker.shared.config import Settings
from tracker.shared.constants.assessment import MESSAGES_PER_THREAD
from tracker.shared.constants.pagination import DEFAULT_PAGE_SIZE


def _exporter(repositories: Repositories, clock: FixedClock, directory: Path) -> AssessmentExporter:
    return AssessmentExporter(repositories, clock, directory)


def test_a_person_never_assessed_is_exported(
    repositories: Repositories,
    clock: FixedClock,
    tmp_path: Path,
) -> None:
    person = make_person()
    thread = make_thread(person, last_inbound=moment(16), last_outbound=moment(14))
    seed(
        repositories,
        people=[person],
        threads=[thread],
        messages=[
            make_message(thread, direction=Direction.OUTBOUND, sent_at=moment(14), body="Hello"),
            make_message(
                thread,
                direction=Direction.INBOUND,
                sent_at=moment(16),
                body="Happy to talk",
                source="message-2",
            ),
        ],
    )

    result = _exporter(repositories, clock, tmp_path).export()

    batch = parse_batch(result.batch_paths[0].read_text(encoding="utf-8"))
    assert result.people == 1
    assert batch.people[0].person_id == person.id
    assert [message.text for message in batch.people[0].threads[0].messages] == [
        "Hello",
        "Happy to talk",
    ]
    assert batch.people[0].threads[0].owner_has_replied is True
    assert batch.people[0].threads[0].exchange_count == 1


def test_the_dossier_says_which_is_the_newest_message_it_covers(
    repositories: Repositories,
    clock: FixedClock,
    tmp_path: Path,
) -> None:
    person = make_person()
    thread = make_thread(person, last_inbound=moment(16), last_outbound=moment(14))
    seed(repositories, people=[person], threads=[thread])

    result = _exporter(repositories, clock, tmp_path).export()

    batch = parse_batch(result.batch_paths[0].read_text(encoding="utf-8"))
    assert batch.people[0].newest_message_at == moment(16)


def test_a_person_the_owner_answered_no_about_is_not_exported(
    repositories: Repositories,
    clock: FixedClock,
    tmp_path: Path,
) -> None:
    person = make_person("Bruno Sala")
    thread = make_thread(person, last_inbound=moment(16))
    seed(
        repositories,
        people=[person],
        threads=[thread],
        messages=[
            make_message(thread, direction=Direction.INBOUND, sent_at=moment(16), body="Newsletter")
        ],
        review_items=[make_answer(person, thread, answer=ReviewAnswer.NO)],
    )

    result = _exporter(repositories, clock, tmp_path).export()

    assert result.people == 0
    assert result.batch_paths == ()


def test_a_person_with_no_new_messages_is_skipped(
    repositories: Repositories,
    clock: FixedClock,
    tmp_path: Path,
) -> None:
    person = make_person()
    thread = make_thread(person, last_inbound=moment(10))
    seed(
        repositories,
        people=[person],
        threads=[thread],
        messages=[make_message(thread, direction=Direction.INBOUND, sent_at=moment(10), body="Hi")],
        states=[make_state(person, assessed_through=moment(10))],
    )

    assert _exporter(repositories, clock, tmp_path).export().people == 0


def test_a_person_with_newer_messages_is_exported_again(
    repositories: Repositories,
    clock: FixedClock,
    tmp_path: Path,
) -> None:
    person = make_person()
    thread = make_thread(person, last_inbound=moment(17))
    seed(
        repositories,
        people=[person],
        threads=[thread],
        messages=[
            make_message(thread, direction=Direction.INBOUND, sent_at=moment(17), body="Any news?")
        ],
        states=[make_state(person, assessed_through=moment(10))],
    )

    assert _exporter(repositories, clock, tmp_path).export().people == 1


def test_a_thread_already_marked_noise_is_left_out(
    repositories: Repositories,
    clock: FixedClock,
    tmp_path: Path,
) -> None:
    person = make_person()
    real = make_thread(person, last_inbound=moment(16))
    junk = make_thread(
        person, source="thread-2", relevance=Relevance.NOISE, last_inbound=moment(17)
    )
    seed(
        repositories,
        people=[person],
        threads=[real, junk],
        messages=[
            make_message(real, direction=Direction.INBOUND, sent_at=moment(16), body="Real"),
            make_message(junk, direction=Direction.INBOUND, sent_at=moment(17), body="Junk"),
        ],
    )

    result = _exporter(repositories, clock, tmp_path).export()

    batch = parse_batch(result.batch_paths[0].read_text(encoding="utf-8"))
    assert [thread.conversation_id for thread in batch.people[0].threads] == [real.id]


def test_only_the_most_recent_messages_of_a_thread_are_sent(
    repositories: Repositories,
    clock: FixedClock,
    tmp_path: Path,
) -> None:
    person = make_person()
    thread = make_thread(person, last_inbound=moment(17))
    messages = [
        make_message(
            thread,
            direction=Direction.INBOUND,
            sent_at=moment(1, hour=index % 24),
            body=f"message {index}",
            source=f"message-{index:03d}",
        )
        for index in range(MESSAGES_PER_THREAD + 5)
    ]
    seed(repositories, people=[person], threads=[thread], messages=messages)

    result = _exporter(repositories, clock, tmp_path).export()

    batch = parse_batch(result.batch_paths[0].read_text(encoding="utf-8"))
    assert len(batch.people[0].threads[0].messages) == MESSAGES_PER_THREAD


def test_the_dossier_carries_the_previous_assessment_and_the_owners_correction(
    repositories: Repositories,
    clock: FixedClock,
    tmp_path: Path,
) -> None:
    person = make_person()
    thread = make_thread(person, last_inbound=moment(17))
    seed(
        repositories,
        people=[person],
        threads=[thread],
        messages=[make_message(thread, direction=Direction.INBOUND, sent_at=moment(17), body="Hi")],
        states=[make_state(person, assessed_through=moment(10))],
        overrides=[
            make_override(
                person,
                status=ContactStatus.IN_PROCESS,
                waiting_on=WaitingOn.ME,
                person_type="network",
            )
        ],
    )

    result = _exporter(repositories, clock, tmp_path).export()

    dossier = parse_batch(result.batch_paths[0].read_text(encoding="utf-8")).people[0]
    assert dossier.previous_assessment is not None
    assert dossier.owner_override is not None
    assert dossier.owner_override.status is ContactStatus.IN_PROCESS


def test_a_batch_file_carries_no_configuration_value(
    repositories: Repositories,
    clock: FixedClock,
    tmp_path: Path,
    valid_environment: None,  # noqa: ARG001 - sets the variables a batch must not leak
) -> None:
    person = make_person()
    thread = make_thread(person, last_inbound=moment(16))
    seed(
        repositories,
        people=[person],
        threads=[thread],
        messages=[
            make_message(thread, direction=Direction.INBOUND, sent_at=moment(16), body="Hello")
        ],
    )

    result = _exporter(repositories, clock, tmp_path).export()

    written = result.batch_paths[0].read_text(encoding="utf-8")
    for secret in (TEST_ENCRYPTION_KEY, "service-key", "anon-key", "supabase"):
        assert secret not in written


def test_people_are_split_into_batches_of_ten(
    repositories: Repositories,
    clock: FixedClock,
    tmp_path: Path,
) -> None:
    people = [make_person(f"Person {index:02d}") for index in range(12)]
    threads = [
        make_thread(person, source=f"thread-{index}", last_inbound=moment(16))
        for index, person in enumerate(people)
    ]
    messages = [
        make_message(
            thread, direction=Direction.INBOUND, sent_at=moment(16), body="Hi", source=f"m-{index}"
        )
        for index, thread in enumerate(threads)
    ]
    seed(repositories, people=people, threads=threads, messages=messages)

    result = _exporter(repositories, clock, tmp_path).export()

    assert result.people == 12
    assert len(result.batch_paths) == 2


def test_the_limit_caps_how_many_people_are_exported(
    repositories: Repositories,
    clock: FixedClock,
    tmp_path: Path,
) -> None:
    people = [make_person(f"Person {index:02d}") for index in range(4)]
    threads = [
        make_thread(person, source=f"thread-{index}", last_inbound=moment(16))
        for index, person in enumerate(people)
    ]
    messages = [
        make_message(
            thread, direction=Direction.INBOUND, sent_at=moment(16), body="Hi", source=f"m-{index}"
        )
        for index, thread in enumerate(threads)
    ]
    seed(repositories, people=people, threads=threads, messages=messages)

    assert _exporter(repositories, clock, tmp_path).export(limit=2).people == 2


def test_pending_people_counts_without_writing_anything(
    repositories: Repositories,
    clock: FixedClock,
    tmp_path: Path,
) -> None:
    person = make_person()
    thread = make_thread(person, last_inbound=moment(16))
    seed(
        repositories,
        people=[person],
        threads=[thread],
        messages=[make_message(thread, direction=Direction.INBOUND, sent_at=moment(16), body="Hi")],
    )

    assert _exporter(repositories, clock, tmp_path).pending_people() == 1
    assert list(tmp_path.iterdir()) == []


def test_ai_status_counts_every_open_question_not_just_the_first_page(
    repositories: Repositories,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_client: FakeSupabaseClient,
    settings: Settings,
) -> None:
    """``tracker ai status`` must not stop counting at one page of questions.

    A plain ``list_unanswered()`` call stops at ``DEFAULT_PAGE_SIZE``, so the
    owner would be told "100 questions" for ever once the list grew past a
    hundred. The summary e-mail already pages through them; the command has to
    agree with it.
    """
    person = make_person()
    seed(
        repositories,
        people=[person],
        review_items=[
            ReviewItem(
                kind=ReviewKind.RELEVANCE,
                person_id=person.id,
                question=f"Is question {index} part of your job search?",
            )
            for index in range(DEFAULT_PAGE_SIZE + 23)
        ],
    )
    monkeypatch.setattr(
        "tracker.cli.commands.ai.create_database_client",
        lambda _settings: as_client(fake_client),
    )

    result = CliRunner().invoke(
        build_cli(),
        ["ai", "status", "--batches", str(tmp_path), "--results", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert f"questions waiting for your answer: {DEFAULT_PAGE_SIZE + 23}" in result.output
