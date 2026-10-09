"""LinkedIn's sign-in with the owner's own application: the listener, the exchange, the store.

LinkedIn itself is mocked with respx; the one-time listener is real but listens
on this computer only, on a port the system picks, and is reached with the
standard library so the respx mocks never see those requests.
"""

from __future__ import annotations

import asyncio
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import pytest
import respx
from pydantic import SecretStr

from tests.conftest import TEST_ENCRYPTION_KEY, FakeSupabaseClient, as_client
from tracker.domain.linkedin_sign_in import LinkedInApp, SignInProblem
from tracker.infrastructure.imap.connection import StoreAccess
from tracker.infrastructure.linkedin.callback import CallbackAnswer, CallbackListener
from tracker.infrastructure.linkedin.connection import LinkedInConnection
from tracker.infrastructure.linkedin.oauth import LinkedInOAuthApi, authorization_url
from tracker.shared.clock import FixedClock
from tracker.shared.constants.linkedin_sign_in import (
    ACCESS_TOKEN_URL,
    CALLBACK_PATH,
    INTROSPECT_URL,
    REDIRECT_URL,
    SCOPE,
)
from tracker.shared.errors import LinkedInSignInError, SourceUnavailableError

pytestmark = pytest.mark.asyncio

_NOW = datetime(2026, 10, 9, 8, 0, tzinfo=UTC)
_APP = LinkedInApp("78abcdefghijkl", SecretStr("app-secret"))
_SIXTY_DAYS = 60 * 24 * 60 * 60


def _listener(state: str) -> CallbackListener:
    """A listener on a port the system picks, on the IPv4 loopback address only."""
    return CallbackListener(state, port=0, addresses=("127.0.0.1",))


def _open(listener: CallbackListener, **query: str) -> int:
    """Play the browser that LinkedIn sends back, and return the status it got."""
    url = f"http://127.0.0.1:{listener.port}{CALLBACK_PATH}?{urlencode(query)}"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310 - loopback only
            return int(response.status)
    except urllib.error.HTTPError as error:
        return error.code


# --- The consent page's address --------------------------------------------------


async def test_the_consent_page_asks_for_the_data_portability_permission_only() -> None:
    url = authorization_url(_APP.client_id, "state-1")

    parts = urlsplit(url)
    query = {name: values[0] for name, values in parse_qs(parts.query).items()}
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == (
        "https://www.linkedin.com/oauth/v2/authorization"
    )
    assert query == {
        "response_type": "code",
        "client_id": _APP.client_id,
        "redirect_uri": REDIRECT_URL,
        "state": "state-1",
        "scope": SCOPE,
    }
    assert "app-secret" not in url


async def test_the_address_on_the_auth_tab_is_on_this_computer() -> None:
    assert REDIRECT_URL == "http://localhost:8746/linkedin"


# --- The one-time listener -------------------------------------------------------


async def test_the_listener_takes_the_answer_that_carries_its_state() -> None:
    with _listener("right") as listener:
        status = await asyncio.to_thread(_open, listener, code="the-code", state="right")
        answer = await listener.wait(1)

    assert status == 200
    assert answer == CallbackAnswer(code="the-code", error=None, error_description=None)


async def test_the_listener_turns_away_an_answer_with_another_state() -> None:
    with _listener("right") as listener:
        wrong = await asyncio.to_thread(_open, listener, code="sneaked-in", state="wrong")
        missing = await asyncio.to_thread(_open, listener, code="sneaked-in")
        answer = await listener.wait(0)

    assert (wrong, missing) == (400, 400)
    assert answer is None


async def test_the_listener_passes_on_linkedins_error() -> None:
    with _listener("right") as listener:
        await asyncio.to_thread(
            _open,
            listener,
            error="user_cancelled_authorize",
            error_description="The user cancelled",
            state="right",
        )
        answer = await listener.wait(1)

    assert answer == CallbackAnswer(None, "user_cancelled_authorize", "The user cancelled")


async def test_the_listener_keeps_the_first_answer_only() -> None:
    with _listener("right") as listener:
        await asyncio.to_thread(_open, listener, code="first", state="right")
        await asyncio.to_thread(_open, listener, code="second", state="right")
        answer = await listener.wait(1)

    assert answer is not None
    assert answer.code == "first"


async def test_the_listener_answers_nothing_on_other_paths() -> None:
    with _listener("right") as listener:
        url = f"http://127.0.0.1:{listener.port}/elsewhere?code=x&state=right"
        status = await asyncio.to_thread(_status_of, url)
        answer = await listener.wait(0)

    assert status == 404
    assert answer is None


