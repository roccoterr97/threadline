"""Step: the time of the daily run, written into the GitHub Actions workflow.

GitHub reads the time from two lines of ``.github/workflows/threadline-run.yml``:
a ``cron`` line and a ``timezone`` line, which lets GitHub follow the owner's
summer and winter time. The zone is ``OWNER_TIME_ZONE``, saved by the time-zone
step (and asked for here only when it is missing). The step rewrites those two
lines, shows what changed,
and only runs ``git`` when the owner says yes — GitHub sees a new time once it
is pushed.

The same time and zone are copied into the database, where the on-time morning
start reads them (``daily_start.py``), so the two never drift apart.

An express run does not ask: it keeps the time already set, or 07:00, and says
how to change it.
"""

from __future__ import annotations

from datetime import time

from tracker.services.setup import values
from tracker.services.setup.context import SetupContext
from tracker.services.setup.daily_start import save_schedule_in_database
from tracker.services.setup.models import StepName
from tracker.services.setup.step_time_zone import ask_time_zone, saved_time_zone
from tracker.services.setup.workflow_schedule import (
    WORKFLOW_PATH,
    Schedule,
    offer_push,
    offer_unsent_change,
    read_schedule,
    show_changes,
    write_schedule,
)
from tracker.shared.constants.github import DEFAULT_RUN_TIME


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
            if ctx.session.express:
                ctx.io.say(f"To change the time: uv run tracker setup {StepName.SCHEDULE}")
            save_schedule_in_database(ctx, schedule)
            offer_unsent_change(ctx)
            return
        show_changes(ctx, before, after)
        workflow.write(after)
        ctx.io.say(f"Saved {WORKFLOW_PATH}: every day at {schedule.describe()}.")
        ctx.io.say("GitHub's own timer may start it late. With the on-time morning start")
        ctx.io.say(f"(uv run tracker setup {StepName.REFRESH}), Supabase starts it at this time.")
        save_schedule_in_database(ctx, schedule)
        offer_push(ctx)


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
    """Ask for the time of day, offering the one already set; an express run takes it."""
    offered = f"{current.at:%H:%M}" if current else DEFAULT_RUN_TIME
    if ctx.session.express:
        return values.daily_time(offered)
    return ctx.ask_until_valid(
        lambda: ctx.io.ask(
            "What time should the daily run start? 24-hour clock, such as 07:00",
            default=offered,
        ),
        values.daily_time,
    )
