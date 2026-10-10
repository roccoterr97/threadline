"""Step: choose the dashboard, save its address, and point Supabase's sign-in at it.

By default the owner uses Threadline's shared dashboard: one page for every
owner, with nothing to create and no key to paste. The data stays in the
owner's own Supabase project; a personal link tells the page which project to
open (see ``tracker.domain.dashboard_link``). The step shows that link and
opens it once.

The owner may publish their own copy on Netlify instead (``netlify_publish``),
which an owner who already has a Netlify site is offered first, so running the
step again publishes the newest dashboard to the same address. An owner who
hosts it elsewhere types its address, which is opened once before it is saved.
An express run takes the shared dashboard without asking, unless the owner
already has a Netlify site.
"""

from __future__ import annotations

from typing import Final

from tracker.domain.dashboard_link import DashboardAddress, connect_fragment, dashboard_address
from tracker.domain.supabase import AuthSettings
from tracker.services.setup import values
from tracker.services.setup.context import SetupContext
from tracker.services.setup.models import StepName
from tracker.services.setup.netlify_publish import SITE_ID, browser_settings, publish_on_netlify
from tracker.services.setup.supabase_session import full_access_needed, require_supabase_token
from tracker.shared.constants.dashboard import HOSTED_DASHBOARD_URL, LOGIN_WALL_STATUSES
from tracker.shared.constants.setup import SUPABASE_URL_CONFIGURATION_PAGE
from tracker.shared.errors import (
    SourceAuthError,
    SourceUnavailableError,
    ValidationFailedError,
)

ADDRESS: Final[str] = "DASHBOARD_BASE_URL"

#: The step that changes the dashboard, as typed after ``tracker setup``.
ADDRESS_STEP: Final[str] = StepName.DASHBOARD.value

#: First status that counts as "the page did not open".
FIRST_ERROR_STATUS: Final[int] = 400

_SUPABASE_URL: Final[str] = "SUPABASE_URL"
_PUBLISHABLE_KEY: Final[str] = "SUPABASE_ANON_KEY"


class DashboardStep:
    """Sets up the shared dashboard (or publishes the owner's own copy, or takes its address)."""

    name = StepName.DASHBOARD
    title = "Your dashboard"

    async def is_done(self, ctx: SetupContext) -> bool:
        """Done when the address is saved."""
        return ctx.env.get(ADDRESS) is not None

    async def run(self, ctx: SetupContext) -> None:
        """Choose the dashboard, save its address, point Supabase at it, then give the link.

        Raises:
            ValidationFailedError: If no dashboard is chosen at all, so a full
                set-up stops here and carries on from here next time.
        """
        ctx.io.say("Your dashboard is a private web page: open it on your computer or your phone.")
        address = await _chosen_address(ctx)
        link = _personal_link(ctx) if address == HOSTED_DASHBOARD_URL else None
        await _save(ctx, address)
        if link is not None:
            _give_personal_link(ctx, link)


def _personal_link(ctx: SetupContext) -> str:
    """The owner's personal link to the shared dashboard.

    Raises:
        ValidationFailedError: If the project address or the publishable key is
            missing or not one the browser may hold.
    """
    settings = browser_settings(ctx)
    fragment = connect_fragment(settings.supabase_url, settings.publishable_key)
    return DashboardAddress(HOSTED_DASHBOARD_URL, fragment).page()


def opening_link(ctx: SetupContext) -> str | None:
    """Where the owner opens the saved dashboard: the personal link for the shared one.

    Returns:
        The address to open, or ``None`` when none is saved yet.
    """
    address = dashboard_address(
        ctx.env.get(ADDRESS),
        ctx.env.get(_SUPABASE_URL) or "",
        ctx.env.get(_PUBLISHABLE_KEY) or "",
    )
    return None if address is None else address.page()


async def _chosen_address(ctx: SetupContext) -> str:
    """The shared dashboard, a newly published copy, or another host's address.

    An owner with a Netlify site is asked about republishing it first.
    """
    io = ctx.io
    if ctx.env.get(SITE_ID) is not None:
        if io.confirm("Publish the newest version of your dashboard on Netlify?", default=True):
            return await publish_on_netlify(ctx)
        if _shared_wanted(ctx):
            return HOSTED_DASHBOARD_URL
        return await _hosted_elsewhere(ctx)
    if ctx.session.express:
        io.say("You get Threadline's shared dashboard: nothing to create, and only you can")
        io.say(f"sign in to your data. Your own copy instead: uv run tracker setup {ADDRESS_STEP}")
        return HOSTED_DASHBOARD_URL
    if _shared_wanted(ctx):
        return HOSTED_DASHBOARD_URL
    if io.confirm(
        "Publish your own copy on Netlify instead (it needs a free Netlify account)?",
        default=True,
    ):
        return await publish_on_netlify(ctx)
    return await _hosted_elsewhere(ctx)


