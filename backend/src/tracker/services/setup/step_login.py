"""Step 4: the first dashboard login, and switching off sign-ups."""

from __future__ import annotations

from pydantic import SecretStr

from tracker.services.setup import values
from tracker.services.setup.context import SetupContext
from tracker.services.setup.models import StepName
from tracker.shared.constants.setup import SUPABASE_SIGN_IN_PAGE
from tracker.shared.errors import ValidationFailedError


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
    """Make sure strangers cannot create a login, guiding by hand if needed."""
    io = ctx.io
    if await _signups_disabled(ctx):
        io.say("Sign-ups are switched off: nobody else can create a login.")
        return
    io.say("Sign-ups are still open. On the page that opens, switch off")
    io.say("'Allow new users to sign up', then click Save.")
    io.open_page(
        SUPABASE_SIGN_IN_PAGE.format(
            ref=values.project_ref(ctx.require("SUPABASE_URL", "supabase"))
        )
    )
    io.pause("Once you have saved")
    if await _signups_disabled(ctx):
        io.say("Sign-ups are now switched off.")
        return
    message = "sign-ups are still open - switch them off, then run this step again"
    raise ValidationFailedError(message)
