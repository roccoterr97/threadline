"""Command discovery, the help text, and one clean line when something is wrong."""

from __future__ import annotations

import pytest
import typer
from typer.testing import CliRunner

from tracker.cli.discovery import command_module_names, register_commands
from tracker.cli.main import build_cli, main
from tracker.shared.config import DEFAULT_PRODUCT_NAME, reset_settings_cache
from tracker.shared.errors import ConfigurationError


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_command_modules_are_discovered() -> None:
    assert "system" in command_module_names()


def test_every_discovered_module_is_registered() -> None:
    cli = typer.Typer()

    registered = register_commands(cli)

    assert registered == command_module_names()


def test_a_module_without_register_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    from tracker.cli import discovery

    monkeypatch.setattr(discovery, "command_module_names", lambda: ("clock",))
    monkeypatch.setattr(discovery, "COMMAND_PACKAGE", "tracker.shared")

    with pytest.raises(ConfigurationError, match="does not expose"):
        discovery.register_commands(typer.Typer())


def test_help_lists_the_system_commands(runner: CliRunner) -> None:
    result = runner.invoke(build_cli(), ["--help"])

    assert result.exit_code == 0
    assert "system" in result.output
    assert "healthcheck" in result.output
    assert "sample" in result.output


def test_help_names_the_default_product_without_configuration(runner: CliRunner) -> None:
    result = runner.invoke(build_cli(), ["--help"])

    assert result.exit_code == 0
    assert DEFAULT_PRODUCT_NAME in result.output


@pytest.mark.usefixtures("valid_environment")
def test_help_names_the_configured_product(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PRODUCT_NAME", "Weekly Desk")
    reset_settings_cache()

    result = runner.invoke(build_cli(), ["--help"])

    assert "Weekly Desk" in result.output


def test_sample_group_offers_load_and_clear(runner: CliRunner) -> None:
    result = runner.invoke(build_cli(), ["sample", "--help"])

    assert result.exit_code == 0
    assert "load" in result.output
    assert "clear" in result.output


def test_healthcheck_without_configuration_fails_on_one_line(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("sys.argv", ["tracker", "healthcheck"])

    with pytest.raises(SystemExit) as raised:
        main()

    assert raised.value.code == 1
    errors = capsys.readouterr().err.strip().splitlines()
    assert len(errors) == 1
    assert "configuration_invalid" in errors[0]
    assert "Traceback" not in errors[0]
