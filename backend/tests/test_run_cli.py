"""The daily-run commands: the help, the file they write, one clean line on failure."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.conftest import FakeSupabaseClient, as_client, printed_lines
from tests.summary_world import sample_client
from tracker.cli.commands import ai, profile
from tracker.cli.discovery import command_module_names
from tracker.cli.main import build_cli, main
from tracker.domain.enums import RunStatus, RunStep, RunTrigger
from tracker.services.assessment.work_files import clean_work_directory
from tracker.shared.config import Settings, reset_settings_cache
from tracker.shared.errors import DatabaseUnavailableError, ValidationFailedError, WorkFileError

#: The codes a terminal reads as "switch to this colour".
_COLOUR_CODES = re.compile(r"\x1b\[[0-9;]*m")


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
    runner.invoke(build_cli(), ["run", "start"])

    result = runner.invoke(build_cli(), ["summary", "send", "--file", str(out)])

    assert result.exit_code != 0
    assert settings.summary_route.value == "gmail_connector"
    sent = [row for row in database.tables["run_step_logs"] if row["step"] == "summary_email"]
    assert "configuration_invalid" in [row["error_code"] for row in sent]


# --- run start --prepare: the health check and the profile in the same step -----


@pytest.fixture
def profile_arguments(tmp_path: Path) -> list[str]:
    """Keep ``profile apply`` away from the repository: no profile file, a guide of its own."""
    return ["--file", str(tmp_path / "no-profile.toml"), "--guide", str(tmp_path / "guide.md")]


@pytest.fixture
def prepared(
    database: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
    profile_arguments: list[str],
) -> FakeSupabaseClient:
    """Put the health check and the profile on the same in-memory database as the run."""
    for module in ("system", "profile"):
        monkeypatch.setattr(
            f"tracker.cli.commands.{module}.create_database_client",
            lambda _settings: as_client(database),
        )
    monkeypatch.setattr(
        "tracker.cli.commands.run.apply_profile",
        lambda: profile.apply(file=Path(profile_arguments[1]), guide=Path(profile_arguments[3])),
    )
    return database


def test_prepare_prints_what_the_three_separate_commands_print(
    runner: CliRunner,
    prepared: FakeSupabaseClient,
    settings: Settings,
    profile_arguments: list[str],
) -> None:
    assert settings.supabase_url
    started = runner.invoke(build_cli(), ["run", "start", "--trigger", "manual"])
    checked = runner.invoke(build_cli(), ["healthcheck"])
    applied = runner.invoke(build_cli(), ["profile", "apply", *profile_arguments])

    result = runner.invoke(build_cli(), ["run", "start", "--trigger", "manual", "--prepare"])

    assert result.exit_code == 0
    lines = printed_lines(result)
    assert lines[0].startswith("run ")
    assert lines[0].endswith("started · trigger manual")
    assert lines[1:] == [
        *printed_lines(started)[1:],
        *printed_lines(checked),
        *printed_lines(applied),
        "ready: yes",
    ]
    assert "configuration ok · database reachable · secret store ok" in lines
    assert "stage labels saved: 6" in lines
    assert any(line.startswith("guide written: ") for line in lines)
    running = [row for row in prepared.tables["run_logs"] if row["status"] == "running"]
    assert len(running) == 2


def test_prepare_with_a_failed_health_check_says_not_ready_and_leaves_the_profile_alone(
    runner: CliRunner,
    prepared: FakeSupabaseClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert settings.supabase_url
    attempted: list[str] = []

    def refuse(*_arguments: object, **_options: object) -> None:
        message = "the database did not answer"
        raise DatabaseUnavailableError(message)

    monkeypatch.setattr("tracker.cli.commands.system.probe_database", refuse)
    monkeypatch.setattr(
        "tracker.cli.commands.run.apply_profile", lambda: attempted.append("profile")
    )

    result = runner.invoke(build_cli(), ["run", "start", "--trigger", "refresh", "--prepare"])

    assert result.exit_code == 0
    lines = printed_lines(result)
    assert lines[0].endswith("started · trigger refresh")
    assert lines[-2:] == ["healthcheck failed · code=database_unavailable", "ready: no"]
    assert attempted == []
    assert [
        row["status"] for row in prepared.tables["run_logs"] if row["trigger"] == "refresh"
    ] == [RunStatus.RUNNING.value]


def test_prepare_carries_on_when_the_profile_cannot_be_applied(
    runner: CliRunner,
    prepared: FakeSupabaseClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert settings.supabase_url
    assert prepared.tables["run_logs"]

    def refuse() -> None:
        message = "the profile file names a stage twice"
        raise ValidationFailedError(message)

    monkeypatch.setattr("tracker.cli.commands.run.apply_profile", refuse)

    result = runner.invoke(build_cli(), ["run", "start", "--prepare"])

    assert result.exit_code == 0
    assert printed_lines(result)[-3:] == [
        "configuration ok · database reachable · secret store ok",
        "profile apply failed · code=validation_failed",
        "ready: yes",
    ]


def test_without_prepare_a_start_checks_nothing_and_applies_nothing(
    runner: CliRunner,
    database: FakeSupabaseClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert settings.supabase_url
    assert database.tables["run_logs"]
    called: list[str] = []
    monkeypatch.setattr("tracker.cli.commands.run.healthcheck", lambda: called.append("check"))
    monkeypatch.setattr("tracker.cli.commands.run.apply_profile", lambda: called.append("profile"))

    result = runner.invoke(build_cli(), ["run", "start"])

    assert result.exit_code == 0
    assert called == []
    lines = printed_lines(result)
    assert len(lines) == 2
    assert lines[0].endswith("started · trigger cloud")
    assert lines[1] == "time zone: UTC"


@pytest.mark.parametrize(("command", "option"), [("start", "--prepare"), ("finish", "--clean")])
def test_the_help_offers_the_folded_steps(runner: CliRunner, command: str, option: str) -> None:
    result = runner.invoke(build_cli(), ["run", command, "--help"])

    assert result.exit_code == 0
    # On GitHub Actions the help is printed in colour, and the colour codes sit
    # between the two dashes and the option's name.
    assert option in _COLOUR_CODES.sub("", result.output)


# --- run finish --clean: the work files removed in the same step ----------------


@pytest.fixture
def work(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A work directory as a day's run leaves it, standing in for the real one."""
    directory = tmp_path / "work"
    (directory / "batches").mkdir(parents=True)
    (directory / "batches" / "batch-0001.json").write_text("{}", encoding="utf-8")
    (directory / "summary.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(ai, "clean_work_directory", lambda: clean_work_directory(directory))
    return directory


def test_finish_with_clean_prints_what_the_two_separate_commands_print(
    runner: CliRunner,
    database: FakeSupabaseClient,
    settings: Settings,
    work: Path,
) -> None:
    assert settings.supabase_url
    started = runner.invoke(build_cli(), ["run", "start", "--trigger", "manual"])
    run_id = _printed_run_id(started.output)
    runner.invoke(build_cli(), ["run", "step", "--step", "assess", "--result", "success"])

    result = runner.invoke(build_cli(), ["run", "finish", "--clean"])

    assert result.exit_code == 0
    assert printed_lines(result) == [
        f"run {run_id} finished · status success",
        "2 files removed from the work directory",
    ]
    assert list(work.iterdir()) == []
    stored = [row for row in database.tables["run_logs"] if row["id"] == run_id]
    assert stored[0]["status"] == RunStatus.SUCCESS.value
    assert stored[0]["finished_at"] is not None


def test_a_cleaning_that_fails_is_printed_and_the_run_is_still_closed(
    runner: CliRunner,
    database: FakeSupabaseClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert settings.supabase_url
    started = runner.invoke(build_cli(), ["run", "start", "--trigger", "manual"])
    run_id = _printed_run_id(started.output)

    def refuse() -> None:
        message = "1 item(s) under the work directory could not be removed"
        raise WorkFileError(message)

    monkeypatch.setattr(ai, "clean_work_directory", refuse)

    result = runner.invoke(build_cli(), ["run", "finish", "--clean"])

    assert result.exit_code == 0
    assert printed_lines(result) == [
        f"run {run_id} finished · status failed",
        "ai clean failed · code=work_file_not_removed",
    ]
    stored = [row for row in database.tables["run_logs"] if row["id"] == run_id]
    assert stored[0]["finished_at"] is not None


def test_the_work_files_are_removed_even_when_the_run_cannot_be_closed(
    runner: CliRunner,
    database: FakeSupabaseClient,
    settings: Settings,
    work: Path,
) -> None:
    assert settings.supabase_url
    database.tables["run_logs"].clear()

    result = runner.invoke(build_cli(), ["run", "finish", "--clean"])

    assert result.exit_code != 0
    assert isinstance(result.exception, ValidationFailedError)
    assert printed_lines(result) == ["2 files removed from the work directory"]
    assert list(work.iterdir()) == []


def test_without_clean_a_finish_leaves_the_work_files(
    runner: CliRunner,
    database: FakeSupabaseClient,
    settings: Settings,
    work: Path,
) -> None:
    assert settings.supabase_url
    assert database.tables["run_logs"]
    runner.invoke(build_cli(), ["run", "start"])

    result = runner.invoke(build_cli(), ["run", "finish"])

    assert result.exit_code == 0
    assert len(printed_lines(result)) == 1
    assert (work / "summary.json").is_file()
    assert (work / "batches" / "batch-0001.json").is_file()