def _shared_wanted(ctx: SetupContext) -> bool:
    """Explain the shared dashboard and ask whether to use it."""
    io = ctx.io
    io.say("The simplest is Threadline's shared dashboard: nothing to create, no key to paste.")
    io.say("Everyone opens the same page, but your data stays in your own database,")
    io.say("and only you can sign in to it.")
    return io.confirm("Use the shared dashboard?", default=True)


def _give_personal_link(ctx: SetupContext, link: str) -> None:
    """Show the personal link, put it on the clipboard and open it once."""
    io = ctx.io
    io.say("Your personal link opens your dashboard on any computer or phone:")
    io.say(f"  {link}")
    io.say("Keep it. Every morning e-mail carries it too.")
    if io.copy(link):
        io.say("It is on your clipboard as well.")
    io.open_page(link)


async def _hosted_elsewhere(ctx: SetupContext) -> str:
    """Take the address of a dashboard published some other way, once it opens.

    Raises:
        ValidationFailedError: If it is not published anywhere yet.
    """
    io = ctx.io
    if not io.confirm("Do you publish it somewhere else instead?", default=False):
        message = (
            "no dashboard is chosen yet - run the step again and choose the shared "
            "dashboard (part 5 of the guide)"
        )
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
    if previous is not None:
        _say_what_else_to_update(ctx)


def _say_what_else_to_update(ctx: SetupContext) -> None:
    """Name the two steps that keep a copy of the old address."""
    ctx.io.say(
        f"The address changed: run 'uv run tracker setup {StepName.GITHUB}' so the daily run"
    )
    ctx.io.say(
        f"links to it, and 'uv run tracker setup {StepName.REFRESH}' again if you use Refresh now."
    )


async def point_supabase_at(ctx: SetupContext, address: str) -> None:
    """Make Supabase's sign-in links open the dashboard.

    Supabase sends the owner back to its Site URL after a sign-in, and only to
    addresses on its Redirect URLs list. Both are set through Supabase's
    Management API with the run's access token. The Site URL is replaced; the
    list is read first and the dashboard's address is added to it, so an
    address the owner already allows (a local one for testing, an older host)
    stays. When Supabase refuses or cannot be reached, or the owner prefers
    not to use a token, the page opens with the two values.

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
    """Set the Site URL and add the Redirect URL; ``False`` when that did not happen."""
    if (
        ctx.session.supabase_token is None
        and not ctx.session.express
        and not ctx.io.confirm(
            "Point Supabase's sign-in at it with a Supabase access token (used now, not saved)?",
            default=True,
        )
    ):
        return False
    entry = f"{address}/**"
    try:
        token = await require_supabase_token(ctx)
        with full_access_needed(ctx):
            known = await ctx.gateways.platform.redirect_urls(ref, token)
            urls = known if entry in known else (*known, entry)
            settings = AuthSettings(site_url=address, redirect_urls=urls)
            await ctx.gateways.platform.configure_auth(ref, token, settings)
    except (SourceAuthError, SourceUnavailableError) as error:
        ctx.io.say(f"Supabase would not change the sign-in addresses: {error.message}.")
        return False
    _say_redirect_change(ctx, entry, known)
    return True


def _say_redirect_change(ctx: SetupContext, entry: str, known: tuple[str, ...]) -> None:
    """Tell which Redirect URL was added, or that it was already there."""
    if entry in known:
        ctx.io.say(f"Supabase's redirect addresses already hold {entry}.")
        return
    ctx.io.say(f"Added {entry} to Supabase's redirect addresses.")
    if known:
        ctx.io.say("The ones you already had were left as they were.")


def _point_by_hand(ctx: SetupContext, ref: str, address: str) -> None:
    """Open the URL Configuration page with the two values to type."""
    io = ctx.io
    io.say("On the Supabase page that opens (URL Configuration):")
    io.say(f"  Site URL: {address}")
    io.say(f"  Redirect URLs: add {address}/**")
    io.open_page(SUPABASE_URL_CONFIGURATION_PAGE.format(ref=ref))
    io.pause("Once both are saved")