def _status_of(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310 - loopback only
            return int(response.status)
    except urllib.error.HTTPError as error:
        return error.code


async def test_a_busy_port_is_said_plainly() -> None:
    with _listener("first") as first:
        busy = CallbackListener("second", port=first.port, addresses=("127.0.0.1",))
        with pytest.raises(LinkedInSignInError, match="Another program") as raised:
            busy.__enter__()

    assert raised.value.problem == SignInProblem.OTHER


# --- The key exchange -------------------------------------------------------------


@respx.mock
async def test_the_code_is_traded_for_a_key_with_its_expiry() -> None:
    route = respx.post(ACCESS_TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "new-key", "expires_in": 5_184_000})
    )

    grant = await LinkedInOAuthApi(FixedClock(_NOW)).exchange(_APP, "the-code")

    assert grant.access_token.get_secret_value() == "new-key"
    assert grant.expires_at == _NOW + timedelta(seconds=_SIXTY_DAYS)
    sent = parse_qs(route.calls.last.request.content.decode())
    assert sent == {
        "grant_type": ["authorization_code"],
        "code": ["the-code"],
        "redirect_uri": [REDIRECT_URL],
        "client_id": [_APP.client_id],
        "client_secret": ["app-secret"],
    }


@respx.mock
async def test_a_key_without_a_lifetime_has_no_expiry_yet() -> None:
    respx.post(ACCESS_TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "new-key"})
    )

    grant = await LinkedInOAuthApi(FixedClock(_NOW)).exchange(_APP, "the-code")

    assert grant.expires_at is None


@respx.mock
@pytest.mark.parametrize(
    ("status", "body", "problem", "words"),
    [
        (401, {"error": "invalid_client"}, SignInProblem.APP_DETAILS, "Client Secret"),
        (401, {}, SignInProblem.APP_DETAILS, "Client Secret"),
        (400, {"error": "invalid_redirect_uri"}, SignInProblem.APP_DETAILS, "Auth tab"),
        (401, {"error": "invalid_request"}, SignInProblem.OTHER, "already been used"),
        (400, {"error": "invalid_request"}, SignInProblem.OTHER, "already been used"),
        (200, {"expires_in": 10}, SignInProblem.OTHER, "without a key"),
    ],
)
async def test_a_refused_exchange_is_said_plainly(
    status: int, body: dict[str, object], problem: SignInProblem, words: str
) -> None:
    respx.post(ACCESS_TOKEN_URL).mock(return_value=httpx.Response(status, json=body))

    with pytest.raises(LinkedInSignInError, match=words) as raised:
        await LinkedInOAuthApi(FixedClock(_NOW)).exchange(_APP, "the-code")

    assert raised.value.problem == problem
    assert "app-secret" not in raised.value.message


@respx.mock
async def test_an_exchange_that_never_arrives_is_not_sent_twice() -> None:
    route = respx.post(ACCESS_TOKEN_URL).mock(side_effect=httpx.ReadTimeout("slow"))

    with pytest.raises(SourceUnavailableError, match="could not be reached"):
        await LinkedInOAuthApi(FixedClock(_NOW)).exchange(_APP, "the-code")

    assert route.call_count == 1


@respx.mock
async def test_linkedins_own_fault_is_said_as_such() -> None:
    respx.post(ACCESS_TOKEN_URL).mock(return_value=httpx.Response(503))

    with pytest.raises(SourceUnavailableError, match="problem of its own"):
        await LinkedInOAuthApi(FixedClock(_NOW)).exchange(_APP, "the-code")


# --- Reading a key's expiry --------------------------------------------------------


@respx.mock
async def test_the_expiry_of_a_key_is_read_from_linkedin() -> None:
    expires_at = int(datetime(2027, 9, 24, tzinfo=UTC).timestamp())
    route = respx.post(INTROSPECT_URL).mock(
        return_value=httpx.Response(200, json={"active": True, "expires_at": expires_at})
    )

    moment = await LinkedInOAuthApi(FixedClock(_NOW)).expiry_of(_APP, SecretStr("a-key"))

    assert moment == datetime(2027, 9, 24, tzinfo=UTC)
    assert parse_qs(route.calls.last.request.content.decode())["token"] == ["a-key"]


@respx.mock
@pytest.mark.parametrize(
    ("status", "body"),
    [
        (200, {"active": False, "status": "expired"}),
        (200, {"active": True}),
        (400, {"error": "invalid_request"}),
    ],
)
async def test_no_expiry_comes_back_for_a_key_linkedin_does_not_vouch_for(
    status: int, body: dict[str, object]
) -> None:
    respx.post(INTROSPECT_URL).mock(return_value=httpx.Response(status, json=body))

    assert await LinkedInOAuthApi(FixedClock(_NOW)).expiry_of(_APP, SecretStr("k")) is None


@respx.mock
async def test_a_refused_secret_while_reading_the_expiry_is_said_plainly() -> None:
    respx.post(INTROSPECT_URL).mock(return_value=httpx.Response(401, json={}))

    with pytest.raises(LinkedInSignInError, match="Client Secret") as raised:
        await LinkedInOAuthApi(FixedClock(_NOW)).expiry_of(_APP, SecretStr("k"))

    assert raised.value.problem == SignInProblem.APP_DETAILS


