"""Step 4: the first dashboard login, and switching off sign-ups.

Sign-ups are switched off through Supabase's Management API with this run's
access token; the settings page is opened only when Supabase refuses that.
"""

from __future__ import annotations

from pydantic import SecretStr

from tracker.domain.supabase import AuthSettings
from tracker.services.setup import values
from tracker.services.setup.context import SetupContext
from tracker.services.setup.models import StepName
from tracker.services.setup.supabase_session import full_access_needed, require_supabase_token
from tracker.shared.constants.setup import (
    SIGNUP_CHECK_ATTEMPTS,
    SIGNUP_CHECK_WAIT_SECONDS,
    SUPABASE_SIGN_IN_PAGE,
)
from tracker.shared.errors import (
    DatabaseUnavailableError,
    SourceAuthError,
    SourceUnavailableError,
    ValidationFailedError,
)
from tracker.shared.logging import get_logger

_log = get_logger(__name__)


class LoginStep:
    """Creates your dashboard login and records it as the only owner."""

    name = StepName.LOGIN
    title = "Your dashboard login"

    async def is_done(self, ctx: SetupContext) -> bool:
        """Done when somebody is recorded as the owner."""
        return bool(ctx.admin().owner_ids())

    async def run(self, ctx: SetupContext) -> None:
        """Create the login (or find it), record it, then check sign-ups are off."""
        io = ctx.io
        io.say("You sign in to the dashboard with a link Supabase e-mails to you.")
        io.say("Supabase's free e-mail only reaches the members of your Supabase account,")
        io.say("so use the address you signed up to Supabase with.")
        email = ctx.ask_until_valid(
            lambda: io.ask("E-mail address for the dashboard", default=_first_owner_address(ctx)),
            values.email_address,
        )
        admin = ctx.admin()
        user_id = admin.create_confirmed_user(email) or admin.find_user_id(email)
        if user_id is None:
            message = "Supabase says this login exists but could not find it - try again"
            raise ValidationFailedError(message)
        admin.add_owner(user_id)
        io.say(f"{email} can now sign in to the dashboard, and nobody else can read it.")
        await _switch_off_signups(ctx)


def login_address(ctx: SetupContext) -> str | None:
    """The address the dashboard login was made for, read back from Supabase.

    It is not kept in ``.env``, so it is asked for afresh; a set-up that is
    carried on later, or was finished before, still names the right address.

    Args:
        ctx: The set-up's context.

    Returns:
        The owner login's address, or ``None`` when Supabase could not say.
    """
    try:
        admin = ctx.admin()
        addresses = (admin.user_email(user_id) for user_id in admin.owner_ids())
        return next((address for address in addresses if address), None)
    except (DatabaseUnavailableError, SourceAuthError) as error:
        _log.warning("login_address_unavailable", code=error.code)
        return None


def _first_owner_address(ctx: SetupContext) -> str | None:
    """Offer the first of your own addresses as the default answer."""
    saved = ctx.env.get("OWNER_EMAIL_ADDRESSES")
    return saved.split(",")[0].strip() if saved else None


async def _signups_disabled(ctx: SetupContext) -> bool:
    """Read the project's public settings."""
    url = ctx.require("SUPABASE_URL", StepName.SUPABASE)
    key = SecretStr(ctx.require("SUPABASE_ANON_KEY", StepName.SUPABASE))
    return await ctx.gateways.platform.signups_disabled(url, key)


async def _switch_off_signups(ctx: SetupContext) -> None:
    """Make sure strangers cannot create a login: through the API, or by hand if refused."""
    io = ctx.io
    if await _signups_disabled(ctx):
        io.say("Sign-ups are switched off: nobody else can create a login.")
        return
    io.say("Sign-ups are still open, so they are switched off now.")
    if await _switched_off_through_the_api(ctx) and await _signups_off_once_applied(ctx):
        io.say("Sign-ups are now switched off: nobody else can create a login.")
        return
    _guide_by_hand(ctx)
    if await _signups_disabled(ctx):
        io.say("Sign-ups are now switched off.")
        return
    message = "sign-ups are still open - switch them off, then run this step again"
    raise ValidationFailedError(message)


async def _switched_off_through_the_api(ctx: SetupContext) -> bool:
    """Ask Supabase to refuse new sign-ups; ``False`` when it would not or could not.

    A refused token, a refused request and an outage (a server error, a timeout)
    all end in the same place: the hand-guided settings page.
    """
    if ctx.session.supabase_token is None and not ctx.io.confirm(
        "Switch them off with a Supabase access token (used now, not saved)?", default=True
    ):
        return False
    ref = values.project_ref(ctx.require("SUPABASE_URL", StepName.SUPABASE))
    try:
        token = await require_supabase_token(ctx)
        with full_access_needed(ctx):
            await ctx.gateways.platform.configure_auth(
                ref, token, AuthSettings(disable_signup=True)
            )
    except (SourceAuthError, SourceUnavailableError) as error:
        ctx.io.say(f"Supabase would not change the setting: {error.message}.")
        return False
    return True


async def _signups_off_once_applied(ctx: SetupContext) -> bool:
    """Read the public settings until the change shows; the auth server takes a moment."""
    for attempt in range(1, SIGNUP_CHECK_ATTEMPTS + 1):
        try:
            if await _signups_disabled(ctx):
                return True
        except SourceUnavailableError as error:
            _log.warning("auth_settings_unavailable", code=error.code)
        if attempt < SIGNUP_CHECK_ATTEMPTS:
            await ctx.gateways.sleep(SIGNUP_CHECK_WAIT_SECONDS)
    return False


def _guide_by_hand(ctx: SetupContext) -> None:
    """Open the sign-in settings page and wait for the switch to be saved."""
    io = ctx.io
    io.say("On the page that opens, switch off 'Allow new users to sign up', then click Save.")
    ref = values.project_ref(ctx.require("SUPABASE_URL", StepName.SUPABASE))
    io.open_page(SUPABASE_SIGN_IN_PAGE.format(ref=ref))
    io.pause("Once you have saved")
