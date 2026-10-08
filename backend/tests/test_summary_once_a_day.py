"""One morning summary a day: a second daily run on the same day sends nothing."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, tzinfo
from itertools import count
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from typer.testing import CliRunner

from tests.conftest import FakeSupabaseClient, as_client
from tests.summary_world import NOW, TODAYS_RUN, sample_client
from tests.test_summary_send import MAILBOX, FakeSmtp, mailer_on, written_summary
from tracker.cli.main import build_cli
from tracker.domain.enums import RunStatus, RunStep, RunTrigger
from tracker.domain.models import RunLog
from tracker.repositories import build_repositories
from tracker.services.runs.run_recorder import RunRecorder
from tracker.services.summary.builder import SummaryBuilder
from tracker.services.summary.once_a_day import OnceADay
from tracker.services.summary.sender import SentSummary, SkippedSummary, SummarySender
from tracker.shared import config
from tracker.shared.clock import FixedClock
from tracker.shared.config import Settings

#: The morning the command tests run on, well after the sample data's runs.
MORNING = datetime(2026, 10, 4, 6, 0, tzinfo=UTC)

#: Greta Lindqvist, who wrote back in the sample data.
GRETA = "b0000000-0000-4000-8000-000000000007"


@pytest.fixture
def imap_settings(valid_environment: None, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """An owner who reads Gmail over IMAP, so the summary goes by SMTP."""
    monkeypatch.setenv("MAIL_SOURCES", "imap")
    monkeypatch.setenv("IMAP_PROVIDER", "gmail")
    monkeypatch.setenv("IMAP_USERNAME", MAILBOX)
    config.reset_settings_cache()
    return config.get_settings()


def _summary_of(client: FakeSupabaseClient, run_id: UUID | str, how: str) -> None:
    """Record that run's ``summary_email`` step as ``"sent"`` or ``"failed"``."""
    client.tables["run_step_logs"].append(
        {
            "id": str(uuid4()),
            "run_id": str(run_id),
            "step": RunStep.SUMMARY_EMAIL.value,
            "status": "success" if how == "sent" else "failed",
            "items_found": 1 if how == "sent" else None,
            "items_new": 1 if how == "sent" else None,
            "error_code": None if how == "sent" else "source_unavailable",
            "error_detail": None,
        }
    )


def _open_run(
    client: FakeSupabaseClient, started_at: datetime, trigger: RunTrigger = RunTrigger.GITHUB
) -> UUID:
    """Add a daily run still going, as one is while its summary goes out."""
    run_id = uuid4()
    client.tables["run_logs"].append(
        {
            "id": str(run_id),
            "started_at": started_at.isoformat(),
            "finished_at": None,
            "status": RunStatus.RUNNING.value,
            "trigger": trigger.value,
        }
    )
    return run_id


def _sender(
    settings: Settings, client: FakeSupabaseClient, server: FakeSmtp, clock: FixedClock
) -> SummarySender:
    repositories = build_repositories(as_client(client))
    return SummarySender(
        settings,
        lambda: mailer_on(server),
        RunRecorder(repositories, clock),
        OnceADay(repositories, clock),
    )


def _step(client: FakeSupabaseClient, run_id: UUID) -> dict[str, object]:
    [row] = [
        row
        for row in client.tables["run_step_logs"]
        if row["run_id"] == str(run_id) and row["step"] == RunStep.SUMMARY_EMAIL.value
    ]
    return row


def test_a_second_daily_run_on_the_same_day_sends_nothing_and_says_why(
    imap_settings: Settings, tmp_path: Path
) -> None:
    client = sample_client()
    _summary_of(client, TODAYS_RUN, "sent")
    second = _open_run(client, NOW)
    path = written_summary(imap_settings, tmp_path, client)
    server = FakeSmtp()

    result = _sender(imap_settings, client, server, FixedClock(NOW)).send(path, second)

    assert isinstance(result, SkippedSummary)
    assert result.earlier.id == TODAYS_RUN
    assert server.sent == []
    step = _step(client, second)
    assert step["status"] == RunStatus.SUCCESS.value
    assert step["items_new"] == 0
    assert str(TODAYS_RUN) in str(step["error_detail"])


