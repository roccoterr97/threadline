"""Every source read at the same time, stored in order, each failure kept apart.

The promise checked here: collecting everything in one step leaves exactly the
rows that collecting the sources one after another leaves, a source that fails
never stops the others, and each source is recorded as its own step of the run.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
import respx
from pydantic import SecretStr
from typer.testing import CliRunner

from tests.conftest import JOB_SEARCH_RULES, TEST_ENCRYPTION_KEY, FakeSupabaseClient, as_client
from tests.test_calendar_collector import CALENDAR_URL, graph_event
from tests.test_collectors import ARCHIVE, MAILBOX, mock_archive, mock_mailbox, rows_of
from tracker.cli.main import build_cli
from tracker.domain.enums import Channel, RunStatus, RunStep, RunTrigger
from tracker.infrastructure.secret_store import MICROSOFT_REFRESH_TOKEN, SecretStore
from tracker.repositories import Repositories, build_repositories
from tracker.services.collection.all_sources import (
    AllSourcesCollector,
    Source,
    SourceOutcome,
    record_outcomes,
)
from tracker.services.collection.calendar_collector import CalendarCollector
from tracker.services.collection.email_collector import EmailCollector
from tracker.services.collection.linkedin_collector import LinkedInCollector
from tracker.services.collection.models import CollectionReport, SaveStep
from tracker.services.runs.run_recorder import RunRecorder
from tracker.shared.clock import FixedClock
from tracker.shared.config import Settings
from tracker.shared.errors import DatabaseUnavailableError, SourceAuthError

EVENTS = [
    graph_event("e-intro"),
    graph_event(
        "e-coffee",
        subject="Coffee",
        organizer=("elodie.martin@acme.example", "Élodie Martin"),
    ),
]


def fake_source(
    channel: Channel,
    step: RunStep,
    diary: list[str],
    *,
    read_fails: bool = False,
    save_fails: bool = False,
    not_configured: bool = False,
) -> Source:
    """A source that notes when it is read and stored instead of doing either."""

    def save() -> CollectionReport:
        diary.append(f"{channel.value} stored")
        if save_fails:
            message = "the database did not answer"
            raise DatabaseUnavailableError(message)
        return CollectionReport(
            channel=channel,
            conversations_found=7,
            conversations_new=2,
            not_configured=not_configured,
        )

    async def read() -> SaveStep:
        diary.append(f"{channel.value} read started")
        await asyncio.sleep(0)
        diary.append(f"{channel.value} read finished")
        if read_fails:
            message = "the key was refused"
            raise SourceAuthError(message)
        return save

    return Source(channel, step, read)


def three_sources(diary: list[str], **email_options: bool) -> tuple[tuple[Source, ...], ...]:
    """LinkedIn on its own; the mailboxes and the calendar sharing a lane."""
    return (
        (fake_source(Channel.LINKEDIN, RunStep.COLLECT_LINKEDIN, diary),),
        (
            fake_source(Channel.EMAIL, RunStep.COLLECT_EMAIL, diary, **email_options),
            fake_source(Channel.CALENDAR, RunStep.COLLECT_CALENDAR, diary),
        ),
    )


def test_lanes_are_read_together_and_a_lane_is_read_in_turn() -> None:
    diary: list[str] = []

    AllSourcesCollector(three_sources(diary)).collect()

    reading = [line for line in diary if "read" in line]
    assert reading[:2] == ["linkedin read started", "email read started"]
    assert reading.index("email read finished") < reading.index("calendar read started")


def test_nothing_is_stored_before_everything_is_read_and_storing_keeps_the_order() -> None:
    diary: list[str] = []

    outcomes = AllSourcesCollector(three_sources(diary)).collect()

    assert diary[-3:] == ["linkedin stored", "email stored", "calendar stored"]
    assert [outcome.source.channel for outcome in outcomes] == [
        Channel.LINKEDIN,
        Channel.EMAIL,
        Channel.CALENDAR,
    ]
    assert all(outcome.succeeded for outcome in outcomes)


def test_a_source_that_cannot_be_read_never_stops_the_others() -> None:
    diary: list[str] = []

    linkedin, email, calendar = AllSourcesCollector(three_sources(diary, read_fails=True)).collect()

    assert isinstance(email.failure, SourceAuthError)
    assert not email.succeeded
    assert "email stored" not in diary
    assert linkedin.succeeded
    assert calendar.succeeded


def test_a_source_that_cannot_be_stored_never_stops_the_next_one() -> None:
    diary: list[str] = []

    _, email, calendar = AllSourcesCollector(three_sources(diary, save_fails=True)).collect()

    assert isinstance(email.failure, DatabaseUnavailableError)
    assert calendar.succeeded


def test_a_source_that_is_not_set_up_is_neither_a_success_nor_a_failure() -> None:
    _, email, _ = AllSourcesCollector(three_sources([], not_configured=True)).collect()

    assert email.failure is None
    assert not email.succeeded


def steps_of(client: FakeSupabaseClient) -> dict[str, dict[str, Any]]:
    """The recorded steps of the run, by step name."""
    return {str(row["step"]): row for row in rows_of(client, "run_step_logs")}


def test_each_source_is_recorded_as_its_own_step(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    clock: FixedClock,
) -> None:
    recorder = RunRecorder(repositories, clock)
    run = recorder.start(RunTrigger.MANUAL)
    outcomes = AllSourcesCollector(three_sources([], read_fails=True)).collect()

    record_outcomes(recorder, run.id, outcomes)

    steps = steps_of(fake_client)
    assert steps["collect_linkedin"]["status"] == RunStatus.SUCCESS.value
    assert (steps["collect_linkedin"]["items_found"], steps["collect_linkedin"]["items_new"]) == (
        7,
        2,
    )
    assert steps["collect_email"]["status"] == RunStatus.FAILED.value
    assert steps["collect_email"]["error_code"] == SourceAuthError.code
    assert steps["collect_calendar"]["status"] == RunStatus.SUCCESS.value


def test_a_source_that_is_not_set_up_is_not_a_step_of_the_run(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    clock: FixedClock,
) -> None:
    recorder = RunRecorder(repositories, clock)
    run = recorder.start(RunTrigger.MANUAL)
    outcomes = AllSourcesCollector(three_sources([], not_configured=True)).collect()

    record_outcomes(recorder, run.id, outcomes)

    assert set(steps_of(fake_client)) == {"collect_linkedin", "collect_calendar"}


# --- the real collectors, against made-up sources -----------------------------


def signed_in(repositories: Repositories, clock: FixedClock) -> None:
    """Store a made-up Microsoft sign-in key."""
    SecretStore(repositories.app_secrets, SecretStr(TEST_ENCRYPTION_KEY), clock).put_secret(
        MICROSOFT_REFRESH_TOKEN, "old-long-lived-key"
    )


def mock_every_source(calendar_status: int = 200) -> None:
    """Answer LinkedIn, the mailbox and the calendar."""
    mock_archive(ARCHIVE)
    mock_mailbox(MAILBOX)
    respx.get(CALENDAR_URL).mock(
        return_value=httpx.Response(calendar_status, json={"value": EVENTS})
    )


def real_sources(
    repositories: Repositories, settings: Settings, clock: FixedClock
) -> tuple[tuple[Source, ...], ...]:
    """The three collectors, grouped as the command groups them."""
    linkedin = LinkedInCollector(repositories, settings, clock, JOB_SEARCH_RULES)
    email = EmailCollector(repositories, settings, clock, JOB_SEARCH_RULES)
    calendar = CalendarCollector(repositories, settings, clock, JOB_SEARCH_RULES)
    return (
        (Source(Channel.LINKEDIN, RunStep.COLLECT_LINKEDIN, linkedin.read),),
        (
            Source(Channel.EMAIL, RunStep.COLLECT_EMAIL, email.read),
            Source(Channel.CALENDAR, RunStep.COLLECT_CALENDAR, calendar.read),
        ),
    )


def stored(client: FakeSupabaseClient) -> dict[str, list[tuple[Any, ...]]]:
    """Everything the collectors wrote, without the identifiers made up on the way."""
    names = {row["id"]: row["full_name"] for row in rows_of(client, "people")}
    threads = {row["id"]: row["source_conversation_id"] for row in rows_of(client, "conversations")}
    return {
        "people": sorted((name,) for name in names.values()),
        "identities": sorted(
            (row["channel"], row["identifier"], names[row["person_id"]])
            for row in rows_of(client, "person_identities")
        ),
        "conversations": sorted(
            (
                row["channel"],
                row["source_conversation_id"],
                row["relevance"],
                str(row["subject"]),
                str(names.get(row["person_id"])),
            )
            for row in rows_of(client, "conversations")
        ),
        "messages": sorted(
            (
                threads[row["conversation_id"]],
                row["source_message_id"],
                row["direction"],
                str(row["body"]),
            )
            for row in rows_of(client, "messages")
        ),
    }


def test_one_step_leaves_the_same_rows_as_one_source_after_another(
    settings: Settings,
    clock: FixedClock,
) -> None:
    in_turn_client, together_client = FakeSupabaseClient(), FakeSupabaseClient()
    in_turn = build_repositories(as_client(in_turn_client))
    together = build_repositories(as_client(together_client))
    signed_in(in_turn, clock)
    signed_in(together, clock)

    with respx.mock:
        mock_every_source()
        LinkedInCollector(in_turn, settings, clock, JOB_SEARCH_RULES).collect()
        EmailCollector(in_turn, settings, clock, JOB_SEARCH_RULES).collect()
        CalendarCollector(in_turn, settings, clock, JOB_SEARCH_RULES).collect()
    with respx.mock:
        mock_every_source()
        outcomes = AllSourcesCollector(real_sources(together, settings, clock)).collect()

    assert all(outcome.succeeded for outcome in outcomes)
    assert stored(together_client) == stored(in_turn_client)
    assert len(stored(together_client)["conversations"]) > len(EVENTS)


def test_a_calendar_that_does_not_answer_leaves_linkedin_and_the_mail_stored(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    signed_in(repositories, clock)

    with respx.mock:
        mock_every_source(calendar_status=403)
        linkedin, email, calendar = AllSourcesCollector(
            real_sources(repositories, settings, clock)
        ).collect()

    assert linkedin.succeeded
    assert email.succeeded
    assert calendar.failure is not None
    channels = {row["channel"] for row in rows_of(fake_client, "conversations")}
    assert channels == {Channel.LINKEDIN.value, Channel.EMAIL.value}


# --- the command ----------------------------------------------------------------


@pytest.fixture
def wired(
    monkeypatch: pytest.MonkeyPatch,
    repositories: Repositories,
    settings: Settings,
    clock: FixedClock,
) -> Repositories:
    """Point ``tracker collect`` at the in-memory database and a signed-in mailbox."""
    monkeypatch.setattr("tracker.cli.commands.collect._wiring", lambda: (settings, repositories))
    monkeypatch.setattr("tracker.cli.commands.collect._rules", lambda _repos: JOB_SEARCH_RULES)
    monkeypatch.setattr("tracker.cli.commands.collect.SystemClock", lambda _zone: clock)
    signed_in(repositories, clock)
    return repositories


def run_command(*arguments: str, calendar_status: int = 200) -> tuple[Any, int]:
    """Run ``tracker collect all`` against made-up sources.

    Returns:
        What the command printed and how it ended, and how many requests it made.
    """
    with respx.mock:
        mock_every_source(calendar_status)
        result = CliRunner().invoke(build_cli(), ["collect", "all", *arguments])
        return result, sum(route.call_count for route in respx.routes)


def test_the_command_prints_every_source_and_records_every_step(
    wired: Repositories,
    fake_client: FakeSupabaseClient,
    clock: FixedClock,
) -> None:
    RunRecorder(wired, clock).start(RunTrigger.MANUAL)

    result, _ = run_command("--record")

    assert result.exit_code == 0
    lines = result.output.splitlines()
    for channel in ("linkedin", "email", "calendar"):
        assert f"channel: {channel}" in lines
    assert "sources collected: 3" in lines
    assert lines[-1] == "steps recorded"
    assert {step["status"] for step in steps_of(fake_client).values()} == {RunStatus.SUCCESS.value}
    assert set(steps_of(fake_client)) == {"collect_linkedin", "collect_email", "collect_calendar"}


def test_with_record_a_failed_source_is_printed_and_recorded_and_the_command_carries_on(
    wired: Repositories,
    fake_client: FakeSupabaseClient,
    clock: FixedClock,
) -> None:
    RunRecorder(wired, clock).start(RunTrigger.MANUAL)

    result, _ = run_command("--record", calendar_status=403)

    assert result.exit_code == 0
    assert "failed · code=source_unavailable" in result.output.splitlines()
    assert "sources collected: 2" in result.output.splitlines()
    assert steps_of(fake_client)["collect_calendar"]["error_code"] == "source_unavailable"
    assert steps_of(fake_client)["collect_email"]["status"] == RunStatus.SUCCESS.value


def test_with_record_and_no_run_open_nothing_is_read(wired: Repositories) -> None:
    result, requests = run_command("--record")

    assert result.exit_code != 0
    assert requests == 0


def test_by_hand_a_failed_source_still_ends_the_command_as_a_failure(
    wired: Repositories,
    fake_client: FakeSupabaseClient,
) -> None:
    result, _ = run_command(calendar_status=403)

    assert result.exit_code != 0
    assert "sources collected: 2" in result.output.splitlines()
    assert rows_of(fake_client, "run_step_logs") == []


def test_refresh_and_since_cannot_be_combined(wired: Repositories) -> None:
    result, requests = run_command("--refresh", "--since", "2026-09-01")

    assert result.exit_code != 0
    assert requests == 0


def test_outcomes_say_whether_a_source_was_collected() -> None:
    source = fake_source(Channel.EMAIL, RunStep.COLLECT_EMAIL, [])

    assert SourceOutcome(source, report=CollectionReport(channel=Channel.EMAIL)).succeeded
    assert not SourceOutcome(source, failure=SourceAuthError("refused")).succeeded
