"""Step: publish the dashboard, save its address, and point Supabase's sign-in at it.

The dashboard is published on Netlify, for free, with nothing to install: the
set-up downloads the ready-made dashboard, adds the project's two public
values and uploads it with a token the owner pastes (see ``netlify_publish``).
Running the step again publishes the newest dashboard to the same address.
An owner who hosts it elsewhere types its address instead, which is opened
once before it is saved.
"""

from __future__ import annotations

from typing import Final

from tracker.domain.supabase import AuthSettings
from tracker.services.setup import values
from tracker.services.setup.context import SetupContext
from tracker.services.setup.models import StepName
from tracker.services.setup.netlify_publish import SITE_ID, publish_on_netlify
from tracker.services.setup.supabase_session import require_supabase_token
from tracker.shared.constants.setup import SUPABASE_URL_CONFIGURATION_PAGE
from tracker.shared.errors import (
    SourceAuthError,
    SourceRequestRejectedError,
    ValidationFailedError,
)

ADDRESS: Final[str] = "DASHBOARD_BASE_URL"

#: Statuses a page answers when it is behind a host's login (a Vercel preview, say).
LOGIN_WALL_STATUSES: Final[frozenset[int]] = frozenset({401, 403})

#: First status that counts as "the page did not open".
FIRST_ERROR_STATUS: Final[int] = 400


class DashboardStep:
    """Publishes the dashboard on Netlify (or takes the address of another host)."""

    name = StepName.DASHBOARD
    title = "Your dashboard"

    async def is_done(self, ctx: SetupContext) -> bool:
        """Done when the address is saved."""
        return ctx.env.get(ADDRESS) is not None

    async def run(self, ctx: SetupContext) -> None:
        """Publish it (or take another host's address), save it, then point Supabase at it.

        Raises:
            ValidationFailedError: If the dashboard is not published at all, so a
                full set-up stops here and carries on from here next time.
        """
        io = ctx.io
        io.say("Your dashboard is a private web page: open it on your computer or your phone.")
        io.say("It is published on Netlify, free, and only you can sign in to it.")
        republish = ctx.env.get(SITE_ID) is not None
        question = (
            "Publish the newest version of your dashboard on Netlify?"
            if republish
            else "Publish it on Netlify now?"
        )
        if io.confirm(question, default=True):
            address = await publish_on_netlify(ctx)
        else:
            address = await _hosted_elsewhere(ctx)
        await _save(ctx, address)


async def _hosted_elsewhere(ctx: SetupContext) -> str:
    """Take the address of a dashboard published some other way, once it opens.

    Raises:
        ValidationFailedError: If it is not published anywhere yet.
    """
    io = ctx.io
    if not io.confirm("Do you publish it somewhere else instead?", default=False):
        message = "the dashboard is not published yet - publish it first (part 5 of the guide)"
        raise ValidationFailedError(message)
    return await ctx.ask_until_accepted(
        lambda: io.ask("The dashboard's address (https://...)"),
        lambda raw: _check_address(ctx, raw),
    )


async def _check_address(ctx: SetupContext, raw: str) -> str:
    """Open the address once and refuse one that does not show the dashboard."""
    address = values.web_address(raw)
    status = await ctx.gateways.status_of(address)
    if status in LOGIN_WALL_STATUSES:
        message = (
            "that address asks for a login - use the one that opens without it "
            "(on Vercel, the production address in the project's Domains tab)"
        )
        raise ValidationFailedError(message)
    if status >= FIRST_ERROR_STATUS:
        message = f"that address answered status {status}"
        raise ValidationFailedError(message)
    return address


async def _save(ctx: SetupContext, address: str) -> None:
    """Save the address; a new one also needs Supabase's sign-in pointed at it."""
    previous = ctx.env.get(ADDRESS)
    if not ctx.write(ADDRESS, address):
        return
    if previous == address:
        ctx.io.say("Its address has not changed, so Supabase needs nothing new.")
        return
    await point_supabase_at(ctx, address)


async def point_supabase_at(ctx: SetupContext, address: str) -> None:
    """Make Supabase's sign-in links open the dashboard.

    Supabase sends the owner back to its Site URL after a sign-in, and only to
    addresses on its Redirect URLs list. Both are set through Supabase's
    Management API with the run's access token. The list is replaced, not
    added to: the project belongs to one owner and one dashboard, so an older
    address of that dashboard is rightly dropped. When Supabase refuses, or
    the owner prefers not to use a token, the page opens with the two values.

    Args:
        ctx: The conversation, the ``.env`` file and the services.
        address: The dashboard's address.
    """
    ref = values.project_ref(ctx.require("SUPABASE_URL", StepName.SUPABASE))
    if await _pointed_through_the_api(ctx, ref, address):
        ctx.io.say("Supabase's sign-in links now open your dashboard.")
        return
    _point_by_hand(ctx, ref, address)


async def _pointed_through_the_api(ctx: SetupContext, ref: str, address: str) -> bool:
    """Set the Site URL and Redirect URLs; ``False`` when that did not happen."""
    if ctx.session.supabase_token is None and not ctx.io.confirm(
        "Point Supabase's sign-in at it with a Supabase access token (used now, not saved)?",
        default=True,
    ):
        return False
    settings = AuthSettings(site_url=address, redirect_urls=(f"{address}/**",))
    try:
        token = await require_supabase_token(ctx)
        await ctx.gateways.platform.configure_auth(ref, token, settings)
    except (SourceAuthError, SourceRequestRejectedError) as error:
        ctx.io.say(f"Supabase would not change the sign-in addresses: {error.message}.")
        return False
    return True


def _point_by_hand(ctx: SetupContext, ref: str, address: str) -> None:
    """Open the URL Configuration page with the two values to type."""
    io = ctx.io
    io.say("On the Supabase page that opens (URL Configuration):")
    io.say(f"  Site URL: {address}")
    io.say(f"  Redirect URLs: add {address}/**")
    io.open_page(SUPABASE_URL_CONFIGURATION_PAGE.format(ref=ref))
    io.pause("Once both are saved")
