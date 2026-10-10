"""Signing in to Supabase in the browser instead of pasting a token.

The tests play Supabase: they read the public key from the page the set-up
opened, seal a made-up token for it with their own key, and hand it back.
Nothing here reaches supabase.com.
"""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx
from pydantic import SecretStr

from tests.setup_world import (
    GOOD_CODE,
    GOOD_TOKEN,
    PASTE,
    World,
    make_world,
)
from tracker.domain.supabase import SealedAccessToken
from tracker.infrastructure.supabase_platform import SupabasePlatform
from tracker.services.setup.context import SetupContext
from tracker.services.setup.models import StepName
from tracker.services.setup.supabase_session import (
    ROUTE_LABELS,
    TOKEN_PROMPT,
    TokenRoute,
    require_supabase_token,
)
from tracker.services.setup.supabase_sign_in import CODE_PROMPT, CODE_REFUSED, SIGN_IN_FAILED
from tracker.services.setup.wizard import SetupWizard
from tracker.shared.constants.setup import (
    SUPABASE_BROWSER_SIGN_IN_PAGE,
    SUPABASE_SIGN_IN_TIMEOUT_SECONDS,
    SUPABASE_SIGN_IN_TOKEN_PREFIX,
    SUPABASE_TOKENS_PAGE,
)
from tracker.shared.errors import (
    SourceAuthError,
    SourceUnavailableError,
    ValidationFailedError,
)

pytestmark = pytest.mark.asyncio

SESSION_ID = "0b7c4f5e-1d2a-4e3b-9c8d-7a6b5c4d3e2f"
SESSION_URL = f"https://api.supabase.com/platform/cli/login/{SESSION_ID}"
#: The test world's fixed clock; the token's name ends with it as Unix time.
SIGNED_IN_AT = datetime(2026, 9, 29, 7, 0, tzinfo=UTC)
TOKEN_NAME = f"{SUPABASE_SIGN_IN_TOKEN_PREFIX}{int(SIGNED_IN_AT.timestamp())}"


def _sign_in_page(world: World) -> dict[str, list[str]]:
    """The query of the sign-in page the set-up opened."""
    [page] = [url for url in world.io.opened if url.startswith(SUPABASE_BROWSER_SIGN_IN_PAGE)]
    return parse_qs(urlsplit(page).query)


async def _token(world: World) -> tuple[SecretStr, SetupContext]:
    ctx = world.context()
    return await require_supabase_token(ctx), ctx


# --- The session answer, over HTTP ------------------------------------------------


async def test_the_session_is_asked_once_with_the_code_and_no_token() -> None:
    answer = {"id": "x", "access_token": "aa", "public_key": "bb", "nonce": "cc"}
    with respx.mock:
        route = respx.get(SESSION_URL).mock(return_value=httpx.Response(200, json=answer))
        async with SupabasePlatform() as platform:
            sealed = await platform.sign_in_token(SESSION_ID, GOOD_CODE)

    assert sealed == SealedAccessToken(ciphertext_hex="aa", public_key_hex="bb", nonce_hex="cc")
    request = route.calls.last.request
    assert request.url.params["device_code"] == GOOD_CODE
    assert "Authorization" not in request.headers
    assert request.extensions["timeout"]["read"] == SUPABASE_SIGN_IN_TIMEOUT_SECONDS


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429])
async def test_a_refused_code_is_an_auth_error_asked_only_once(status: int) -> None:
    with respx.mock:
        route = respx.get(SESSION_URL).mock(return_value=httpx.Response(status))
        async with SupabasePlatform() as platform:
            with pytest.raises(SourceAuthError, match="did not accept that code"):
                await platform.sign_in_token(SESSION_ID, "wrong")

    assert route.call_count == 1


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500),
        httpx.Response(200, json={"access_token": "aa", "nonce": "cc"}),
        httpx.Response(200, json=["aa"]),
        httpx.Response(200, text="<html>"),
    ],
    ids=["server-error", "missing-field", "not-an-object", "not-json"],
)
async def test_an_odd_answer_is_reported_as_unavailable(response: httpx.Response) -> None:
    with respx.mock:
        route = respx.get(SESSION_URL).mock(return_value=response)
        async with SupabasePlatform() as platform:
            with pytest.raises(SourceUnavailableError):
                await platform.sign_in_token(SESSION_ID, GOOD_CODE)

    assert route.call_count == 1


