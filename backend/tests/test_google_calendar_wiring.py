"""Google Calendar in the configuration, the daily run, the summary and the doctor."""

from __future__ import annotations

import httpx
import pytest
import respx
from pydantic import SecretStr
from typer.testing import CliRunner

from tests.conftest import JOB_SEARCH_RULES, FakeSupabaseClient
from tests.ical_world import GOOGLE_ADDRESS, calendar_file, vevent
from tests.test_all_sources import mock_every_source, signed_in, steps_of
from tracker.cli.doctor_wiring import DEPENDENT_CHECKS, _google_calendar_count, render
from tracker.cli.main import build_cli
from tracker.domain.enums import RunStatus, RunStep, RunTrigger
from tracker.repositories import Repositories
from tracker.services.doctor.checks import GoogleCalendarCheck
from tracker.services.doctor.models import CheckStatus
from tracker.services.doctor.service import DoctorService
from tracker.services.runs.run_recorder import RunRecorder, unconfigured_steps
from tracker.services.summary.problem_messages import explain
from tracker.shared.clock import FixedClock
from tracker.shared.config import Settings, get_settings, reset_settings_cache
from tracker.shared.errors import ConfigurationError

COPIED_FROM_APPLE = "webcal://p01-caldav.icloud.example/published/2/secret"


