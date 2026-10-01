"""Step: the time of the daily run, written into the GitHub Actions workflow.

GitHub reads the time from two lines of ``.github/workflows/threadline-run.yml``:
a ``cron`` line and a ``timezone`` line, which lets GitHub follow the owner's
summer and winter time. The zone is ``OWNER_TIME_ZONE``, saved by the time-zone
step (and asked for here only when it is missing). The step rewrites those two
lines, shows what changed,
and only runs ``git`` when the owner says yes — GitHub sees a new time once it
is pushed.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from datetime import time
from typing import Final

from tracker.services.setup import values
from tracker.services.setup.context import SetupContext
from tracker.services.setup.github_copy import has_copy
from tracker.services.setup.models import StepName
from tracker.services.setup.step_time_zone import ask_time_zone, saved_time_zone
from tracker.shared.config import REPOSITORY_ROOT
from tracker.shared.constants.github import (
    DEFAULT_RUN_TIME,
    SCHEDULE_COMMIT_MESSAGE,
    WORKFLOW_FILE,
)
from tracker.shared.errors import ValidationFailedError

#: The workflow file as ``git`` and the owner see it, from the repository root.
WORKFLOW_PATH: Final[str] = WORKFLOW_FILE.relative_to(REPOSITORY_ROOT).as_posix()

_CRON_LINE: Final[re.Pattern[str]] = re.compile(r'^(?P<lead>\s*- cron: )"(?P<value>[^"]*)"$', re.M)
_ZONE_LINE: Final[re.Pattern[str]] = re.compile(
    r'^(?P<lead>\s*timezone: )"(?P<value>[^"]*)"$', re.M
)
#: git's way of naming a path from the top of the project, wherever it is typed.
_FROM_TOP: Final[str] = ":/"

_DAILY_CRON: Final[re.Pattern[str]] = re.compile(r"^(\d{1,2}) (\d{1,2}) \* \* \*$")


@dataclass(frozen=True, slots=True)
class Schedule:
    """When the daily run starts.

    Attributes:
        at: The time of day.
        zone: The IANA time zone it is read in.
    """

    at: time
    zone: str

    @property
    def cron(self) -> str:
        """The ``cron`` expression for every day at this time."""
        return f"{self.at.minute} {self.at.hour} * * *"

    def describe(self) -> str:
        """Say it the way a person would: ``07:00 (Europe/Rome)``."""
        return f"{self.at:%H:%M} ({self.zone})"


def read_schedule(text: str) -> Schedule | None:
    """Read the daily time the workflow holds.

    Args:
        text: The workflow file.

    Returns:
        The schedule, or ``None`` when the lines are missing or not a daily time.
    """
    cron, zone = _CRON_LINE.search(text), _ZONE_LINE.search(text)
    daily = _DAILY_CRON.match(cron.group("value")) if cron else None
    if daily is None or zone is None:
        return None
    return Schedule(time(int(daily.group(2)), int(daily.group(1))), zone.group("value"))


def write_schedule(text: str, schedule: Schedule) -> str:
    """Put a schedule into the workflow's ``cron`` and ``timezone`` lines.

    Args:
        text: The workflow file.
        schedule: The new time.

    Returns:
        The file with only those two lines changed.

    Raises:
        ValidationFailedError: If the file lacks either line.
    """
    if len(_CRON_LINE.findall(text)) != 1 or len(_ZONE_LINE.findall(text)) != 1:
        message = f"{WORKFLOW_PATH} no longer has exactly one cron line and one timezone line"
        raise ValidationFailedError(message)
    text = _CRON_LINE.sub(lambda found: f'{found.group("lead")}"{schedule.cron}"', text)
    return _ZONE_LINE.sub(lambda found: f'{found.group("lead")}"{schedule.zone}"', text)


class ScheduleStep:
    """Asks for the daily time and writes it into the workflow."""

    name = StepName.SCHEDULE
    title = "The daily time (GitHub Actions)"

    async def is_done(self, ctx: SetupContext) -> bool:
        """Never skipped: it offers the current time, so Enter keeps it."""
        return False

    async def run(self, ctx: SetupContext) -> None:
        """Ask the time, read it in the saved zone, rewrite the workflow, offer to push."""
        workflow = ctx.gateways.workflow
        before = workflow.read()
        current = read_schedule(before)
        schedule = Schedule(_ask_time(ctx, current), _zone(ctx))
        after = write_schedule(before, schedule)
        if after == before:
            ctx.io.say(f"The daily run already starts at {schedule.describe()}. Nothing to change.")
            return
        _show_changes(ctx, before, after)
        workflow.write(after)
        ctx.io.say(f"Saved {WORKFLOW_PATH}: every day at {schedule.describe()}.")
        ctx.io.say("GitHub may start it a few minutes late, most often on the hour.")
        _offer_push(ctx)


def _zone(ctx: SetupContext) -> str:
    """The owner's saved time zone; asked for now only when none is saved."""
    saved = saved_time_zone(ctx)
    if saved is None:
        return ask_time_zone(ctx)
    ctx.io.say(
        f"The time is read in your time zone, {saved}. "
        f"To change it: uv run tracker setup {StepName.TIME_ZONE}"
    )
    return saved


