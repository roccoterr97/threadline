"""``tracker doctor``: check every connection, live, and say what to fix."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Final

import typer

from tracker.cli.doctor_wiring import render, run_doctor

#: Panel the root help groups this command under.
HELP_PANEL: Final[str] = "system"


def register(cli: typer.Typer) -> None:
    """Attach the doctor to the root application.

    Args:
        cli: The root Typer application.
    """
    cli.command("doctor", rich_help_panel=HELP_PANEL)(doctor)


def doctor() -> None:
    """Check every connection, one line each, with what to do about any problem."""
    if not print_doctor_report():
        raise typer.Exit(1)


def print_doctor_report(say: Callable[[str], None] = typer.echo) -> bool:
    """Run every check, show one line per check, and say whether all passed.

    Args:
        say: Shows one line; the terminal unless the set-up page is open.

    Returns:
        ``True`` when no check found a problem.
    """
    report = asyncio.run(run_doctor())
    for line in render(report):
        say(line)
    return report.healthy
