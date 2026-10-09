"""Step: your time zone, and the name you go by. Both decide how dates read.

The time zone decides what "today" is for due dates and the summary, and the
daily run's time is read in it. The computer's own zone is offered, so keeping
it is usually enough. The name is optional: it helps only when your
addresses do not spell it (``jd123@`` rather than ``sam.rivera@``).

A new zone is also written into the GitHub Actions workflow's ``timezone``
line, so the daily run keeps starting at the owner's chosen hour, and into the
database, where the on-time morning start reads it.
"""

from __future__ import annotations

from typing import Final

from tracker.services.setup import values
from tracker.services.setup.context import SetupContext
from tracker.services.setup.daily_start import save_schedule_in_database
from tracker.services.setup.models import StepName
from tracker.services.setup.workflow_schedule import (
    WORKFLOW_PATH,
    Schedule,
    offer_push,
    read_schedule,
    show_changes,
    write_schedule,
)
from tracker.shared.errors import ValidationFailedError
from tracker.shared.time_zones import canonical_zone_name

OWNER_TIME_ZONE: Final[str] = "OWNER_TIME_ZONE"
OWNER_DISPLAY_NAME: Final[str] = "OWNER_DISPLAY_NAME"


class TimeZoneStep:
    """Asks for the owner's time zone and, optionally, their name."""

    name = StepName.TIME_ZONE
    title = "Your time zone"

    async def is_done(self, ctx: SetupContext) -> bool:
        """Done once a time zone is saved."""
        return ctx.env.get(OWNER_TIME_ZONE) is not None

    async def run(self, ctx: SetupContext) -> None:
        """Ask the zone, offering the computer's, then the optional name."""
        ctx.io.say("Dates are read in your time zone: what 'today' is, and when the daily")
        ctx.io.say("run starts. The one this computer uses is offered; keep it unless it is wrong.")
        zone = ask_time_zone(ctx)
        _follow_in_workflow(ctx, zone)
        _ask_display_name(ctx)


def ask_time_zone(ctx: SetupContext) -> str:
    """Ask for the owner's time zone and save it in ``.env``.

    Args:
        ctx: The set-up's context.

    Returns:
        The zone's name, such as ``Europe/Paris``.
    """
    saved = saved_time_zone(ctx)
    offered = saved or ctx.gateways.local_time_zone()
    zone = ctx.ask_until_valid(
        lambda: ctx.io.ask("Your time zone", default=offered), values.time_zone
    )
    if zone != saved:
        ctx.env.set(OWNER_TIME_ZONE, zone)
        ctx.io.say(f"Saved {OWNER_TIME_ZONE}={zone} in .env.")
    return zone


def saved_time_zone(ctx: SetupContext) -> str | None:
    """Read the saved time zone, putting it right if only its case is wrong.

    A name saved as ``europe/paris`` worked on a Mac but stops the daily run
    on GitHub, whose machines care about case.

    Args:
        ctx: The set-up's context.

    Returns:
        The zone as the time-zone database spells it, or ``None`` when none is
        saved or the saved one is not a zone at all.
    """
    saved = ctx.env.get(OWNER_TIME_ZONE)
    if saved is None:
        return None
    canonical = canonical_zone_name(saved)
    if canonical is not None and canonical != saved:
        ctx.env.set(OWNER_TIME_ZONE, canonical)
        ctx.io.say(f"Saved {OWNER_TIME_ZONE}={canonical} in .env, spelled the way GitHub needs.")
    return canonical


def _follow_in_workflow(ctx: SetupContext, zone: str) -> None:
    """Write the zone into the workflow's schedule, keeping its time of day.

    Nothing happens when there is no workflow file, it holds no daily time, or
    the time is already read in this zone. A workflow changed by hand beyond
    one daily time is left as it is, with a note: the zone is already saved.
    """
    workflow = ctx.gateways.workflow
    try:
        before = workflow.read()
    except FileNotFoundError:
        return
    current = read_schedule(before)
    if current is None or current.zone == zone:
        return
    schedule = Schedule(current.at, zone)
    try:
        after = write_schedule(before, schedule)
    except ValidationFailedError:
        ctx.io.say(
            f"{WORKFLOW_PATH} was changed by hand, so its schedule was left as it is."
            f" Change its timezone line to {zone} yourself."
        )
        return
    show_changes(ctx, before, after)
    workflow.write(after)
    ctx.io.say(f"Saved {WORKFLOW_PATH}: the daily run now starts at {schedule.describe()}.")
    save_schedule_in_database(ctx, schedule)
    offer_push(ctx)


def _ask_display_name(ctx: SetupContext) -> None:
    """Ask for the name the owner goes by; an empty answer keeps what is there."""
    saved = ctx.env.get(OWNER_DISPLAY_NAME)
    raw = ctx.io.ask(
        "Your name as people write it, such as Sam Rivera (optional; leave empty to skip)",
        default=saved,
    )
    name = " ".join(raw.split())
    if not name or name == saved:
        return
    ctx.env.set(OWNER_DISPLAY_NAME, name)
    ctx.io.say(f"Saved {OWNER_DISPLAY_NAME} in .env.")