def _ask_time(ctx: SetupContext, current: Schedule | None) -> time:
    """Ask for the time of day, offering the one already set."""
    offered = f"{current.at:%H:%M}" if current else DEFAULT_RUN_TIME
    return ctx.ask_until_valid(
        lambda: ctx.io.ask(
            "What time should the daily run start? 24-hour clock, such as 07:00",
            default=offered,
        ),
        values.daily_time,
    )


def _show_changes(ctx: SetupContext, before: str, after: str) -> None:
    """Show the changed lines, the way git would."""
    ctx.io.say(f"The change to {WORKFLOW_PATH}:")
    diff = difflib.unified_diff(
        before.splitlines(), after.splitlines(), WORKFLOW_PATH, WORKFLOW_PATH, n=0, lineterm=""
    )
    for line in diff:
        ctx.io.say(f"  {line}")


def _offer_push(ctx: SetupContext) -> None:
    """Commit and push only after an explicit yes, and only when there is a copy to push to."""
    if not has_copy(ctx):
        _offer_commit(ctx)
        return
    ctx.io.say("GitHub uses the new time once this file is committed and pushed.")
    if ctx.io.confirm("Run git add, git commit and git push for this file now?", default=False):
        ctx.gateways.git.commit_and_push(WORKFLOW_PATH, SCHEDULE_COMMIT_MESSAGE)
        ctx.io.say("Committed and pushed. GitHub will use the new time from now on.")
        return
    _say_commit_lines(ctx)
    ctx.io.say("  git push")


def _offer_commit(ctx: SetupContext) -> None:
    """Without a copy on GitHub, keep the change in git so it travels with the copy."""
    ctx.io.say("This folder is not linked to a copy of yours on GitHub yet, so there is")
    ctx.io.say(
        f"nothing to push to. The next step ('uv run tracker setup {StepName.GITHUB}') "
        "makes that copy."
    )
    if ctx.io.confirm("Save this change in git now, so it goes up with your copy?", default=True):
        ctx.gateways.git.commit(WORKFLOW_PATH, SCHEDULE_COMMIT_MESSAGE)
        ctx.io.say("Saved in git. It goes to GitHub when your copy is made.")
        return
    _say_commit_lines(ctx)


def _say_commit_lines(ctx: SetupContext) -> None:
    """Print the git lines that save the workflow file, runnable from any folder."""
    ctx.io.say("When you are ready, run these in Terminal, in any folder of the project:")
    ctx.io.say(f"  git add {_FROM_TOP}{WORKFLOW_PATH}")
    ctx.io.say(f'  git commit -m "{SCHEDULE_COMMIT_MESSAGE}"')
