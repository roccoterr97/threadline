"""The sample set covers the whole contract, and loads and clears cleanly."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

import pytest
from typer.testing import CliRunner

from tests.conftest import FakeSupabaseClient, as_client
from tests.summary_world import overview_rows, sample_data
from tracker.cli.main import build_cli
from tracker.domain.enums import Channel, ContactStatus, Relevance, RunStatus, WaitingOn
from tracker.repositories import Repositories
from tracker.services.sample_data import (
    SAMPLE_DATA_FILE,
    SampleDataService,
    SampleDataSet,
    read_sample_data,
)
from tracker.shared.clock import FixedClock
from tracker.shared.config import Settings

#: The day the sample set was written; "overdue" is judged against it.
WRITTEN_ON = date(2026, 9, 18)

#: A moment on that day, for loading the set exactly as the file holds it.
WRITTEN_AT = datetime(2026, 9, 18, 7, 0, tzinfo=UTC)


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
    counts = SampleDataService(repositories, FixedClock(WRITTEN_AT)).load(dataset)

    assert {count.table for count in counts} == set(fake_client.tables)
    assert len(fake_client.tables["people"]) == 12


def test_loading_twice_creates_no_duplicates(
    dataset: SampleDataSet,
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
) -> None:
    service = SampleDataService(repositories, FixedClock(WRITTEN_AT))
    service.load(dataset)
    service.load(dataset)

    assert len(fake_client.tables["people"]) == 12
    assert len(fake_client.tables["messages"]) == len(dataset.messages)


def test_clearing_removes_exactly_what_was_loaded(
    dataset: SampleDataSet,
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
) -> None:
    service = SampleDataService(repositories, FixedClock(WRITTEN_AT))
    service.load(dataset)

    service.clear(dataset)

    assert all(rows == [] for rows in fake_client.tables.values())


def test_clearing_leaves_other_rows_alone(
    dataset: SampleDataSet,
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
) -> None:
    service = SampleDataService(repositories, FixedClock(WRITTEN_AT))
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


# --- loading moves the sample's dates to the owner's today ----------------------

#: A later day to load the sample on: 16 days after it was written.
LOADED_ON = datetime(2026, 10, 4, 7, 0, tzinfo=UTC)


def _counts_on(tables: dict[str, list[dict[str, object]]], today: date) -> tuple[int, int]:
    """How many people are overdue and how many are due a chase, seen on ``today``."""
    rows = overview_rows(cast("dict[str, list[dict[str, Any]]]", tables), today=today)
    return sum(row["is_overdue"] for row in rows), sum(row["is_chase_due"] for row in rows)


def test_loaded_later_the_sample_is_exactly_as_overdue_as_on_the_day_it_was_written(
    dataset: SampleDataSet, repositories: Repositories, fake_client: FakeSupabaseClient
) -> None:
    SampleDataService(repositories, FixedClock(LOADED_ON)).load(dataset)

    later = _counts_on(fake_client.tables, LOADED_ON.date())

    assert later == _counts_on(sample_data(), WRITTEN_ON)
    assert later != _counts_on(sample_data(), LOADED_ON.date())  # unmoved, it would look stale


def test_loading_moves_every_date_by_whole_days(
    dataset: SampleDataSet, repositories: Repositories, fake_client: FakeSupabaseClient
) -> None:
    SampleDataService(repositories, FixedClock(LOADED_ON)).load(dataset)

    started = sorted(str(row["started_at"]) for row in fake_client.tables["run_logs"])
    loaded = _due_dates(fake_client.tables["person_states"])
    written = _due_dates(sample_data()["person_states"])

    assert [moment[:19] for moment in started] == ["2026-10-03T05:00:00", "2026-10-04T05:00:00"]
    assert written
    assert loaded == {key: day + timedelta(days=16) for key, day in written.items()}


def _due_dates(rows: list[dict[str, object]]) -> dict[str, date]:
    """Each person's follow-up date, for the people who have one."""
    return {
        str(row["person_id"]): date.fromisoformat(str(row["due_date"]))
        for row in rows
        if row.get("due_date") is not None
    }


def test_the_day_moved_to_is_the_owners_today(
    dataset: SampleDataSet, repositories: Repositories, fake_client: FakeSupabaseClient
) -> None:
    """Late evening in UTC is already the next day in Tokyo."""
    evening = datetime(2026, 9, 18, 22, 0, tzinfo=UTC)
    SampleDataService(repositories, FixedClock(evening, ZoneInfo("Asia/Tokyo"))).load(dataset)

    started = sorted(str(row["started_at"]) for row in fake_client.tables["run_logs"])

    assert started[-1].startswith("2026-09-19T05:00:00")


def test_loading_leaves_the_file_and_the_set_it_read_unmoved(
    dataset: SampleDataSet, repositories: Repositories
) -> None:
    before = dataset.model_dump()

    SampleDataService(repositories, FixedClock(LOADED_ON)).load(dataset)

    assert dataset.model_dump() == before
    assert read_sample_data().run_logs[-1].started_at.date() == WRITTEN_ON


def test_the_command_loads_the_sample_dated_as_of_today(
    monkeypatch: pytest.MonkeyPatch, fake_client: FakeSupabaseClient, settings: Settings
) -> None:
    monkeypatch.setattr(
        "tracker.cli.commands.system.create_database_client",
        lambda _settings: as_client(fake_client),
    )
    monkeypatch.setattr(
        "tracker.cli.commands.system.SystemClock",
        lambda zone=UTC: FixedClock(LOADED_ON, zone),
    )

    result = CliRunner().invoke(build_cli(), ["sample", "load"])

    assert result.exit_code == 0
    assert settings.supabase_url
    assert _counts_on(fake_client.tables, LOADED_ON.date()) == _counts_on(sample_data(), WRITTEN_ON)
