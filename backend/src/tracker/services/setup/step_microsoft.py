"""Step: signing in to the Microsoft mailbox and calendar.

Outlook is optional once another mailbox is read: the step then asks before
signing in, because only an Outlook mailbox or the Outlook calendar needs it.
A "no" is remembered, so a later full run does not ask again.
"""

from __future__ import annotations

from pydantic import SecretStr

from tracker.services.setup.context import SetupContext
from tracker.services.setup.mail_sources import save_sources, saved_sources
from tracker.services.setup.models import StepName
from tracker.services.setup.owner_address import remember_address
from tracker.services.setup.ports import MicrosoftAccess
from tracker.services.setup.skipped_steps import remember_skip, skipped_earlier
from tracker.shared.constants.collection import MICROSOFT_CLIENT_ID, MICROSOFT_DEFAULT_TENANT
from tracker.shared.constants.mailbox import MailSource


class MicrosoftStep:
    """Signs in once with a short code; the key then renews itself."""

    name = StepName.MICROSOFT
    title = "Microsoft mailbox and calendar"

    async def is_done(self, ctx: SetupContext) -> bool:
        """Done when a sign-in key is stored."""
        return await ctx.gateways.microsoft.is_signed_in(microsoft_access(ctx))

    async def run(self, ctx: SetupContext) -> None:
        """Show the code, wait for the sign-in, then say who signed in."""
        io = ctx.io
        saved = saved_sources(ctx)
        if saved and MailSource.OUTLOOK not in saved and not _wanted(ctx):
            return
        io.say("Threadline reads your Outlook or Hotmail mailbox and calendar, read-only.")
        io.say("A Microsoft page opens: type the code below, sign in, and approve")
        io.say("the read-only permissions. Then come back here and wait a moment.")
        address = await ctx.gateways.microsoft.sign_in(
            microsoft_access(ctx), lambda url, code: _show_code(ctx, url, code)
        )
        io.say(f"Signed in as {address}." if address else "Signed in.")
        if saved and MailSource.OUTLOOK not in saved:
            save_sources(ctx, (*saved, MailSource.OUTLOOK))
        remember_address(ctx, address)


def _wanted(ctx: SetupContext) -> bool:
    """Ask whether to connect Outlook too, unless the owner said no on an earlier run."""
    io = ctx.io
    if skipped_earlier(ctx, StepName.MICROSOFT, "To add it"):
        return False
    io.say("Outlook is optional: Threadline already reads another mailbox. It is")
    io.say("only needed for an Outlook or Hotmail mailbox, or for your Outlook calendar.")
    if io.confirm("Connect Outlook as well?", default=False):
        return True
    remember_skip(ctx, StepName.MICROSOFT)
    io.say(f"Skipped. To add it later: uv run tracker setup {StepName.MICROSOFT}")
    return False


def microsoft_access(ctx: SetupContext) -> MicrosoftAccess:
    """Collect what the sign-in needs from ``.env``."""
    return MicrosoftAccess(
        supabase_url=ctx.require("SUPABASE_URL", StepName.SUPABASE),
        service_key=SecretStr(ctx.require("SUPABASE_SERVICE_ROLE_KEY", StepName.SUPABASE)),
        encryption_key=SecretStr(ctx.require("TOKEN_ENCRYPTION_KEY", StepName.ENCRYPTION)),
        client_id=ctx.env.get("MICROSOFT_CLIENT_ID") or MICROSOFT_CLIENT_ID,
        tenant=ctx.env.get("MICROSOFT_TENANT") or MICROSOFT_DEFAULT_TENANT,
    )


def _show_code(ctx: SetupContext, url: str, code: str) -> None:
    """Show the one-time code and open the page it is typed on."""
    ctx.io.say(f"Your code: {code}")
    ctx.io.open_page(url)
