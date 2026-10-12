"""Runs the steps in order, skipping finished ones, and stops cleanly on a problem.

The set-up has two halves. The core steps are what the first morning e-mail
needs, and ``tracker setup`` runs them and ends with what happens next,
naming the command that adds LinkedIn later: LinkedIn is left out of the full
run to keep it short, and the dashboard and the morning e-mail offer it once
the first summary is in. Only ``--ask-everything`` still asks about it at the
end. The extras (LinkedIn, Slack, the Refresh now button, the Claude cloud
route) are run together by ``tracker setup extras``, or one at a time by name.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from tracker.services.setup.claude_key_maker import make_while_project_starts
from tracker.services.setup.context import SetupContext
from tracker.services.setup.first_run import FirstRun, workflow_page
from tracker.services.setup.models import NotesWhatIsDone, Step, StepGroup, StepName
from tracker.services.setup.ports import SetupIO
from tracker.services.setup.setup_summary import say_summary
from tracker.services.setup.skipped_steps import forget_skip
from tracker.services.setup.step_categories import CategoriesStep
from tracker.services.setup.step_cloud import CloudStep
from tracker.services.setup.step_dashboard import DashboardStep, opening_link
from tracker.services.setup.step_database import DatabaseStep
from tracker.services.setup.step_github import GitHubStep
from tracker.services.setup.step_google_calendar import GoogleCalendarStep, say_calendar_tip
from tracker.services.setup.step_linkedin import LinkedInStep, wants_linkedin_now
from tracker.services.setup.step_login import LoginStep, login_address
from tracker.services.setup.step_mailbox import MailboxStep, ask_while_project_starts
from tracker.services.setup.step_microsoft import MicrosoftStep
from tracker.services.setup.step_refresh import RefreshStep
from tracker.services.setup.step_schedule import ScheduleStep
from tracker.services.setup.step_slack import SlackStep
from tracker.services.setup.step_supabase import EncryptionStep, SupabaseStep
from tracker.services.setup.step_teams import TeamsStep
from tracker.services.setup.step_telegram import TelegramStep
from tracker.services.setup.step_time_zone import TimeZoneStep
from tracker.services.setup.supabase_sign_in import say_sign_in_can_go
from tracker.services.setup.workflow_schedule import read_schedule
from tracker.shared.constants.github import FIRST_SUMMARY_MINUTES
from tracker.shared.errors import SetupStoppedError, TrackerError
from tracker.shared.logging import get_logger

_log = get_logger(__name__)

#: How the owner types the set-up, as every message names it.
_COMMAND: Final[str] = "uv run tracker setup"

#: The command that adds the extras.
_EXTRAS: Final[str] = f"{_COMMAND} {StepGroup.EXTRAS}"

#: The command that checks every connection, the daily run on GitHub included.
_DOCTOR: Final[str] = "uv run tracker doctor"


def core_steps() -> tuple[Step, ...]:
    """The steps the first morning e-mail needs, in the order ``tracker setup`` runs them.

    While Supabase starts a new project, the mailbox is asked for (its app
    password checked live and held in memory), then, if the project is still
    not up, the Claude key is made; the mailbox and GitHub steps use them
    once the database is ready.
    """
    return (
        SupabaseStep(meanwhile=(ask_while_project_starts, make_while_project_starts)),
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
    return (
        LinkedInStep(),
        GoogleCalendarStep(),
        TelegramStep(),
        SlackStep(),
        TeamsStep(),
        RefreshStep(),
        CloudStep(),
    )


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
        """Run every core step that is not finished yet, then say what is next.

        Returns:
            Whether every core step finished. LinkedIn is not one of them: with
            ``--ask-everything`` it is offered here, and when it stops, it says
            how to carry on, and the run still ends as done.
        """
        if not await self._run_group(StepGroup.CORE):
            return False
        linkedin_connected = await self._offer_linkedin()
        _say_finish_line(self._ctx, self._first_run(), linkedin_connected=linkedin_connected)
        say_sign_in_can_go(self._ctx)
        return True

    async def run_extras(self) -> bool:
        """Run every extra step that is not finished yet.

        Returns:
            Whether every extra step finished.
        """
        return self._ended(await self._run_group(StepGroup.EXTRAS))

    async def run_one(self, name: StepName) -> bool:
        """Run one step, even if it was finished before.

        Args:
            name: The step to run.

        Returns:
            Whether it finished.
        """
        step = next(step for step in self._steps if step.name is name)
        # Asked for by name, a step skipped on an earlier run asks again.
        forget_skip(self._ctx, name)
        self._ctx.session.named_step = name
        self._ctx.io.say(step.title)
        return self._ended(await self._attempt(step, skip_when_done=False))

    def _ended(self, finished: bool) -> bool:
        """After a finished run, say the Supabase sign-in may be deleted; pass the result on."""
        if finished:
            say_sign_in_can_go(self._ctx)
        return finished

    async def _run_group(self, group: StepGroup) -> bool:
        """Run one half's unfinished steps in order, numbering them.

        An express run leaves the numbered titles out: most of its steps ask
        nothing, and the ones that do say what they need in their own words.
        """
        steps = [step for step in self._steps if step.name.group is group]
        for number, step in enumerate(steps, start=1):
            self._ctx.detail("")
            self._ctx.detail(f"Step {number} of {len(steps)}: {step.title}")
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
                self._ctx.detail(f"Already done. To redo it: {_COMMAND} {step.name}")
                _say_done_note(self._ctx, step)
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

    async def _offer_linkedin(self) -> bool:
        """With ``--ask-everything``, ask once whether to connect LinkedIn now.

        A full run without it never asks: the finish line names the command,
        and the dashboard and the morning e-mail offer it later.

        Returns:
            Whether LinkedIn is connected at the end.
        """
        step = next((step for step in self._steps if step.name is StepName.LINKEDIN), None)
        if step is None:
            return False
        if await step.is_done(self._ctx):
            return True
        if self._ctx.session.express or not wants_linkedin_now(self._ctx):
            return False
        self._ctx.io.say(step.title)
        await self._attempt(step, skip_when_done=False)
        return await step.is_done(self._ctx)

    def _first_run(self) -> FirstRun | None:
        """How the GitHub step left the first run; ``None`` when it did not run here."""
        return next((step.first_run for step in self._steps if isinstance(step, GitHubStep)), None)


def _say_done_note(ctx: SetupContext, step: Step) -> None:
    """Repeat what a finished step left, for a step that has something to repeat."""
    note = step.done_note(ctx) if isinstance(step, NotesWhatIsDone) else None
    if note is not None:
        ctx.detail(note)


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


def _say_finish_line(
    ctx: SetupContext, first_run: FirstRun | None, *, linkedin_connected: bool
) -> None:
    """Say what happens now: the dashboard, the first run, the choices, and the extras.

    Every choice is listed with the command that changes it (``setup_summary``).
    """
    io = ctx.io
    schedule = read_schedule(ctx.gateways.workflow.read())
    run = first_run if first_run is not None else FirstRun(started=False, page=workflow_page(None))
    login = login_address(ctx)
    when = f"every day at {schedule.describe()}" if schedule is not None else "every day"
    if schedule is None:
        when += f", at the time set by {_COMMAND} {StepName.SCHEDULE}"
    io.say("")
    io.say("Set-up done.")
    _say_how_to_sign_in(ctx, login)
    _say_first_run(io, run, when)
    if not run.summary_by_email:
        _say_no_email(io)
    say_summary(ctx, login)
    say_calendar_tip(ctx)
    _say_extras(io, linkedin_connected=linkedin_connected)


def _say_extras(io: SetupIO, *, linkedin_connected: bool) -> None:
    """Name the extras still to add, with LinkedIn's own line while it is not connected."""
    if not linkedin_connected:
        io.say(f"LinkedIn can be added later: {_COMMAND} {StepName.LINKEDIN} (about 5 minutes).")
        io.say("It works if your LinkedIn profile is located in the EEA or Switzerland.")
    io.say("Extras any time: Google Calendar, Telegram, Slack, Teams chats, the Refresh now")
    io.say(f"button (it also starts the daily run on time), the Claude cloud route: {_EXTRAS}")