def test_a_skipped_summary_leaves_the_run_clean(imap_settings: Settings, tmp_path: Path) -> None:
    client = sample_client()
    _summary_of(client, TODAYS_RUN, "sent")
    second = _open_run(client, NOW)
    path = written_summary(imap_settings, tmp_path, client)
    clock = FixedClock(NOW)
    _sender(imap_settings, client, FakeSmtp(), clock).send(path, second)

    finished = RunRecorder(build_repositories(as_client(client)), clock).finish(second)

    assert finished.status is RunStatus.SUCCESS


def test_send_again_sends_a_second_copy_on_purpose(
    imap_settings: Settings, tmp_path: Path
) -> None:
    client = sample_client()
    _summary_of(client, TODAYS_RUN, "sent")
    second = _open_run(client, NOW)
    path = written_summary(imap_settings, tmp_path, client)
    server = FakeSmtp()

    result = _sender(imap_settings, client, server, FixedClock(NOW)).send(
        path, second, send_again=True
    )

    assert isinstance(result, SentSummary)
    assert len(server.sent) == 1
    assert _step(client, second)["items_new"] == 1


def test_the_next_day_sends_as_usual(imap_settings: Settings, tmp_path: Path) -> None:
    client = sample_client()
    _summary_of(client, TODAYS_RUN, "sent")
    tomorrow = NOW + timedelta(days=1)
    next_morning = _open_run(client, tomorrow)
    path = written_summary(imap_settings, tmp_path, client)
    server = FakeSmtp()

    result = _sender(imap_settings, client, server, FixedClock(tomorrow)).send(path, next_morning)

    assert isinstance(result, SentSummary)
    assert len(server.sent) == 1


def test_an_earlier_send_that_failed_does_not_stop_the_rerun(
    imap_settings: Settings, tmp_path: Path
) -> None:
    client = sample_client()
    _summary_of(client, TODAYS_RUN, "failed")
    second = _open_run(client, NOW)
    path = written_summary(imap_settings, tmp_path, client)
    server = FakeSmtp()

    result = _sender(imap_settings, client, server, FixedClock(NOW)).send(path, second)

    assert isinstance(result, SentSummary)
    assert len(server.sent) == 1


def test_a_skipped_rerun_does_not_count_as_a_summary_that_went_out(
    imap_settings: Settings, tmp_path: Path
) -> None:
    """A third run the same day still finds the first one, and still skips."""
    client = sample_client()
    _summary_of(client, TODAYS_RUN, "sent")
    second = _open_run(client, NOW)
    third = _open_run(client, NOW + timedelta(minutes=30))
    path = written_summary(imap_settings, tmp_path, client)
    clock = FixedClock(NOW + timedelta(minutes=30))
    _sender(imap_settings, client, FakeSmtp(), clock).send(path, second)

    result = _sender(imap_settings, client, FakeSmtp(), clock).send(path, third)

    assert isinstance(result, SkippedSummary)
    assert result.earlier.id == TODAYS_RUN


def test_tomorrows_replies_count_from_the_run_that_sent_not_the_one_that_skipped(
    imap_settings: Settings, tmp_path: Path
) -> None:
    """A reply between the sending run and the skipped rerun reaches the next e-mail."""
    client = sample_client()
    _summary_of(client, TODAYS_RUN, "sent")
    second = _open_run(client, NOW)
    path = written_summary(imap_settings, tmp_path, client)
    _sender(imap_settings, client, FakeSmtp(), FixedClock(NOW)).send(path, second)
    for row in client.tables["conversations"]:
        if row.get("person_id") == GRETA:
            row["last_inbound_at"] = "2026-09-18T06:00:00Z"  # between 05:00 and 07:00
    tomorrow = NOW + timedelta(days=1)
    next_morning = _open_run(client, tomorrow)
    repositories = build_repositories(as_client(client))
    builder = SummaryBuilder(repositories, imap_settings, FixedClock(tomorrow))

    replied = builder.build(next_morning).content.replied

    assert [person.name for person in replied] == ["Greta Lindqvist"]


