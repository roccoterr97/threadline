"""One Supabase access token for the whole ``tracker setup`` run.

Several steps talk to Supabase's Management API: creating the project, applying
the database structure, switching sign-ups off, deploying the Refresh now
function. Each asks for the token through :func:`require_supabase_token`, so
the owner gives it once; it is checked with one harmless read, kept in memory
for the rest of the run, and never written to ``.env``, logged or shown.

There are two routes to it. The offered one is a browser sign-in
(:mod:`tracker.services.setup.supabase_sign_in`): click Authorize on a
Supabase page and type back a short code. The other, and the fallback when the
browser route does not work, is pasting a token made on Supabase's website.

A pasted token must be a legacy (full-access) one. Supabase's newer scoped tokens
cannot reveal a project's secret API key at all
(https://github.com/supabase/supabase/issues/50244), and a new account has no
project to scope one to, so the set-up only ever describes the legacy kind.
When Supabase still turns a token away as too limited, :func:`full_access_needed`
forgets it and says how to make the right one.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from enum import IntEnum
from typing import Final

from pydantic import SecretStr

from tracker.services.setup import values
from tracker.services.setup.context import SetupContext
from tracker.services.setup.supabase_sign_in import sign_in_with_browser
from tracker.shared.constants.setup import SUPABASE_TOKEN_NAME, SUPABASE_TOKENS_PAGE
from tracker.shared.errors import SourcePermissionError


class TokenRoute(IntEnum):
    """How the owner gives Threadline access to Supabase, by its number in the list."""

    BROWSER = 1
    PASTE = 2


#: How each route is offered.
ROUTE_LABELS: Final[dict[TokenRoute, str]] = {
    TokenRoute.BROWSER: "Sign in to Supabase in your browser (easiest)",
    TokenRoute.PASTE: "I'd rather paste a token",
}

#: The question that picks a route.
ROUTE_PROMPT: Final[str] = "Your choice (number)"

#: The question, asked hidden.
TOKEN_PROMPT = "Paste the Supabase access token (it stays hidden)"

#: How to make the token on Supabase's Access Tokens page, in its own words.
TOKEN_STEPS: Final[tuple[str, ...]] = (
    "  1. Click 'Generate new token'.",
    "  2. On the left, under 'Resource access', click the small link 'Create legacy token'.",
    f"  3. Name it '{SUPABASE_TOKEN_NAME}' and choose the shortest expiry.",
    "  4. Click 'Generate token' and copy it (it starts with sbp_).",
)

#: What is said when Supabase finds a token too limited, and how to make one that is not.
TOO_LITTLE_ACCESS: Final[str] = (
    "Supabase says this access token has too little access - make a new one with the "
    "small link 'Create legacy token' on Supabase's Access Tokens page"
)


async def require_supabase_token(ctx: SetupContext) -> SecretStr:
    """Return this run's Supabase access token, asking for it the first time.

    The first call offers the browser sign-in or a pasted token (an express
    run goes straight to the browser sign-in). A pasted
    token's route opens Supabase's token page, says how to make the token and
    takes it hidden; it also takes over when the browser route does not work.
    Either way the token is proven with one read that changes nothing (the
    list of organizations). Later calls in the same run return the same token
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
    token = None
    if _chosen_route(ctx) is TokenRoute.BROWSER:
        token = await sign_in_with_browser(ctx)
    if token is None:
        token = await _pasted_token(ctx)
    ctx.session.supabase_token = token
    return token


@contextmanager
def full_access_needed(ctx: SetupContext) -> Iterator[None]:
    """Turn Supabase's "too little access" into the plain fix, forgetting the token.

    Calls made inside the block that Supabase turns away as too limited raise
    a :class:`SourcePermissionError` that says how to make a legacy token. The
    token is dropped from the session, so the next step that needs one asks
    for a new one instead of failing the same way.

    Args:
        ctx: The set-up's context.

    Yields:
        Nothing; the block runs as it is.

    Raises:
        SourcePermissionError: If Supabase found the token too limited.
    """
    try:
        yield
    except SourcePermissionError as error:
        raise too_little_access(ctx) from error


def too_little_access(ctx: SetupContext) -> SourcePermissionError:
    """Forget this run's token and build the error that says how to make a better one.

    Args:
        ctx: The set-up's context; its token is dropped.

    Returns:
        The error, with :data:`TOO_LITTLE_ACCESS` as its message.
    """
    ctx.session.supabase_token = None
    return SourcePermissionError(TOO_LITTLE_ACCESS)


def _chosen_route(ctx: SetupContext) -> TokenRoute:
    """Offer the browser sign-in first and the pasted token second; express takes the first."""
    ctx.io.say("Threadline needs your permission to work in your Supabase account.")
    if ctx.session.express:
        return TokenRoute.BROWSER
    for route in TokenRoute:
        ctx.io.say(f"  {route.value}. {ROUTE_LABELS[route]}")
    number = ctx.ask_until_valid(
        lambda: ctx.io.ask(ROUTE_PROMPT, default=str(TokenRoute.BROWSER.value)),
        lambda raw: values.list_number(raw, len(TokenRoute)),
    )
    return TokenRoute(number)


async def _pasted_token(ctx: SetupContext) -> SecretStr:
    """Say how to make a legacy token, take it hidden and prove it."""
    _explain(ctx)
    token = await ctx.ask_until_accepted(
        lambda: ctx.io.ask_secret(TOKEN_PROMPT), lambda raw: _check(ctx, raw)
    )
    ctx.io.say("Supabase accepted the token. It is kept in memory for this run only.")
    return token


def _explain(ctx: SetupContext) -> None:
    """Say what the token is for and how to make it, then open the page."""
    io = ctx.io
    io.say("Threadline talks to Supabase on your behalf with an access token. It is used")
    io.say("now, kept in memory until this set-up ends, and never saved. On the page that opens:")
    for line in TOKEN_STEPS:
        io.say(line)
    io.say("It must be a legacy token: Supabase's newer, limited tokens cannot read your")
    io.say("project's secret key yet, and the set-up needs it.")
    io.say("You can delete the token on the same page once the set-up is finished.")
    io.open_page(SUPABASE_TOKENS_PAGE)


async def _check(ctx: SetupContext, raw: str) -> SecretStr:
    """Prove a typed token with one read that changes nothing."""
    token = SecretStr(values.non_empty("".join(raw.split()), "the access token"))
    with full_access_needed(ctx):
        await ctx.gateways.platform.organizations(token)
    return token