def _say_how_to_sign_in(ctx: SetupContext, login: str | None) -> None:
    """Name the dashboard's address and the one address that can sign in to it.

    An express run, which did not show the personal link earlier, also puts it
    on the clipboard and opens it now that the set-up is done.
    """
    address = opening_link(ctx)
    if address is None:
        return
    if ctx.session.express and ctx.io.copy(address):
        ctx.io.say(f"Your dashboard (keep this link; it is on your clipboard): {address}")
    else:
        ctx.io.say(f"Your dashboard: {address}")
    if login is None:
        ctx.io.say("Sign in there with the address you gave for the dashboard login: a sign-in")
        ctx.io.say("link is e-mailed to it.")
    else:
        ctx.io.say(f"Sign in there with {login}: a sign-in link is e-mailed to that address.")
    if ctx.session.express:
        ctx.io.open_page(address)


def _say_first_run(io: SetupIO, run: FirstRun, when: str) -> None:
    """Say how the first run was left and what comes when, promising an e-mail only when one can.

    The GitHub step already said a started run is going, and when its e-mail
    comes. It is not waited for: when it stops, GitHub e-mails the owner and
    ``tracker doctor`` says why.
    """
    if run.needs_claude_key:
        io.say("The first run is not started yet: GitHub still needs your Claude key.")
        io.say("Run 'claude setup-token' in a new terminal window, then run")
        io.say(f"'{_COMMAND} {StepName.GITHUB}' and paste the key.")
    elif not run.started:
        io.say(f"Start the first run at {run.page}:")
        first = "the summary e-mail follows" if run.summary_by_email else "the dashboard fills"
        io.say(f"{first} about {FIRST_SUMMARY_MINUTES} minutes later.")
    if run.summary_by_email:
        io.say(f"After the first one, the summary e-mail comes {when}.")
    else:
        io.say(f"After the first run, the dashboard is updated {when}.")
    if run.started:
        io.say(f"If a run stops with a problem, GitHub e-mails you; '{_DOCTOR}' says why.")


def _say_no_email(io: SetupIO) -> None:
    """Say plainly that no summary e-mail will come, and the two ways to get one."""
    io.say("No summary e-mail will come yet: GitHub sends it only from a mailbox with an app")
    io.say(f"password. Add one with '{_COMMAND} {StepName.MAILBOX}' and then")
    io.say(f"'{_COMMAND} {StepName.GITHUB}', or use the Claude cloud route:")
    io.say(f"{_COMMAND} {StepGroup.EXTRAS}")
