"""Entry point of the ``tracker`` command-line tool.

The root application holds no commands of its own: every group comes from a
module under :mod:`tracker.cli.commands`. Any error the application raises on
purpose leaves as one clean line — never a stack trace.
"""

from __future__ import annotations

import typer

from tracker.cli.discovery import register_commands
from tracker.shared.config import DEFAULT_PRODUCT_NAME, AppEnv, LogLevel, get_settings
from tracker.shared.constants.setup import CONFIGURATION_FIX
from tracker.shared.errors import ConfigurationError, TrackerError
from tracker.shared.logging import configure_logging, get_logger

_log = get_logger(__name__)

#: What the root help says after the product name.
_HELP_TAIL = "collect messages, assess them, report on them."

#: The plain line a command adds when it failed because a setting is missing or
#: wrong; the same fix the doctor prints.
_CONFIGURATION_PROBLEM = f"PROBLEM  A setting is missing or wrong. Fix: {CONFIGURATION_FIX}."


def build_cli() -> typer.Typer:
    """Build the root application with every discovered command attached.

    Returns:
        The Typer application.
    """
    cli = typer.Typer(help=_help_text(), no_args_is_help=True, add_completion=False)
    register_commands(cli)
    return cli


def main() -> None:
    """Run the command-line tool.

    A broken configuration is the one failure a newcomer meets before anything
    else works, so it also gets the doctor's plain fix line, on standard output.

    Raises:
        SystemExit: With status 1 when a command fails for a known reason.
    """
    level, app_env = _logging_preferences()
    configure_logging(level, app_env)
    try:
        build_cli()()
    except TrackerError as error:
        _log.error("command_failed", code=error.code, detail=error.message)
        if isinstance(error, ConfigurationError):
            typer.echo(_CONFIGURATION_PROBLEM)
        raise SystemExit(1) from error


def _help_text() -> str:
    """Build the root help line from the configured product name.

    The help must show even when the configuration is broken — that is when it
    is needed most — so a broken configuration falls back to the default name.

    Returns:
        The one-line description of the tool.
    """
    try:
        name = get_settings().product_name
    except ConfigurationError:
        name = DEFAULT_PRODUCT_NAME
    return f"{name}: {_HELP_TAIL}"


def _logging_preferences() -> tuple[LogLevel, AppEnv]:
    """Read the logging preferences, falling back when configuration is broken.

    Logging must work before configuration is validated, otherwise a missing
    variable would have nowhere to be reported. The command that needs the
    configuration raises the error itself a moment later.

    Returns:
        The log level and deployment to configure logging with.
    """
    try:
        settings = get_settings()
    except ConfigurationError:
        return LogLevel.INFO, AppEnv.DEVELOPMENT
    return settings.log_level, settings.app_env
