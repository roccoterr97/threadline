"""``tracker setup``: the guided set-up, all of it or one step."""

from __future__ import annotations

import asyncio
from typing import Annotated, Final

import typer

from tracker.cli.commands.doctor import print_doctor_report
from tracker.cli.setup_wiring import build_context
from tracker.infrastructure.supabase_platform import SupabasePlatform
from tracker.services.setup.models import StepName
from tracker.services.setup.wizard import SetupWizard, default_steps
from tracker.shared import config

#: Panel the root help groups this command under.
HELP_PANEL: Final[str] = "system"

StepArgument = Annotated[
    StepName | None,
    typer.Argument(
        help="Run only this step. Without it, every unfinished step runs in order.",
        show_default=False,
    ),
]


def register(cli: typer.Typer) -> None:
    """Attach the set-up to the root application.

    Args:
        cli: The root Typer application.
    """
    cli.command("setup", rich_help_panel=HELP_PANEL)(setup)


def setup(step: StepArgument = None) -> None:
    """Set up every connection, checking each one live before saving it.

    Steps: supabase, encryption, database, login, categories, timezone, mailbox,
    microsoft, linkedin, dashboard, schedule, github, refresh (the dashboard's
    Refresh now button), and cloud (the alternative to GitHub). Running it
    again carries on where it stopped.
    """
    finished = asyncio.run(_run(step))
    if not finished:
        raise typer.Exit(1)
    if step is None:
        typer.echo("")
        typer.echo("Final check of every connection:")
        config.reset_settings_cache()
        if not print_doctor_report():
            raise typer.Exit(1)


async def _run(step: StepName | None) -> bool:
    """Run the wizard on real clients."""
    async with SupabasePlatform() as platform:
        wizard = SetupWizard(build_context(config.ENV_FILE, platform), default_steps())
        if step is None:
            return await wizard.run_all()
        return await wizard.run_one(step)