def _run(started_at: datetime, trigger: RunTrigger = RunTrigger.GITHUB) -> RunLog:
    return RunLog(started_at=started_at, status=RunStatus.RUNNING, trigger=trigger)


@pytest.mark.parametrize(
    ("zone", "skipped"),
    [(ZoneInfo("Europe/Rome"), True), (UTC, False)],
)
def test_the_day_is_the_owners_day(zone: tzinfo, *, skipped: bool) -> None:
    """23:30 UTC on the 17th is already the 18th in Rome, the same day as 05:00 UTC."""
    client = sample_client()
    late = _open_run(client, datetime(2026, 9, 17, 23, 30, tzinfo=UTC))
    _summary_of(client, late, "sent")
    clock = FixedClock(NOW, zone)
    once = OnceADay(build_repositories(as_client(client)), clock)
    todays = next(
        RunLog.model_validate(row)
        for row in client.tables["run_logs"]
        if row["id"] == str(TODAYS_RUN)
    )

    earlier = once.sent_earlier_today(todays)

    assert (earlier is not None) is skipped


def test_a_refresh_is_never_held_back() -> None:
    client = sample_client()
    _summary_of(client, TODAYS_RUN, "sent")
    once = OnceADay(build_repositories(as_client(client)), FixedClock(NOW))

    assert once.sent_earlier_today(_run(NOW, RunTrigger.REFRESH)) is None


# --- the commands: what the daily recipe sees -----------------------------------


@pytest.fixture
def database(monkeypatch: pytest.MonkeyPatch) -> FakeSupabaseClient:
    """The sample data behind the commands, on one morning whose clock moves a minute a call."""
    client = sample_client()
    monkeypatch.setattr(
        "tracker.cli.commands.run.create_database_client",
        lambda _settings: as_client(client),
    )
    ticks = count()

    def morning_clock(zone: tzinfo = UTC) -> FixedClock:
        return FixedClock(MORNING + timedelta(minutes=next(ticks)), zone)

    monkeypatch.setattr("tracker.cli.commands.run.SystemClock", morning_clock)
    return client


def _morning(runner: CliRunner, out: Path) -> None:
    """One daily run on the connector route: start, build, send, record, finish."""
    runner.invoke(build_cli(), ["run", "start", "--trigger", "github"])
    runner.invoke(build_cli(), ["summary", "build", "--out", str(out)])
    sent = ["run", "step", "--step", "summary_email", "--result", "success"]
    runner.invoke(build_cli(), [*sent, "--found", "1", "--new", "1"])
    runner.invoke(build_cli(), ["run", "finish"])


@pytest.mark.usefixtures("settings")
def test_a_rerun_of_the_morning_builds_no_second_summary(
    database: FakeSupabaseClient, tmp_path: Path
) -> None:
    runner = CliRunner()
    out = tmp_path / "summary.json"
    _morning(runner, out)
    runner.invoke(build_cli(), ["run", "start", "--trigger", "github"])

    result = runner.invoke(build_cli(), ["summary", "build", "--out", str(out)])

    assert result.exit_code == 0
    assert "summary skipped · today's summary already went out with run" in result.output
    assert not out.exists()
    steps = [row for row in database.tables["run_step_logs"] if row["items_new"] == 0]
    assert [row["step"] for row in steps] == [RunStep.SUMMARY_EMAIL.value]


@pytest.mark.usefixtures("settings", "database")
def test_send_again_builds_the_rerun_summary_anyway(tmp_path: Path) -> None:
    runner = CliRunner()
    out = tmp_path / "summary.json"
    _morning(runner, out)
    runner.invoke(build_cli(), ["run", "start", "--trigger", "github"])

    result = runner.invoke(build_cli(), ["summary", "build", "--out", str(out), "--send-again"])

    assert result.exit_code == 0
    assert json.loads(out.read_text(encoding="utf-8"))["subject"]
