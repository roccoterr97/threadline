"""The collection commands: the help, the options, and one clean line on failure."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from typer.testing import CliRunner

from tracker.cli.commands.collect import _parse_since, _person_line
from tracker.cli.discovery import command_module_names
from tracker.cli.main import build_cli, main
from tracker.domain.enums import Channel
from tracker.services.identity.directory import DirectoryEntry
from tracker.shared.errors import ValidationFailedError


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_the_collect_module_is_discovered() -> None:
    assert "collect" in command_module_names()


def test_the_help_lists_the_collection_commands(runner: CliRunner) -> None:
    result = runner.invoke(build_cli(), ["--help"])

    assert result.exit_code == 0
    assert "collect" in result.output
    assert "microsoft" in result.output
    assert "people" in result.output


def test_the_collect_group_offers_both_sources_and_both_together(runner: CliRunner) -> None:
    result = runner.invoke(build_cli(), ["collect", "--help"])

    assert result.exit_code == 0
    for command in ("linkedin", "email", "all"):
        assert command in result.output


def test_the_microsoft_group_offers_the_one_time_sign_in(runner: CliRunner) -> None:
    result = runner.invoke(build_cli(), ["microsoft", "--help"])

    assert result.exit_code == 0
    assert "login" in result.output


def test_the_people_group_offers_list_merge_and_link(runner: CliRunner) -> None:
    result = runner.invoke(build_cli(), ["people", "--help"])

    assert result.exit_code == 0
    for command in ("list", "merge", "link"):
        assert command in result.output


@pytest.mark.parametrize(
    "command",
    [
        ["collect", "linkedin"],
        ["collect", "email"],
        ["collect", "all"],
        ["microsoft", "login"],
        ["people", "list"],
        ["people", "link"],
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


def test_a_since_date_is_read_as_the_start_of_that_day_in_utc() -> None:
    assert _parse_since("2026-09-01", UTC) == datetime(2026, 9, 1, tzinfo=UTC)
    assert _parse_since(None, UTC) is None


def test_a_since_date_starts_at_the_owners_midnight() -> None:
    # Midnight in Tokyo on 1 September is 15:00 UTC on 31 August.
    since = _parse_since("2026-09-01", ZoneInfo("Asia/Tokyo"))

    assert since == datetime(2026, 8, 31, 15, 0, tzinfo=UTC)


def test_a_since_value_that_is_not_a_date_is_refused_in_plain_words() -> None:
    with pytest.raises(ValidationFailedError, match="must be a date"):
        _parse_since("last tuesday", UTC)


def test_a_person_is_shown_with_channels_count_and_last_contact() -> None:
    entry = DirectoryEntry(
        full_name="Élodie Martin",
        channels=(Channel.EMAIL, Channel.LINKEDIN),
        message_count=7,
        last_contact_at=datetime(2026, 9, 12, 9, 0, tzinfo=UTC),
    )

    assert _person_line(entry) == "Élodie Martin · email+linkedin · 7 messages · 2026-09-12"


def test_a_person_with_no_message_yet_is_shown_too() -> None:
    entry = DirectoryEntry(
        full_name="Nobody Yet", channels=(), message_count=0, last_contact_at=None
    )

    assert _person_line(entry) == "Nobody Yet · - · 0 messages · never"