def _with_address(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("GOOGLE_CALENDAR_URL", value)
    reset_settings_cache()


# --- The setting -----------------------------------------------------------------


@pytest.mark.usefixtures("valid_environment")
def test_the_google_calendar_is_optional() -> None:
    settings = get_settings()

    assert settings.google_calendar_url is None
    assert settings.google_calendar_enabled is False
    assert RunStep.COLLECT_GOOGLE_CALENDAR in unconfigured_steps(settings)


@pytest.mark.usefixtures("valid_environment")
def test_a_saved_address_is_a_secret_and_switches_the_step_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with_address(monkeypatch, f"  {GOOGLE_ADDRESS}  ")

    settings = get_settings()

    assert settings.google_calendar_url is not None
    assert settings.google_calendar_url.get_secret_value() == GOOGLE_ADDRESS
    assert "private-" not in repr(settings)
    assert RunStep.COLLECT_GOOGLE_CALENDAR not in unconfigured_steps(settings)


@pytest.mark.usefixtures("valid_environment")
def test_a_webcal_address_is_read_over_https(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_address(monkeypatch, COPIED_FROM_APPLE)

    address = get_settings().google_calendar_url

    assert address is not None
    assert address.get_secret_value() == COPIED_FROM_APPLE.replace("webcal://", "https://", 1)


@pytest.mark.usefixtures("valid_environment")
@pytest.mark.parametrize(
    "value",
    ["http://calendar.example/secret-123.ics", "calendar.google.com/secret-123", "https://"],
)
def test_a_wrong_address_stops_with_its_name_and_never_its_value(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    _with_address(monkeypatch, value)

    with pytest.raises(ConfigurationError) as raised:
        get_settings()

    assert "GOOGLE_CALENDAR_URL" in raised.value.message
    assert "secret-123" not in raised.value.message


# --- The daily run ---------------------------------------------------------------


def _wired(
    monkeypatch: pytest.MonkeyPatch,
    repositories: Repositories,
    settings: Settings,
    clock: FixedClock,
) -> None:
    """Point ``tracker collect`` at the in-memory database and a Google calendar."""
    google = settings.model_copy(update={"google_calendar_url": SecretStr(GOOGLE_ADDRESS)})
    monkeypatch.setattr("tracker.cli.commands.collect._wiring", lambda: (google, repositories))
    monkeypatch.setattr("tracker.cli.commands.collect._rules", lambda _repos: JOB_SEARCH_RULES)
    monkeypatch.setattr("tracker.cli.commands.collect.SystemClock", lambda _zone: clock)
    signed_in(repositories, clock)


def _collect_all(google_status: int) -> list[str]:
    """Run ``tracker collect all --record`` with every source answering."""
    content = calendar_file(vevent("google-intro@google.com"))
    with respx.mock:
        mock_every_source()
        respx.get(GOOGLE_ADDRESS).mock(return_value=httpx.Response(google_status, content=content))
        result = CliRunner().invoke(build_cli(), ["collect", "all", "--record"])
    assert result.exit_code == 0
    return result.output.splitlines()


def test_the_daily_run_reads_and_records_the_google_calendar(
    monkeypatch: pytest.MonkeyPatch,
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    _wired(monkeypatch, repositories, settings, clock)
    RunRecorder(repositories, clock).start(RunTrigger.MANUAL)

    lines = _collect_all(200)

    assert "sources collected: 4" in lines
    step = steps_of(fake_client)[RunStep.COLLECT_GOOGLE_CALENDAR.value]
    assert step["status"] == RunStatus.SUCCESS.value
    assert step["items_found"] == 1
    threads = {row["source_conversation_id"] for row in fake_client.tables["conversations"]}
    assert "google-intro@google.com" in threads


def test_a_refused_address_is_recorded_and_the_other_sources_still_count(
    monkeypatch: pytest.MonkeyPatch,
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    _wired(monkeypatch, repositories, settings, clock)
    RunRecorder(repositories, clock).start(RunTrigger.MANUAL)

    lines = _collect_all(404)

    assert "sources collected: 3" in lines
    assert "failed · code=source_auth_failed" in lines
    assert not any("private-" in line for line in lines)
    steps = steps_of(fake_client)
    assert steps[RunStep.COLLECT_GOOGLE_CALENDAR.value]["error_code"] == "source_auth_failed"
    assert steps[RunStep.COLLECT_CALENDAR.value]["status"] == RunStatus.SUCCESS.value


def test_the_command_reads_the_google_calendar_alone(
    monkeypatch: pytest.MonkeyPatch,
    repositories: Repositories,
    settings: Settings,
    clock: FixedClock,
) -> None:
    _wired(monkeypatch, repositories, settings, clock)
    content = calendar_file(vevent("google-intro@google.com"))

    with respx.mock:
        respx.get(GOOGLE_ADDRESS).mock(return_value=httpx.Response(200, content=content))
        result = CliRunner().invoke(build_cli(), ["collect", "google-calendar"])

    assert result.exit_code == 0
    assert "channel: calendar" in result.output.splitlines()


# --- The morning summary ---------------------------------------------------------


def test_a_link_that_stopped_working_says_to_make_a_new_one() -> None:
    problem = explain(RunStep.COLLECT_GOOGLE_CALENDAR, "source_auth_failed")

    assert "Google says its secret address no longer works" in problem.what_happened
    assert "uv run tracker setup google-calendar" in problem.what_to_do
    assert "Google Workspace administrator" in problem.what_to_do


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("source_unavailable", "next run tries again"),
        ("download_too_large", "larger than Threadline reads"),
        ("validation_failed", "Secret address in iCal format"),
        ("a_brand_new_code", "Google Calendar could not be read"),
    ],
)
def test_every_google_calendar_problem_reads_as_plain_words(code: str, expected: str) -> None:
    problem = explain(RunStep.COLLECT_GOOGLE_CALENDAR, code)

    assert expected in f"{problem.what_happened} {problem.what_to_do}"
    assert code not in f"{problem.what_happened} {problem.what_to_do}"


# --- The doctor ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_doctor_skips_a_calendar_that_is_not_connected(settings: Settings) -> None:
    result = await GoogleCalendarCheck(_google_calendar_count(settings)).run()

    assert result.status is CheckStatus.SKIPPED
    assert "Google Calendar" in DEPENDENT_CHECKS


@pytest.mark.asyncio
async def test_the_doctor_reads_the_calendar_once(settings: Settings) -> None:
    google = settings.model_copy(update={"google_calendar_url": SecretStr(GOOGLE_ADDRESS)})
    content = calendar_file(vevent("intro@google.com"), vevent("coffee@google.com"))

    with respx.mock:
        respx.get(GOOGLE_ADDRESS).mock(return_value=httpx.Response(200, content=content))
        report = await DoctorService([GoogleCalendarCheck(_google_calendar_count(google))]).run()

    (result,) = report.results
    assert result.status is CheckStatus.OK
    assert result.detail.startswith("the calendar answered with 2 events")


@pytest.mark.asyncio
async def test_the_doctor_names_the_fix_for_a_refused_address_and_never_the_address(
    settings: Settings,
) -> None:
    google = settings.model_copy(update={"google_calendar_url": SecretStr(GOOGLE_ADDRESS)})

    with respx.mock:
        respx.get(GOOGLE_ADDRESS).mock(return_value=httpx.Response(403))
        report = await DoctorService([GoogleCalendarCheck(_google_calendar_count(google))]).run()

    (result,) = report.results
    assert result.status is CheckStatus.PROBLEM
    assert result.fix == "run 'uv run tracker setup google-calendar'"
    assert "private-" not in " ".join(render(report))
