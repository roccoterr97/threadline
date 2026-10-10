"""Sign in to Supabase in the browser, the way Supabase's own tool does.

Instead of making an access token on Supabase's website and pasting it, the
owner clicks Authorize on a Supabase page and types back the short code it
shows. Supabase then makes a normal, full-access token and hands it over
sealed for a key that only this computer holds (see
:mod:`tracker.infrastructure.supabase_sign_in_crypto`), so no server of ours
ever sees it. The token is kept in memory for this run only, exactly like a
pasted one.

The sign-in is not part of Supabase's documented API. When it answers
oddly, or the code is refused every time, this says so in one plain line and
returns ``None``, and the caller asks for a pasted token instead. It never
stops the set-up.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from uuid import uuid4

from pydantic import SecretStr

from tracker.domain.supabase import SealedAccessToken
from tracker.infrastructure.supabase_sign_in_crypto import (
    SignInKeys,
    new_sign_in_keys,
    open_sealed_token,
)
from tracker.services.setup import values
from tracker.services.setup.context import SetupContext
from tracker.shared.constants.setup import (
    SUPABASE_BROWSER_SIGN_IN_PAGE,
    SUPABASE_SIGN_IN_TOKEN_PREFIX,
    SUPABASE_TOKENS_PAGE,
)
from tracker.shared.errors import (
    SourceAuthError,
    SourceUnavailableError,
    SupabaseSignInError,
    ValidationFailedError,
)
from tracker.shared.logging import get_logger

#: The question for the code the Supabase page shows; it is not secret.
CODE_PROMPT: Final[str] = "Verification code from the Supabase page"

#: Said when the code was refused every time, before the paste route starts.
CODE_REFUSED: Final[str] = "Supabase did not accept the code, so let's paste a token instead."

#: Said when the sign-in answered oddly or could not be reached.
SIGN_IN_FAILED: Final[str] = (
    "Signing in through the browser did not work this time, so let's paste a token instead."
)

_log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class BrowserSignIn:
    """One browser sign-in: what goes into the page, and the key that opens the answer.

    Attributes:
        session_id: A fresh random identifier for this sign-in.
        token_name: The name Supabase lists the new token under.
        keys: The one-off key pair; its public half goes into the page.
    """

    session_id: str
    token_name: str
    keys: SignInKeys

    @property
    def page_url(self) -> str:
        """The sign-in page's address.

        Supabase's own tool joins the query without encoding it; every part
        here is letters, digits and dashes, so nothing needs encoding.
        """
        return (
            f"{SUPABASE_BROWSER_SIGN_IN_PAGE}?session_id={self.session_id}"
            f"&token_name={self.token_name}&public_key={self.keys.public_key_hex}"
        )


async def sign_in_with_browser(ctx: SetupContext) -> SecretStr | None:
    """Get a Supabase access token by signing in through the browser.

    Args:
        ctx: The set-up's context; on success the token's name is kept in its session.

    Returns:
        The token, proven with one read that changes nothing, or ``None`` when
        the browser route did not work and a pasted token should be asked for.
    """
    sign_in = _new_sign_in(ctx)
    _explain(ctx)
    ctx.io.open_page(sign_in.page_url)
    token = await _token_from_code(ctx, sign_in)
    if token is None or not await _proven(ctx, token):
        return None
    ctx.session.supabase_token_name = sign_in.token_name
    ctx.io.say("Signed in to Supabase. Threadline keeps this access in memory for this run only.")
    ctx.io.say(
        f"Supabase lists it under Access Tokens as '{sign_in.token_name}'; "
        "you can delete it there once the set-up is finished."
    )
    return token


def say_sign_in_can_go(ctx: SetupContext) -> None:
    """At the end of a run, say the browser sign-in's token may now be deleted.

    Says nothing when this run used a pasted token, or none at all.

    Args:
        ctx: The set-up's context; its session holds the token's name.
    """
    name = ctx.session.supabase_token_name
    if name is None:
        return
    ctx.io.say(
        f"The set-up no longer needs its Supabase access: you can delete '{name}' "
        f"on Supabase's Access Tokens page, {SUPABASE_TOKENS_PAGE}"
    )


def _new_sign_in(ctx: SetupContext) -> BrowserSignIn:
    """Make the key pair, the session identifier and the token's name."""
    stamp = int(ctx.gateways.clock.now().timestamp())
    return BrowserSignIn(
        session_id=str(uuid4()),
        token_name=f"{SUPABASE_SIGN_IN_TOKEN_PREFIX}{stamp}",
        keys=new_sign_in_keys(),
    )


def _explain(ctx: SetupContext) -> None:
    """Say what happens on the Supabase page."""
    io = ctx.io
    io.say("A Supabase page opens. Sign in if it asks, then click 'Authorize'.")
    io.say("The page may mention the 'Supabase CLI': that is expected, Threadline signs in")
    io.say("the same way. Supabase then shows a short verification code: type it here.")


async def _token_from_code(ctx: SetupContext, sign_in: BrowserSignIn) -> SecretStr | None:
    """Ask for the code until Supabase accepts it, then open the sealed token."""
    try:
        sealed = await ctx.ask_until_accepted(
            lambda: ctx.io.ask(CODE_PROMPT, exact=True),
            lambda raw: _collect(ctx, sign_in.session_id, raw),
        )
        return open_sealed_token(sign_in.keys, sealed)
    except (SourceAuthError, ValidationFailedError):
        ctx.io.say(CODE_REFUSED)
    except (SourceUnavailableError, SupabaseSignInError) as error:
        _log.warning("supabase_browser_sign_in_failed", code=error.code)
        ctx.io.say(SIGN_IN_FAILED)
    return None


async def _collect(ctx: SetupContext, session_id: str, raw: str) -> SealedAccessToken:
    """Hand one typed code to Supabase and return its sealed answer."""
    code = values.non_empty("".join(raw.split()), "the code")
    return await ctx.gateways.platform.sign_in_token(session_id, code)


async def _proven(ctx: SetupContext, token: SecretStr) -> bool:
    """Prove the opened token with one read that changes nothing."""
    try:
        await ctx.gateways.platform.organizations(token)
    except (SourceAuthError, SourceUnavailableError) as error:
        _log.warning("supabase_browser_sign_in_unproven", code=error.code)
        ctx.io.say(SIGN_IN_FAILED)
        return False
    return True
