"""Step: your time zone, and the name you go by. Both decide how dates read.

The time zone decides what "today" is for due dates and the summary, and the
daily run's time is read in it. The computer's own zone is offered, so pressing
Return is usually enough. The name is optional: it helps only when your
addresses do not spell it (``jd123@`` rather than ``sam.rivera@``).
"""

from __future__ import annotations

from typing import Final

from tracker.services.setup import values
from tracker.services.setup.context import SetupContext
from tracker.services.setup.models import StepName
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
        ctx.io.say("run starts. The one this computer uses is offered; press Return to keep it.")
        ask_time_zone(ctx)
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


def _ask_display_name(ctx: SetupContext) -> None:
    """Ask for the name the owner goes by; Return keeps what is there."""
    saved = ctx.env.get(OWNER_DISPLAY_NAME)
    raw = ctx.io.ask(
        "Your name as people write it, such as Sam Rivera (optional, Return to skip)",
        default=saved,
    )
    name = " ".join(raw.split())
    if not name or name == saved:
        return
    ctx.env.set(OWNER_DISPLAY_NAME, name)
    ctx.io.say(f"Saved {OWNER_DISPLAY_NAME} in .env.")
