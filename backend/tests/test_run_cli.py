"""The daily-run commands: the help, the file they write, one clean line on failure."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.conftest import FakeSupabaseClient, as_client
from tests.summary_world import sample_client
from tracker.cli.discovery import command_module_names
from tracker.cli.main import build_cli, main
from tracker.domain.enums import RunStatus, RunStep, RunTrigger
from tracker.shared.config import Settings, reset_settings_cache
from tracker.shared.errors import DatabaseUnavailableError


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def database(monkeypatch: pytest.MonkeyPatch) -> FakeSupabaseClient:
    """An in-memory database standing in for Supabase behind the commands."""
    client = sample_client()
    monkeypatch.setattr(
        "tracker.cli.commands.run.create_database_client",
        lambda _settings: as_client(client),
    )
    return client


def _printed_run_id(output: str) -> str:
    """The identifier ``tracker run start`` printed, ignoring the log lines."""
    printed = [line for line in output.splitlines() if line.startswith("run ")]
    return printed[-1].split()[1]


def test_the_run_module_is_discovered() -> None:
    assert "run" in command_module_names()


def test_the_help_lists_the_daily_run_commands(runner: CliRunner) -> None:
    result = runner.invoke(build_cli(), ["--help"])

    assert result.exit_code == 0
    assert "run" in result.output
    assert "summary" in result.output


def test_the_run_group_offers_start_step_and_finish(runner: CliRunner) -> None:
    result = runner.invoke(build_cli(), ["run", "--help"])

    assert result.exit_code == 0
    for command in ("start", "step", "finish"):
        assert command in result.output


def test_starting_a_run_prints_its_identifier(
    runner: CliRunner,
    database: FakeSupabaseClient,
    settings: Settings,
) -> None:
    result = runner.invoke(build_cli(), ["run", "start", "--trigger", RunTrigger.MANUAL.value])

    assert result.exit_code == 0
    assert "started" in result.output
    assert settings.app_env is not None
    started = [row for row in database.tables["run_logs"] if row["trigger"] == "manual"]
    assert len(started) == 1
    assert started[0]["status"] == RunStatus.RUNNING.value


def test_starting_a_run_passes_the_owners_time_zone_to_the_database(
    runner: CliRunner,
    database: FakeSupabaseClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert settings.owner_time_zone == "UTC"
    monkeypatch.setenv("OWNER_TIME_ZONE", "Asia/Tokyo")
    reset_settings_cache()

    first = runner.invoke(build_cli(), ["run", "start"])
    second = runner.invoke(build_cli(), ["run", "start"])

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert "time zone: Asia/Tokyo" in first.output
    (row,) = database.tables["app_settings"]
    assert row["singleton"] is True
    assert row["time_zone"] == "Asia/Tokyo"


def test_a_run_still_starts_when_the_time_zone_cannot_be_saved(
    runner: CliRunner,
    database: FakeSupabaseClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert settings.supabase_url

    def refuse(*_arguments: object) -> str:
        message = "database request failed on app_settings.save_time_zone"
        raise DatabaseUnavailableError(message)

    monkeypatch.setattr("tracker.cli.commands.run.publish_owner_settings", refuse)

    result = runner.invoke(build_cli(), ["run", "start"])

    assert result.exit_code == 0
    assert "started" in result.output
    assert "time zone not saved" in result.output
    assert database.tables["run_logs"]


def test_recording_linkedin_when_it_is_not_set_up_records_nothing(
    runner: CliRunner,
    database: FakeSupabaseClient,
    settings_without_linkedin_key: Settings,
) -> None:
    assert not settings_without_linkedin_key.linkedin_enabled
    started = runner.invoke(build_cli(), ["run", "start"])
    run_id = _printed_run_id(started.output)

    result = runner.invoke(
        build_cli(),
        ["run", "step", "--step", RunStep.COLLECT_LINKEDIN.value, "--result", "failed"],
    )

    assert result.exit_code == 0
    assert "not configured" in result.output
    assert not [row for row in database.tables["run_step_logs"] if row["run_id"] == run_id]


def test_a_step_and_the_finish_record_the_run_as_partial(
    runner: CliRunner,
    database: FakeSupabaseClient,
    settings: Settings,
) -> None:
    assert settings.supabase_url
    started = runner.invoke(build_cli(), ["run", "start", "--trigger", RunTrigger.MANUAL.value])
    run_id = _printed_run_id(started.output)
    runner.invoke(
        build_cli(),
        ["run", "step", "--step", RunStep.COLLECT_LINKEDIN.value, "--result", "success"],
    )
    failed = runner.invoke(
        build_cli(),
        [
            "run",
            "step",
            "--step",
            RunStep.COLLECT_EMAIL.value,
            "--result",
            "failed",
            "--error-code",
            "source_auth_failed",
        ],
    )
    finished = runner.invoke(build_cli(), ["run", "finish"])

    assert failed.exit_code == 0
    assert finished.exit_code == 0
    assert f"status {RunStatus.PARTIAL.value}" in finished.output
    stored = [row for row in database.tables["run_logs"] if row["id"] == run_id]
    assert stored[0]["status"] == RunStatus.PARTIAL.value


def test_building_the_summary_writes_a_file_and_prints_the_subject(
    runner: CliRunner,
    database: FakeSupabaseClient,
    settings: Settings,
    tmp_path: Path,
) -> None:
    assert database.tables["run_logs"]
    assert settings.supabase_url
    out = tmp_path / "nested" / "summary.json"

    result = runner.invoke(build_cli(), ["summary", "build", "--out", str(out)])

    assert result.exit_code == 0
    assert str(out) in result.output
    assert f"to: {settings.summary_recipient_address}" in result.output
    assert "delivery: gmail_connector" in result.output
    stored = json.loads(out.read_text(encoding="utf-8"))
    assert stored["recipient"] == settings.summary_recipient_address
    assert stored["subject_prefix"] == settings.summary_subject_prefix
    assert stored["subject"].startswith(stored["subject_prefix"])
    assert stored["subject"] in result.output
    assert stored["content"]["run_status"] == RunStatus.PARTIAL.value
    assert stored["text_body"]


@pytest.mark.parametrize(
    "command",
    [
        ["run", "start"],
        ["run", "finish"],
        ["run", "step", "--step", "assess", "--result", "success"],
        ["summary", "build"],
    ],
)
def test_a_command_without_configuration_fails_on_one_line(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: list[str],
) -> None:
    monkeypatch.setattr("sys.argv", ["tracker", *command])

    with pytest.raises(SystemExit) as raised:
        main()

    assert raised.value.code == 1
    errors = capsys.readouterr().err.strip().splitlines()
    assert len(errors) == 1
    assert "configuration_invalid" in errors[0]
    assert "Traceback" not in errors[0]


def test_sending_without_an_imap_mailbox_is_refused_and_recorded(
    runner: CliRunner,
    database: FakeSupabaseClient,
    settings: Settings,
    tmp_path: Path,
) -> None:
    out = tmp_path / "summary.json"
    runner.invoke(build_cli(), ["summary", "build", "--out", str(out)])

    result = runner.invoke(build_cli(), ["summary", "send", "--file", str(out)])

    assert result.exit_code != 0
    assert settings.summary_route.value == "gmail_connector"
    sent = [row for row in database.tables["run_step_logs"] if row["step"] == "summary_email"]
    assert "configuration_invalid" in [row["error_code"] for row in sent]
