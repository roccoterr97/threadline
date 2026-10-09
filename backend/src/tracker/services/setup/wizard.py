"""Runs the steps in order, skipping finished ones, and stops cleanly on a problem.

The set-up has two halves. The core steps are what the first morning e-mail
needs, and ``tracker setup`` runs them alone, ending with what happens next.
The extras (LinkedIn, the Refresh now button, the Claude cloud route) are run
together by ``tracker setup extras``, or one at a time by name.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from tracker.services.setup.context import SetupContext
from tracker.services.setup.first_run import FirstRun, workflow_page
from tracker.services.setup.models import Step, StepGroup, StepName
from tracker.services.setup.step_categories import CategoriesStep
from tracker.services.setup.step_cloud import CloudStep
from tracker.services.setup.step_dashboard import DashboardStep
from tracker.services.setup.step_database import DatabaseStep
from tracker.services.setup.step_github import GitHubStep
from tracker.services.setup.step_linkedin import LinkedInStep
from tracker.services.setup.step_login import LoginStep
from tracker.services.setup.step_mailbox import MailboxStep
from tracker.services.setup.step_microsoft import MicrosoftStep
from tracker.services.setup.step_refresh import RefreshStep
from tracker.services.setup.step_schedule import ScheduleStep
from tracker.services.setup.step_supabase import EncryptionStep, SupabaseStep
from tracker.services.setup.step_time_zone import TimeZoneStep
from tracker.services.setup.workflow_schedule import read_schedule
from tracker.shared.constants.github import FIRST_SUMMARY_MINUTES
from tracker.shared.errors import SetupStoppedError, TrackerError
from tracker.shared.logging import get_logger

_log = get_logger(__name__)

#: How the owner types the set-up, as every message names it.
_COMMAND: Final[str] = "uv run tracker setup"


def core_steps() -> tuple[Step, ...]:
    """The steps the first morning e-mail needs, in the order ``tracker setup`` runs them."""
    return (
        SupabaseStep(),
        EncryptionStep(),
        DatabaseStep(),
        LoginStep(),
        CategoriesStep(),
        TimeZoneStep(),
        MailboxStep(),
        MicrosoftStep(),
        DashboardStep(),
        ScheduleStep(),
        GitHubStep(),
    )


def extra_steps() -> tuple[Step, ...]:
    """The optional steps, in the order ``tracker setup extras`` runs them."""
    return (LinkedInStep(), RefreshStep(), CloudStep())


def default_steps() -> tuple[Step, ...]:
    """Every step: the core ones, then the extras."""
    return (*core_steps(), *extra_steps())


class SetupWizard:
    """Walks through the steps; running it again carries on where it stopped."""

    def __init__(self, ctx: SetupContext, steps: Sequence[Step]) -> None:
        """Bind the wizard to its context and steps.

        Args:
            ctx: The conversation, the ``.env`` file and the services.
            steps: The steps, in order.
        """
        self._ctx = ctx
        self._steps = tuple(steps)

    async def run_core(self) -> bool:
        """Run every core step that is not finished yet, then say what happens next.

        Returns:
            Whether every core step finished.
        """
        if not await self._run_group(StepGroup.CORE):
            return False
        _say_finish_line(self._ctx, self._first_run())
        return True

    async def run_extras(self) -> bool:
        """Run every extra step that is not finished yet.

        Returns:
            Whether every extra step finished.
        """
        return await self._run_group(StepGroup.EXTRAS)

    async def run_one(self, name: StepName) -> bool:
        """Run one step, even if it was finished before.

        Args:
            name: The step to run.

        Returns:
            Whether it finished.
        """
        step = next(step for step in self._steps if step.name is name)
        self._ctx.io.say(step.title)
        return await self._attempt(step, skip_when_done=False)

    async def _run_group(self, group: StepGroup) -> bool:
        """Run one half's unfinished steps in order, numbering them."""
        steps = [step for step in self._steps if step.name.group is group]
        for number, step in enumerate(steps, start=1):
            self._ctx.io.say("")
            self._ctx.io.say(f"Step {number} of {len(steps)}: {step.title}")
            if not await self._attempt(step, skip_when_done=True):
                return False
        return True

    async def _attempt(self, step: Step, *, skip_when_done: bool) -> bool:
        """Run one step, turning a problem into two plain lines.

        A full run names the full command to run again, since it skips the
        finished steps and carries on from the one that stopped; a single step
        names itself.
        """
        try:
            if skip_when_done and await step.is_done(self._ctx):
                self._ctx.io.say(f"Already done. To redo it: {_COMMAND} {step.name}")
                return True
            await step.run(self._ctx)
        except SetupStoppedError as error:
            _log.info("setup_stopped", step=step.name.value, detail=error.message)
            self._ctx.io.say(f"Stopped here: {error.message}.")
            again = _group_command(step)
            self._ctx.io.say(f"Run '{again}' again to carry on; what is done is kept.")
            return False
        except TrackerError as error:
            _log.warning("setup_step_stopped", step=step.name.value, code=error.code)
            self._ctx.io.say(f"Stopped: {error.message}.")
            self._ctx.io.say(_how_to_carry_on(step, full_run=skip_when_done))
            return False
        return True

    def _first_run(self) -> FirstRun | None:
        """How the GitHub step left the first run; ``None`` when it did not run here."""
        return next((step.first_run for step in self._steps if isinstance(step, GitHubStep)), None)


def _how_to_carry_on(step: Step, *, full_run: bool) -> str:
    """The one command to run after a stop, and what it does."""
    if full_run:
        return (
            f"Fix that, then run '{_group_command(step)}' again: finished steps are kept "
            "and it carries on from here."
        )
    return f"Fix that, then run '{_COMMAND} {step.name}' - finished steps are kept."


def _group_command(step: Step) -> str:
    """The command that runs the half of the set-up a step belongs to."""
    if step.name.group is StepGroup.EXTRAS:
        return f"{_COMMAND} {StepGroup.EXTRAS}"
    return _COMMAND


def _say_finish_line(ctx: SetupContext, first_run: FirstRun | None) -> None:
    """Say what happens now: the first run, the daily time, and how to add the extras."""
    io = ctx.io
    schedule = read_schedule(ctx.gateways.workflow.read())
    io.say("")
    io.say("Set-up done.")
    if first_run is not None and first_run.started:
        io.say("The first run is going on GitHub, so the first summary e-mail reaches you in")
        io.say(f"about {FIRST_SUMMARY_MINUTES} minutes.")
    else:
        page = first_run.page if first_run is not None else workflow_page(None)
        io.say(f"Start the first run at {page}:")
        io.say(f"the summary e-mail follows about {FIRST_SUMMARY_MINUTES} minutes later.")
    if schedule is not None:
        io.say(f"After that it comes every day at {schedule.describe()}.")
    else:
        io.say(f"After that it comes every day, at the time set by {_COMMAND} {StepName.SCHEDULE}.")
    io.say("Extras you can add any time: LinkedIn (EEA and Switzerland only), the dashboard's")
    io.say("Refresh now button, which also makes the daily run start on time, and the Claude")
    io.say(f"cloud route: {_COMMAND} {StepGroup.EXTRAS}")
