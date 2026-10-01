"""The sample set covers the whole contract, and loads and clears cleanly."""

from __future__ import annotations

from collections import Counter
from datetime import date

import pytest

from tests.conftest import FakeSupabaseClient
from tracker.domain.enums import Channel, ContactStatus, Relevance, RunStatus, WaitingOn
from tracker.repositories import Repositories
from tracker.services.sample_data import (
    SAMPLE_DATA_FILE,
    SampleDataService,
    SampleDataSet,
    read_sample_data,
)

#: The day the sample set was written; "overdue" is judged against it.
WRITTEN_ON = date(2026, 9, 18)


@pytest.fixture
def dataset() -> SampleDataSet:
    return read_sample_data()


def test_the_file_ships_with_the_repository() -> None:
    assert SAMPLE_DATA_FILE.is_file()


def test_there_are_twelve_people_and_all_are_relevant(dataset: SampleDataSet) -> None:
    assert len(dataset.people) == 12
    assert all(person.relevance is Relevance.RELEVANT for person in dataset.people)


def test_every_status_appears(dataset: SampleDataSet) -> None:
    statuses = {state.status for state in dataset.person_states}

    assert statuses == set(ContactStatus)


def test_every_waiting_on_value_appears(dataset: SampleDataSet) -> None:
    assert {state.waiting_on for state in dataset.person_states} == set(WaitingOn)


def test_both_identity_channels_appear(dataset: SampleDataSet) -> None:
    """A calendar meeting is matched by e-mail address, so it has no identities of its own."""
    identity_channels = {identity.channel for identity in dataset.person_identities}
    assert identity_channels == {Channel.EMAIL, Channel.LINKEDIN}


def test_some_people_use_one_channel_and_some_use_both(dataset: SampleDataSet) -> None:
    per_person = Counter(identity.person_id for identity in dataset.person_identities)

    assert 1 in per_person.values()
    assert 2 in per_person.values()


def test_at_least_one_follow_up_is_overdue(dataset: SampleDataSet) -> None:
    overdue = [
        state
        for state in dataset.person_states
        if state.due_date is not None
        and state.due_date < WRITTEN_ON
        and state.waiting_on is not WaitingOn.NOBODY
    ]

    assert overdue


def test_two_review_items_are_waiting_for_an_answer(dataset: SampleDataSet) -> None:
    unanswered = [item for item in dataset.review_items if item.answer is None]

    assert len(unanswered) == 2


def test_two_runs_are_recorded_and_one_failed(dataset: SampleDataSet) -> None:
    assert len(dataset.run_logs) == 2
    assert sum(run.status is RunStatus.FAILED for run in dataset.run_logs) == 1


def test_the_failed_step_records_a_code_and_no_message_text(dataset: SampleDataSet) -> None:
    failed = [step for step in dataset.run_step_logs if step.status is RunStatus.FAILED]

    assert len(failed) == 1
    assert failed[0].error_code == "source_auth_failed"


def test_a_thread_judged_noise_keeps_nothing_private(dataset: SampleDataSet) -> None:
    noise = [c for c in dataset.conversations if c.relevance is Relevance.NOISE]

    assert noise
    assert all(conversation.subject is None for conversation in noise)
    noise_ids = {conversation.id for conversation in noise}
    bodies = [m.body for m in dataset.messages if m.conversation_id in noise_ids]
    assert bodies == [None]


def test_every_identifier_is_unique(dataset: SampleDataSet) -> None:
    identifiers = [
        (identity.channel, identity.identifier) for identity in dataset.person_identities
    ]

    assert len(set(identifiers)) == len(identifiers)


def test_loading_writes_every_table(
    dataset: SampleDataSet,
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
) -> None:
    counts = SampleDataService(repositories).load(dataset)

    assert {count.table for count in counts} == set(fake_client.tables)
    assert len(fake_client.tables["people"]) == 12


def test_loading_twice_creates_no_duplicates(
    dataset: SampleDataSet,
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
) -> None:
    service = SampleDataService(repositories)
    service.load(dataset)
    service.load(dataset)

    assert len(fake_client.tables["people"]) == 12
    assert len(fake_client.tables["messages"]) == len(dataset.messages)


def test_clearing_removes_exactly_what_was_loaded(
    dataset: SampleDataSet,
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
) -> None:
    service = SampleDataService(repositories)
    service.load(dataset)

    service.clear(dataset)

    assert all(rows == [] for rows in fake_client.tables.values())


def test_clearing_leaves_other_rows_alone(
    dataset: SampleDataSet,
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
) -> None:
    service = SampleDataService(repositories)
    service.load(dataset)
    real_person = {"id": "99999999-9999-4999-8999-999999999999", "full_name": "Real Person"}
    fake_client.tables["people"].append(real_person)

    service.clear(dataset)

    assert fake_client.tables["people"] == [real_person]


def test_a_missing_file_is_reported(tmp_path: object) -> None:
    from pathlib import Path

    from tracker.shared.errors import ValidationFailedError

    assert isinstance(tmp_path, Path)
    with pytest.raises(ValidationFailedError, match="could not be read"):
        read_sample_data(tmp_path / "absent.json")