async def test_an_unreachable_session_is_reported_as_unavailable() -> None:
    with respx.mock:
        respx.get(SESSION_URL).mock(side_effect=httpx.ConnectError("no network"))
        async with SupabasePlatform() as platform:
            with pytest.raises(SourceUnavailableError, match="could not be reached"):
                await platform.sign_in_token(SESSION_ID, GOOD_CODE)


# --- The conversation ---------------------------------------------------------------


async def test_the_browser_sign_in_is_offered_first_and_chosen_by_pressing_enter() -> None:
    world = make_world(["", GOOD_CODE])

    token, ctx = await _token(world)

    assert token.get_secret_value() == GOOD_TOKEN
    assert ctx.session.supabase_token == token
    assert ctx.session.supabase_token_name == TOKEN_NAME
    assert world.io.said[1:3] == [
        f"  1. {ROUTE_LABELS[TokenRoute.BROWSER]}",
        f"  2. {ROUTE_LABELS[TokenRoute.PASTE]}",
    ]
    assert "  2. I'd rather paste a token" in world.io.said
    assert world.io.defaults["Your choice (number)"] == "1"
    assert world.io.secret_prompts == []
    assert CODE_PROMPT in world.io.exact
    # The token Supabase sealed was opened and proven with one harmless read.
    assert world.platform.organization_reads == 1


async def test_the_page_carries_the_session_the_name_and_this_computers_public_key() -> None:
    world = make_world(["", GOOD_CODE])

    await _token(world)

    query = _sign_in_page(world)
    assert query["token_name"] == [TOKEN_NAME]
    assert len(query["session_id"][0]) == len(SESSION_ID)
    assert len(query["public_key"][0]) == 130
    assert "Authorize" in world.io.text()


async def test_the_owner_is_told_where_the_token_is_listed_and_that_it_may_go() -> None:
    world = make_world(["", GOOD_CODE])

    await _token(world)

    assert (
        f"Supabase lists it under Access Tokens as '{TOKEN_NAME}'; you can delete it there "
        "once the set-up is finished."
    ) in world.io.said
    assert GOOD_TOKEN not in world.io.text()
    assert world.env.values == {}


async def test_a_wrong_code_is_asked_for_again_then_the_right_one_signs_in() -> None:
    world = make_world(["", "wrong1", GOOD_CODE])

    token, _ = await _token(world)

    assert token.get_secret_value() == GOOD_TOKEN
    assert world.platform.sign_in_codes == ["wrong1", GOOD_CODE]
    assert "  Supabase did not accept that code. Please try again." in world.io.said
    assert TOKEN_PROMPT not in world.io.secret_prompts


async def test_a_code_typed_with_spaces_is_cleaned() -> None:
    world = make_world(["", f" {GOOD_CODE[:4]} {GOOD_CODE[4:]}\n"])

    await _token(world)

    assert world.platform.sign_in_codes == [GOOD_CODE]


async def test_a_code_refused_every_time_falls_back_to_pasting_a_token() -> None:
    world = make_world(["", "wrong1", "wrong2", "wrong3", GOOD_TOKEN])

    token, ctx = await _token(world)

    assert token.get_secret_value() == GOOD_TOKEN
    assert len(world.platform.sign_in_codes) == 3
    assert CODE_REFUSED in world.io.said
    assert world.io.secret_prompts == [TOKEN_PROMPT]
    assert world.io.opened[-1] == SUPABASE_TOKENS_PAGE
    assert ctx.session.supabase_token_name is None


async def test_a_sealed_token_that_does_not_open_falls_back_to_pasting() -> None:
    world = make_world(["", GOOD_CODE, GOOD_TOKEN])
    world.platform.sign_in_damaged = True

    token, ctx = await _token(world)

    assert token.get_secret_value() == GOOD_TOKEN
    assert SIGN_IN_FAILED in world.io.said
    assert world.io.secret_prompts == [TOKEN_PROMPT]
    assert ctx.session.supabase_token_name is None


