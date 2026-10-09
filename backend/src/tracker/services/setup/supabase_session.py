"""One Supabase access token for the whole ``tracker setup`` run.

Several steps talk to Supabase's Management API: creating the project, applying
the database structure, switching sign-ups off, deploying the Refresh now
function. Each asks for the token through :func:`require_supabase_token`, so
the owner pastes it once; it is checked with one harmless read, kept in memory
for the rest of the run, and never written to ``.env``, logged or shown.
"""

from __future__ import annotations

from pydantic import SecretStr

from tracker.services.setup import values
from tracker.services.setup.context import SetupContext
from tracker.shared.constants.setup import SUPABASE_TOKEN_NAME, SUPABASE_TOKENS_PAGE

#: The question, asked hidden.
TOKEN_PROMPT = "Paste the Supabase access token (it stays hidden)"


async def require_supabase_token(ctx: SetupContext) -> SecretStr:
    """Return this run's Supabase access token, asking for it the first time.

    The first call opens Supabase's token page, says how to make the token,
    takes it hidden and proves it with one read that changes nothing (the list
    of organizations). Later calls in the same run return the same token
    without a word.

    Args:
        ctx: The set-up's context; the token is kept in its session.

    Returns:
        The accepted token.

    Raises:
        SourceAuthError: If Supabase refused every token typed.
        ValidationFailedError: If nothing was typed every time.
        SourceUnavailableError: If Supabase could not be reached.
    """
    if ctx.session.supabase_token is not None:
        return ctx.session.supabase_token
    _explain(ctx)
    token = await ctx.ask_until_accepted(
        lambda: ctx.io.ask_secret(TOKEN_PROMPT), lambda raw: _check(ctx, raw)
    )
    ctx.session.supabase_token = token
    ctx.io.say("Supabase accepted the token. It is kept in memory for this run only.")
    return token


def _explain(ctx: SetupContext) -> None:
    """Say what the token is for and how to make it, then open the page."""
    io = ctx.io
    io.say("Threadline talks to Supabase on your behalf with an access token. It is used")
    io.say("now, kept in memory until this set-up ends, and never saved. On the page that opens:")
    io.say(f"  1. Click 'Generate new token' and name it '{SUPABASE_TOKEN_NAME}'.")
    io.say("  2. Choose the shortest expiry offered; the token is only needed today.")
    io.say("  3. If it asks which access to give, give it your whole account: it creates the")
    io.say("     project, reads its keys, builds the database and switches sign-ups off.")
    io.say("  4. Click 'Generate token' and copy it (sbp_...).")
    io.say("You can delete the token on the same page once the set-up is finished.")
    io.open_page(SUPABASE_TOKENS_PAGE)


async def _check(ctx: SetupContext, raw: str) -> SecretStr:
    """Prove a typed token with one read that changes nothing."""
    token = SecretStr(values.non_empty("".join(raw.split()), "the access token"))
    await ctx.gateways.platform.organizations(token)
    return token
