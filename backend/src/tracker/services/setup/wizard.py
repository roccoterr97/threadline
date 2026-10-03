"""Runs the steps in order, skipping finished ones, and stops cleanly on a problem."""

from __future__ import annotations

from collections.abc import Sequence

from tracker.services.setup.context import SetupContext
from tracker.services.setup.models import Step, StepName
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
from tracker.shared.errors import SetupStoppedError, TrackerError
from tracker.shared.logging import get_logger

_log = get_logger(__name__)


def default_steps() -> tuple[Step, ...]:
    """Every step, in the order a full set-up runs them."""
    return (
        SupabaseStep(),
        EncryptionStep(),
        DatabaseStep(),
        LoginStep(),
        CategoriesStep(),
        TimeZoneStep(),
        MailboxStep(),
        MicrosoftStep(),
        LinkedInStep(),
        DashboardStep(),
        ScheduleStep(),
        GitHubStep(),
        RefreshStep(),
        CloudStep(),
    )


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

    async def run_all(self) -> bool:
        """Run every step that is not finished yet.

        Returns:
            Whether every step finished.
        """
        total = len(self._steps)
        for number, step in enumerate(self._steps, start=1):
            self._ctx.io.say("")
            self._ctx.io.say(f"Step {number} of {total}: {step.title}")
            if not await self._attempt(step, skip_when_done=True):
                return False
        return True

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

    async def _attempt(self, step: Step, *, skip_when_done: bool) -> bool:
        """Run one step, turning a problem into two plain lines."""
        try:
            if skip_when_done and await step.is_done(self._ctx):
                self._ctx.io.say(f"Already done. To redo it: uv run tracker setup {step.name}")
                return True
            await step.run(self._ctx)
        except SetupStoppedError as error:
            _log.info("setup_stopped", step=step.name.value, detail=error.message)
            self._ctx.io.say(f"Stopped here: {error.message}.")
            self._ctx.io.say("Run 'uv run tracker setup' again to carry on; what is done is kept.")
            return False
        except TrackerError as error:
            _log.warning("setup_step_stopped", step=step.name.value, code=error.code)
            self._ctx.io.say(f"Stopped: {error.message}.")
            self._ctx.io.say(
                f"Fix that, then run 'uv run tracker setup {step.name}' - finished steps are kept."
            )
            return False
        return True