async def test_an_unreachable_sign_in_falls_back_to_pasting() -> None:
    world = make_world(["", GOOD_CODE, GOOD_TOKEN])
    world.platform.sign_in_failure = SourceUnavailableError("Supabase could not be reached")

    token, _ = await _token(world)

    assert token.get_secret_value() == GOOD_TOKEN
    assert SIGN_IN_FAILED in world.io.said
    assert world.platform.sign_in_codes == [GOOD_CODE]
    assert world.io.secret_prompts == [TOKEN_PROMPT]


async def test_an_opened_token_supabase_then_refuses_falls_back_to_pasting() -> None:
    world = make_world(["", GOOD_CODE, GOOD_TOKEN])
    world.platform.sign_in_token_value = "sbp_not_known"

    token, _ = await _token(world)

    assert token.get_secret_value() == GOOD_TOKEN
    assert SIGN_IN_FAILED in world.io.said
    assert world.io.secret_prompts == [TOKEN_PROMPT]


async def test_choosing_to_paste_skips_the_browser_sign_in() -> None:
    world = make_world([PASTE, GOOD_TOKEN])

    token, ctx = await _token(world)

    assert token.get_secret_value() == GOOD_TOKEN
    assert world.platform.sign_in_codes == []
    assert world.io.opened == [SUPABASE_TOKENS_PAGE]
    assert "Click 'Generate new token'." in world.io.text()
    assert ctx.session.supabase_token_name is None


async def test_a_choice_that_is_not_listed_is_asked_again() -> None:
    world = make_world(["3", PASTE, GOOD_TOKEN])

    await _token(world)

    assert "  type a number from 1 to 2. Please try again." in world.io.said


async def test_an_empty_code_every_time_falls_back_to_pasting() -> None:
    world = make_world(["", "", "", "", GOOD_TOKEN])

    token, _ = await _token(world)

    assert token.get_secret_value() == GOOD_TOKEN
    assert world.platform.sign_in_codes == []
    assert CODE_REFUSED in world.io.said


async def test_a_paste_refused_every_time_after_the_fallback_still_stops_cleanly() -> None:
    world = make_world(["", GOOD_CODE, "bad", "bad", "bad"])
    world.platform.sign_in_damaged = True

    with pytest.raises(SourceAuthError):
        await _token(world)


# --- The end of the run -----------------------------------------------------------


class _NeedsSupabase:
    """A step that only asks for the Supabase token, like the Refresh now step does."""

    name = StepName.REFRESH
    title = "Needs Supabase"

    def __init__(self, *, fails: bool = False) -> None:
        self.fails = fails

    async def is_done(self, ctx: SetupContext) -> bool:
        return False

    async def run(self, ctx: SetupContext) -> None:
        await require_supabase_token(ctx)
        if self.fails:
            message = "something else went wrong"
            raise ValidationFailedError(message)


def _reminder() -> str:
    return (
        f"The set-up no longer needs its Supabase access: you can delete '{TOKEN_NAME}' "
        f"on Supabase's Access Tokens page, {SUPABASE_TOKENS_PAGE}"
    )


async def test_a_finished_run_says_the_signed_in_token_may_now_be_deleted() -> None:
    world = make_world(["", GOOD_CODE])

    assert await SetupWizard(world.context(), [_NeedsSupabase()]).run_extras()

    assert world.io.said[-1] == _reminder()


async def test_a_step_run_by_name_ends_with_the_same_reminder() -> None:
    world = make_world(["", GOOD_CODE])

    assert await SetupWizard(world.context(), [_NeedsSupabase()]).run_one(StepName.REFRESH)

    assert world.io.said[-1] == _reminder()


async def test_a_pasted_token_or_a_stopped_run_ends_without_the_reminder() -> None:
    pasted = make_world([PASTE, GOOD_TOKEN])
    stopped = make_world(["", GOOD_CODE])

    assert await SetupWizard(pasted.context(), [_NeedsSupabase()]).run_extras()
    assert not await SetupWizard(stopped.context(), [_NeedsSupabase(fails=True)]).run_extras()

    for world in (pasted, stopped):
        assert "no longer needs its Supabase access" not in world.io.text()
