"""The daily run's time in the GitHub Actions workflow: reading, rewriting, saving in git.

GitHub reads the time from two lines of ``.github/workflows/threadline-run.yml``:
a ``cron`` line and a ``timezone`` line, which lets GitHub follow the owner's
summer and winter time. Both the schedule step and the time-zone step change
them, show what changed, and run ``git`` only when the owner says yes, or
without asking in an express run, where yes is the usual answer.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from datetime import time
from typing import Final

from tracker.services.setup.context import SetupContext
from tracker.services.setup.github_copy import has_copy
from tracker.services.setup.models import StepName
from tracker.shared.config import REPOSITORY_ROOT
from tracker.shared.constants.github import SCHEDULE_COMMIT_MESSAGE, WORKFLOW_FILE
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


def show_changes(ctx: SetupContext, before: str, after: str) -> None:
    """Show the changed lines, the way git would; an express run leaves them out."""
    if ctx.session.express:
        return
    ctx.io.say(f"The change to {WORKFLOW_PATH}:")
    diff = difflib.unified_diff(
        before.splitlines(), after.splitlines(), WORKFLOW_PATH, WORKFLOW_PATH, n=0, lineterm=""
    )
    for line in diff:
        ctx.io.say(f"  {line}")


def offer_push(ctx: SetupContext, *, committed: bool = False) -> None:
    """Commit and push only after an explicit yes, and only when there is a copy to push to.

    Args:
        ctx: The set-up's context.
        committed: Whether the change is already committed, so only a push is left.
    """
    if not has_copy(ctx):
        _offer_commit(ctx)
        return
    ctx.io.say("GitHub uses the new time once this file is committed and pushed.")
    if ctx.session.express or ctx.io.confirm(
        "Send the new time to your copy on GitHub now?", default=True
    ):
        if committed:
            ctx.gateways.git.push()
        else:
            ctx.gateways.git.commit_and_push(WORKFLOW_PATH, SCHEDULE_COMMIT_MESSAGE)
        ctx.io.say("Committed and pushed. GitHub will use the new time from now on.")
        return
    if not committed:
        _say_commit_lines(ctx)
    ctx.io.say("  git push")


def offer_unsent_change(ctx: SetupContext) -> None:
    """Offer again a time saved on this computer that GitHub does not have yet.

    A push that stopped, or a no, leaves the workflow file changed here while
    GitHub keeps the old time; running the step again would otherwise find
    nothing to change and never offer it. Does nothing when GitHub is up to date.

    Args:
        ctx: The set-up's context.
    """
    git = ctx.gateways.git
    uncommitted = git.has_uncommitted(WORKFLOW_PATH)
    if not uncommitted and not (has_copy(ctx) and git.has_unpushed(WORKFLOW_PATH)):
        return
    ctx.io.say("This computer has your daily time, but GitHub does not have this time yet.")
    offer_push(ctx, committed=not uncommitted)


def _offer_commit(ctx: SetupContext) -> None:
    """Without a copy on GitHub, keep the change in git so it travels with the copy."""
    ctx.io.say("This folder is not linked to a copy of yours on GitHub yet, so there is")
    ctx.io.say(
        f"nothing to push to. The GitHub step ('uv run tracker setup {StepName.GITHUB}') "
        "makes that copy."
    )
    if ctx.session.express or ctx.io.confirm(
        "Save this change in git now, so it goes up with your copy?", default=True
    ):
        ctx.gateways.git.commit(WORKFLOW_PATH, SCHEDULE_COMMIT_MESSAGE)
        ctx.io.say("Saved in git. It goes to GitHub when your copy is made.")
        return
    _say_commit_lines(ctx)


def _say_commit_lines(ctx: SetupContext) -> None:
    """Print the git lines that save the workflow file, runnable from any folder."""
    ctx.io.say("When you are ready, run these in a terminal, in any folder of the project:")
    ctx.io.say(f"  git add {_FROM_TOP}{WORKFLOW_PATH}")
    ctx.io.say(f'  git commit -m "{SCHEDULE_COMMIT_MESSAGE}"')
