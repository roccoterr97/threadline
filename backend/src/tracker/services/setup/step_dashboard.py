"""Step 7: the published dashboard's address."""

from __future__ import annotations

from typing import Final

from tracker.services.setup import values
from tracker.services.setup.context import SetupContext
from tracker.services.setup.models import StepName
from tracker.shared.constants.setup import SUPABASE_URL_CONFIGURATION_PAGE
from tracker.shared.errors import ValidationFailedError

ADDRESS: Final[str] = "DASHBOARD_BASE_URL"

#: Statuses a page answers when it is behind a Vercel login.
LOGIN_WALL_STATUSES: Final[frozenset[int]] = frozenset({401, 403})

#: First status that counts as "the page did not open".
FIRST_ERROR_STATUS: Final[int] = 400


class DashboardStep:
    """Saves the dashboard address once it opens, then points Supabase at it."""

    name = StepName.DASHBOARD
    title = "Dashboard address"

    async def is_done(self, ctx: SetupContext) -> bool:
        """Done when the address is saved."""
        return ctx.env.get(ADDRESS) is not None

    async def run(self, ctx: SetupContext) -> None:
        """Ask for the address, open it once, save it, then set Supabase's Site URL."""
        io = ctx.io
        io.say("The dashboard is published on Vercel (the guide, part 7, shows how).")
        io.say("The morning e-mail links to it once its address is saved here.")
        if not io.confirm("Is the dashboard published already?", default=False):
            io.say("Skipped. Run 'uv run tracker setup dashboard' once it is published.")
            return
        address = await ctx.ask_until_accepted(
            lambda: io.ask("Production address from Vercel's Domains tab (https://...)"),
            lambda raw: _check_address(ctx, raw),
        )
        ctx.write(ADDRESS, address)
        _point_supabase_at(ctx, address)


async def _check_address(ctx: SetupContext, raw: str) -> str:
    """Open the address once and refuse one that does not show the dashboard."""
    address = values.web_address(raw)
    status = await ctx.gateways.status_of(address)
    if status in LOGIN_WALL_STATUSES:
        message = (
            "that address asks for a Vercel login - use the production address "
            "listed in the project's Domains tab"
        )
        raise ValidationFailedError(message)
    if status >= FIRST_ERROR_STATUS:
        message = f"that address answered status {status}"
        raise ValidationFailedError(message)
    return address


def _point_supabase_at(ctx: SetupContext, address: str) -> None:
    """Guide the two Supabase settings that make the login link land there."""
    io = ctx.io
    ref = values.project_ref(ctx.require("SUPABASE_URL", StepName.SUPABASE))
    io.say("Last, on the Supabase page that opens (URL Configuration):")
    io.say(f"  Site URL: {address}")
    io.say(f"  Redirect URLs: add {address}/**")
    io.open_page(SUPABASE_URL_CONFIGURATION_PAGE.format(ref=ref))
    io.pause("Once both are saved")