# --- The whole sign-in --------------------------------------------------------------


def _connection(
    fake_client: FakeSupabaseClient, listeners: list[CallbackListener]
) -> LinkedInConnection:
    def listener_for(state: str) -> CallbackListener:
        listener = _listener(state)
        listeners.append(listener)
        return listener

    return LinkedInConnection(
        lambda _url, _key: as_client(fake_client),
        FixedClock(_NOW),
        listener_for=listener_for,
        wait_slice_seconds=1,
    )


def _browser_that_answers(listeners: list[CallbackListener], **answer: str):  # noqa: ANN202
    """A browser where LinkedIn sends back ``answer`` with the right state."""

    def show_page(url: str) -> None:
        state = parse_qs(urlsplit(url).query)["state"][0]
        _open(listeners[-1], state=state, **answer)

    return show_page


@respx.mock
async def test_signing_in_opens_the_page_catches_the_code_and_returns_the_key(
    fake_client: FakeSupabaseClient,
) -> None:
    route = respx.post(ACCESS_TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "new-key", "expires_in": 60})
    )
    listeners: list[CallbackListener] = []

    grant = await _connection(fake_client, listeners).sign_in(
        _APP, _browser_that_answers(listeners, code="the-code"), lambda: False
    )

    assert grant.access_token.get_secret_value() == "new-key"
    assert parse_qs(route.calls.last.request.content.decode())["code"] == ["the-code"]


@respx.mock
@pytest.mark.parametrize(
    ("error", "problem", "words"),
    [
        ("user_cancelled_authorize", SignInProblem.CANCELLED, "cancelled"),
        ("user_cancelled_login", SignInProblem.CANCELLED, "cancelled"),
        ("unauthorized_scope_error", SignInProblem.PRODUCT_MISSING, "Products tab"),
        ("server_error", SignInProblem.OTHER, "It said: Something odd"),
    ],
)
async def test_linkedins_refusal_on_the_consent_page_is_said_plainly(
    fake_client: FakeSupabaseClient, error: str, problem: SignInProblem, words: str
) -> None:
    route = respx.post(ACCESS_TOKEN_URL)
    listeners: list[CallbackListener] = []
    browser = _browser_that_answers(listeners, error=error, error_description="Something odd")

    with pytest.raises(LinkedInSignInError, match=words) as raised:
        await _connection(fake_client, listeners).sign_in(_APP, browser, lambda: False)

    assert raised.value.problem == problem
    assert not route.called


async def test_no_answer_asks_to_keep_waiting_then_says_what_to_check(
    fake_client: FakeSupabaseClient,
) -> None:
    listeners: list[CallbackListener] = []
    asked: list[bool] = []
    connection = LinkedInConnection(
        lambda _url, _key: as_client(fake_client),
        FixedClock(_NOW),
        listener_for=lambda state: listeners.append(_listener(state)) or listeners[-1],
        wait_slice_seconds=0,
    )

    def keep_waiting() -> bool:
        asked.append(True)
        return len(asked) < 2

    with pytest.raises(LinkedInSignInError, match="redirect_uri does not match") as raised:
        await connection.sign_in(_APP, lambda _url: None, keep_waiting)

    assert raised.value.problem == SignInProblem.NO_ANSWER
    assert len(asked) == 2


@respx.mock
async def test_an_answer_that_comes_while_asking_to_keep_waiting_is_still_used(
    fake_client: FakeSupabaseClient,
) -> None:
    respx.post(ACCESS_TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "new-key", "expires_in": 60})
    )
    listeners: list[CallbackListener] = []
    pages: list[str] = []
    connection = LinkedInConnection(
        lambda _url, _key: as_client(fake_client),
        FixedClock(_NOW),
        listener_for=lambda state: listeners.append(_listener(state)) or listeners[-1],
        wait_slice_seconds=0,
    )

    def answer_then_stop_waiting() -> bool:
        state = parse_qs(urlsplit(pages[-1]).query)["state"][0]
        _open(listeners[-1], state=state, code="the-code")
        return False

    grant = await connection.sign_in(_APP, pages.append, answer_then_stop_waiting)

    assert grant.access_token.get_secret_value() == "new-key"


async def test_the_client_secret_is_kept_encrypted_and_read_back(
    fake_client: FakeSupabaseClient,
) -> None:
    connection = _connection(fake_client, [])
    access = StoreAccess(
        "https://sample-project.supabase.co", SecretStr("key"), SecretStr(TEST_ENCRYPTION_KEY)
    )

    before = await connection.saved_client_secret(access)
    await connection.save_client_secret(access, SecretStr("app-secret"))
    after = await connection.saved_client_secret(access)

    assert before is None
    assert after is not None
    assert after.get_secret_value() == "app-secret"
    assert "app-secret" not in repr(fake_client.__dict__)
