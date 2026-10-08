"""Microsoft sign-in, key renewal, and the read-only mailbox reader.

Every payload is made up; only the shape follows Microsoft's documented answers.
The rule this file exists to prove: the rotated long-lived key reaches the
encrypted store *before* any mailbox call, so a crash straight after a renewal
still leaves a working key behind.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import respx
from pydantic import SecretStr

from tests.conftest import TEST_ENCRYPTION_KEY, FakeSupabaseClient, as_client
from tracker.infrastructure.microsoft.auth import (
    DEVICE_CODE_URL,
    TOKEN_URL,
    MicrosoftAuthenticator,
)
from tracker.infrastructure.microsoft.client import GraphMailbox
from tracker.infrastructure.microsoft.probe import GraphProbe
from tracker.infrastructure.secret_store import MICROSOFT_REFRESH_TOKEN, SecretStore
from tracker.repositories import build_repositories
from tracker.shared.clock import FixedClock
from tracker.shared.concurrency import gather_all
from tracker.shared.constants.collection import GRAPH_CONCURRENT_REQUESTS, MICROSOFT_GRAPH_URL
from tracker.shared.errors import SourceAuthError, SourceUnavailableError

MESSAGES_URL = f"{MICROSOFT_GRAPH_URL}/me/messages"
WINDOW_START = datetime(2026, 8, 19, tzinfo=UTC)

#: Turns of the event loop an answer is held back for, so every request that
#: is allowed to start has started before the first one is answered.
_TURNS_HELD: int = 25


class InFlight:
    """Answers requests slowly and remembers how many were open at once."""

    def __init__(self, answer: Callable[[httpx.Request], httpx.Response]) -> None:
        self._answer = answer
        self._open = 0
        self.peak = 0

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        """Hold the request open for a few turns, then answer it."""
        self._open += 1
        self.peak = max(self.peak, self._open)
        for _ in range(_TURNS_HELD):
            await asyncio.sleep(0)
        self._open -= 1
        return self._answer(request)


def body_answer(request: httpx.Request) -> httpx.Response:
    """Answer a body request with text that names the message it belongs to."""
    message_id = request.url.path.rsplit("/", maxsplit=1)[-1]
    body = {"contentType": "text", "content": f"body of {message_id}"}
    return httpx.Response(200, json={"id": message_id, "body": body})


@pytest.fixture
def secret_store(fake_client: FakeSupabaseClient, clock: FixedClock) -> SecretStore:
    """A secret store on the in-memory database."""
    repositories = build_repositories(as_client(fake_client))
    return SecretStore(repositories.app_secrets, SecretStr(TEST_ENCRYPTION_KEY), clock)


def graph_message(
    message_id: str,
    *,
    conversation_id: str = "thread-1",
    address: str = "elodie.martin@acme.example",
    name: str = "Élodie Martin",
    subject: str = "Coffee next week?",
    sent: str = "2026-09-10T09:30:00Z",
    unsubscribe: bool = False,
    folder: str = "folder-inbox",
    reply_to: tuple[tuple[str, str], ...] = (),
    odata_type: str = "#microsoft.graph.message",
) -> dict[str, Any]:
    """Build one made-up Graph message."""
    headers = [{"name": "List-Unsubscribe", "value": "<https://x.example/u>"}]
    return {
        "@odata.type": odata_type,
        "id": message_id,
        "conversationId": conversation_id,
        "subject": subject,
        "receivedDateTime": sent,
        "sentDateTime": sent,
        "parentFolderId": folder,
        "from": {"emailAddress": {"address": address, "name": name}},
        "toRecipients": [
            {"emailAddress": {"address": "sam.rivera@mailbox.example", "name": "Sam"}}
        ],
        "internetMessageHeaders": headers if unsubscribe else [],
        "replyTo": [
            {"emailAddress": {"address": reply_address, "name": reply_name}}
            for reply_address, reply_name in reply_to
        ],
    }


def mock_folders() -> None:
    """Answer the well-known folder lookups with made-up identifiers."""
    for name in ("junkemail", "deleteditems", "drafts", "outbox"):
        respx.get(f"{MICROSOFT_GRAPH_URL}/me/mailFolders/{name}").mock(
            return_value=httpx.Response(200, json={"id": f"folder-{name}"})
        )


def mock_renewal(refresh_token: str = "new-long-lived-key") -> respx.Route:
    """Answer a renewal with a fresh pair of keys."""
    return respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "made-up-access-key",
                "refresh_token": refresh_token,
                "expires_in": 3599,
            },
        )
    )


@pytest.mark.asyncio
async def test_the_rotated_key_is_saved_before_any_mailbox_call(
    secret_store: SecretStore,
    clock: FixedClock,
) -> None:
    secret_store.put_secret(MICROSOFT_REFRESH_TOKEN, "old-long-lived-key")

    with respx.mock:
        mock_renewal()
        respx.get(url__startswith=f"{MICROSOFT_GRAPH_URL}/me/").mock(
            side_effect=httpx.ConnectError("the run crashed here")
        )
        authenticator = MicrosoftAuthenticator(secret_store, clock)
        async with authenticator, GraphMailbox(authenticator) as mailbox:
            with pytest.raises(SourceUnavailableError):
                await mailbox.list_messages_since(WINDOW_START)

    assert secret_store.get_secret(MICROSOFT_REFRESH_TOKEN) == "new-long-lived-key"


@pytest.mark.asyncio
async def test_a_renewal_that_returns_no_new_key_keeps_the_old_one(
    secret_store: SecretStore,
    clock: FixedClock,
) -> None:
    secret_store.put_secret(MICROSOFT_REFRESH_TOKEN, "old-long-lived-key")

    with respx.mock:
        respx.post(TOKEN_URL).mock(
            return_value=httpx.Response(200, json={"access_token": "a", "expires_in": 3599})
        )
        async with MicrosoftAuthenticator(secret_store, clock) as authenticator:
            assert await authenticator.access_token() == "a"

    assert secret_store.get_secret(MICROSOFT_REFRESH_TOKEN) == "old-long-lived-key"


@pytest.mark.asyncio
async def test_without_a_sign_in_the_owner_is_told_what_to_run(
    secret_store: SecretStore,
    clock: FixedClock,
) -> None:
    async with MicrosoftAuthenticator(secret_store, clock) as authenticator:
        with pytest.raises(SourceAuthError, match="tracker microsoft login"):
            await authenticator.access_token()


@pytest.mark.asyncio
async def test_a_refused_renewal_asks_for_a_new_sign_in(
    secret_store: SecretStore,
    clock: FixedClock,
) -> None:
    secret_store.put_secret(MICROSOFT_REFRESH_TOKEN, "expired-key")

    with respx.mock:
        respx.post(TOKEN_URL).mock(
            return_value=httpx.Response(400, json={"error": "invalid_grant"})
        )
        async with MicrosoftAuthenticator(secret_store, clock) as authenticator:
            with pytest.raises(SourceAuthError, match="sign in again"):
                await authenticator.access_token()


@pytest.mark.asyncio
async def test_a_valid_access_key_is_not_renewed_twice(
    secret_store: SecretStore,
    clock: FixedClock,
) -> None:
    secret_store.put_secret(MICROSOFT_REFRESH_TOKEN, "old-long-lived-key")

    with respx.mock:
        route = mock_renewal()
        async with MicrosoftAuthenticator(secret_store, clock) as authenticator:
            first = await authenticator.access_token()
            second = await authenticator.access_token()

    assert first == second
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_callers_at_the_same_moment_renew_the_key_only_once(
    secret_store: SecretStore,
    clock: FixedClock,
) -> None:
    secret_store.put_secret(MICROSOFT_REFRESH_TOKEN, "old-long-lived-key")
    renewal = InFlight(
        lambda _request: httpx.Response(
            200,
            json={
                "access_token": "made-up-access-key",
                "refresh_token": "new-long-lived-key",
                "expires_in": 3599,
            },
        )
    )

    with respx.mock:
        route = respx.post(TOKEN_URL).mock(side_effect=renewal)
        async with MicrosoftAuthenticator(secret_store, clock) as authenticator:
            keys = await gather_all(authenticator.access_token() for _ in range(5))

    assert keys == ["made-up-access-key"] * 5
    assert route.call_count == 1
    assert secret_store.get_secret(MICROSOFT_REFRESH_TOKEN) == "new-long-lived-key"


@pytest.mark.asyncio
async def test_the_one_time_code_flow_waits_then_stores_the_key(
    secret_store: SecretStore,
    clock: FixedClock,
) -> None:
    waits: list[float] = []

    async def record(seconds: float) -> None:
        waits.append(seconds)

    with respx.mock:
        respx.post(DEVICE_CODE_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "user_code": "AB12-CD34",
                    "verification_uri": "https://microsoft.example/device",
                    "device_code": "made-up-device-code",
                    "interval": 1,
                },
            )
        )
        respx.post(TOKEN_URL).mock(
            side_effect=[
                httpx.Response(400, json={"error": "authorization_pending"}),
                httpx.Response(
                    200,
                    json={
                        "access_token": "made-up-access-key",
                        "refresh_token": "first-long-lived-key",
                        "expires_in": 3599,
                    },
                ),
            ]
        )
        async with MicrosoftAuthenticator(secret_store, clock) as authenticator:
            prompt = await authenticator.request_device_code()
            await authenticator.wait_for_sign_in(prompt, sleep=record)

    assert prompt.user_code == "AB12-CD34"
    assert waits == [1.0]
    assert secret_store.get_secret(MICROSOFT_REFRESH_TOKEN) == "first-long-lived-key"


@pytest.mark.asyncio
async def test_a_sign_in_the_owner_never_finishes_gives_up_cleanly(
    secret_store: SecretStore,
    clock: FixedClock,
) -> None:
    async def no_wait(_seconds: float) -> None:
        return None

    with respx.mock:
        respx.post(DEVICE_CODE_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "user_code": "AB12-CD34",
                    "verification_uri": "https://microsoft.example/device",
                    "device_code": "made-up-device-code",
                    "interval": 1,
                },
            )
        )
        respx.post(TOKEN_URL).mock(
            return_value=httpx.Response(400, json={"error": "authorization_pending"})
        )
        async with MicrosoftAuthenticator(secret_store, clock) as authenticator:
            prompt = await authenticator.request_device_code()
            with pytest.raises(SourceAuthError, match="not completed in time"):
                await authenticator.wait_for_sign_in(prompt, sleep=no_wait, max_polls=3)


@pytest.mark.asyncio
async def test_the_mailbox_listing_follows_the_next_link(
    secret_store: SecretStore,
    clock: FixedClock,
) -> None:
    secret_store.put_secret(MICROSOFT_REFRESH_TOKEN, "old-long-lived-key")
    second_page = f"{MESSAGES_URL}?$skiptoken=made-up-token"

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("$skiptoken") == "made-up-token":
            return httpx.Response(200, json={"value": [graph_message("m-3")]})
        return httpx.Response(
            200,
            json={
                "value": [graph_message("m-1"), graph_message("m-2")],
                "@odata.nextLink": second_page,
            },
        )

    with respx.mock:
        mock_renewal()
        mock_folders()
        respx.get(MESSAGES_URL).mock(side_effect=handle)
        authenticator = MicrosoftAuthenticator(secret_store, clock)
        async with authenticator, GraphMailbox(authenticator) as mailbox:
            messages = await mailbox.list_messages_since(WINDOW_START)

    assert [message.message_id for message in messages] == ["m-1", "m-2", "m-3"]


@pytest.mark.asyncio
async def test_junk_and_deleted_messages_are_never_read(
    secret_store: SecretStore,
    clock: FixedClock,
) -> None:
    secret_store.put_secret(MICROSOFT_REFRESH_TOKEN, "old-long-lived-key")

    with respx.mock:
        mock_renewal()
        mock_folders()
        respx.get(MESSAGES_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "value": [
                        graph_message("m-1"),
                        graph_message("m-junk", folder="folder-junkemail"),
                        graph_message("m-bin", folder="folder-deleteditems"),
                    ]
                },
            )
        )
        authenticator = MicrosoftAuthenticator(secret_store, clock)
        async with authenticator, GraphMailbox(authenticator) as mailbox:
            messages = await mailbox.list_messages_since(WINDOW_START)

    assert [message.message_id for message in messages] == ["m-1"]


@pytest.mark.asyncio
async def test_the_metadata_pass_asks_for_no_body_and_spots_bulk_senders(
    secret_store: SecretStore,
    clock: FixedClock,
) -> None:
    secret_store.put_secret(MICROSOFT_REFRESH_TOKEN, "old-long-lived-key")

    with respx.mock:
        mock_renewal()
        mock_folders()
        route = respx.get(MESSAGES_URL).mock(
            return_value=httpx.Response(
                200, json={"value": [graph_message("m-1", unsubscribe=True)]}
            )
        )
        authenticator = MicrosoftAuthenticator(secret_store, clock)
        async with authenticator, GraphMailbox(authenticator) as mailbox:
            messages = await mailbox.list_messages_since(WINDOW_START)

    selected = route.calls[0].request.url.params["$select"]
    assert "body" not in selected
    assert messages[0].has_list_unsubscribe is True
    assert messages[0].body is None


@pytest.mark.asyncio
async def test_bodies_are_fetched_as_plain_text(
    secret_store: SecretStore,
    clock: FixedClock,
) -> None:
    secret_store.put_secret(MICROSOFT_REFRESH_TOKEN, "old-long-lived-key")

    with respx.mock:
        mock_renewal()
        route = respx.get(f"{MESSAGES_URL}/m-1").mock(
            return_value=httpx.Response(
                200, json={"id": "m-1", "body": {"contentType": "text", "content": "Hello"}}
            )
        )
        authenticator = MicrosoftAuthenticator(secret_store, clock)
        async with authenticator, GraphMailbox(authenticator) as mailbox:
            body = await mailbox.fetch_body("m-1")

    assert body == "Hello"
    assert route.calls[0].request.headers["Prefer"] == 'outlook.body-content-type="text"'


@pytest.mark.asyncio
async def test_the_mailbox_is_never_sent_more_requests_at_once_than_it_accepts(
    secret_store: SecretStore,
    clock: FixedClock,
) -> None:
    secret_store.put_secret(MICROSOFT_REFRESH_TOKEN, "old-long-lived-key")
    wanted = [f"m-{number}" for number in range(GRAPH_CONCURRENT_REQUESTS * 4)]
    in_flight = InFlight(body_answer)

    with respx.mock:
        mock_renewal()
        respx.get(url__startswith=f"{MESSAGES_URL}/").mock(side_effect=in_flight)
        authenticator = MicrosoftAuthenticator(secret_store, clock)
        async with authenticator, GraphMailbox(authenticator) as mailbox:
            bodies = await gather_all(mailbox.fetch_body(message_id) for message_id in wanted)

    assert bodies == [f"body of {message_id}" for message_id in wanted]
    assert in_flight.peak == GRAPH_CONCURRENT_REQUESTS


@pytest.mark.asyncio
async def test_two_threads_read_whole_never_exceed_what_the_mailbox_accepts(
    secret_store: SecretStore,
    clock: FixedClock,
) -> None:
    secret_store.put_secret(MICROSOFT_REFRESH_TOKEN, "old-long-lived-key")
    first = [f"m-{number}" for number in range(GRAPH_CONCURRENT_REQUESTS * 2)]
    second = [f"n-{number}" for number in range(GRAPH_CONCURRENT_REQUESTS * 2)]
    in_flight = InFlight(body_answer)

    with respx.mock:
        mock_renewal()
        respx.get(url__startswith=f"{MESSAGES_URL}/").mock(side_effect=in_flight)
        authenticator = MicrosoftAuthenticator(secret_store, clock)
        async with authenticator, GraphMailbox(authenticator) as mailbox:
            threads = await gather_all([mailbox.fetch_bodies(first), mailbox.fetch_bodies(second)])

    assert threads == [
        [f"body of {message_id}" for message_id in first],
        [f"body of {message_id}" for message_id in second],
    ]
    assert in_flight.peak == GRAPH_CONCURRENT_REQUESTS


@pytest.mark.asyncio
async def test_a_message_identifier_cannot_change_the_address_that_is_called(
    secret_store: SecretStore,
    clock: FixedClock,
) -> None:
    secret_store.put_secret(MICROSOFT_REFRESH_TOKEN, "old-long-lived-key")
    hostile = "../users/other/messages?$select=body#AAMk/+w=="

    with respx.mock:
        mock_renewal()
        route = respx.get(url__startswith=f"{MICROSOFT_GRAPH_URL}/").mock(
            return_value=httpx.Response(200, json={"id": "m-1", "body": {"content": "Hello"}})
        )
        authenticator = MicrosoftAuthenticator(secret_store, clock)
        async with authenticator, GraphMailbox(authenticator) as mailbox:
            await mailbox.fetch_body(hostile)

    request = route.calls[0].request
    assert request.url.raw_path.decode() == (
        "/v1.0/me/messages/..%2Fusers%2Fother%2Fmessages%3F%24select=body%23AAMk%2F%2Bw=="
        "?%24select=id%2Cbody"
    )
    assert request.url.fragment == ""


@pytest.mark.asyncio
async def test_a_rejected_mailbox_key_is_reported_in_plain_words(
    secret_store: SecretStore,
    clock: FixedClock,
) -> None:
    secret_store.put_secret(MICROSOFT_REFRESH_TOKEN, "old-long-lived-key")

    with respx.mock:
        mock_renewal()
        respx.get(url__startswith=f"{MICROSOFT_GRAPH_URL}/me/").mock(
            return_value=httpx.Response(401, json={})
        )
        authenticator = MicrosoftAuthenticator(secret_store, clock)
        async with authenticator, GraphMailbox(authenticator) as mailbox:
            with pytest.raises(SourceAuthError, match="microsoft login"):
                await mailbox.list_messages_since(WINDOW_START)


class _KeyThatExpires:
    """Hands out a new access key on every call, as renewal would once one lapses."""

    def __init__(self) -> None:
        self.handed_out = 0

    async def access_token(self) -> str:
        """Return the next key."""
        self.handed_out += 1
        return f"key-{self.handed_out}"


class _ExpiresDuringTheRetry:
    """Asks for a retry once; by the time it comes, the first key has expired."""

    def __init__(self) -> None:
        self.slowed_down = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """Answer one request."""
        if request.headers["Authorization"] != "Bearer key-1":
            return body_answer(request)
        if self.slowed_down:
            return httpx.Response(401, json={})
        self.slowed_down = True
        return httpx.Response(503, json={})


@pytest.mark.asyncio
async def test_a_key_that_expires_while_a_request_is_retried_is_renewed_not_reported() -> None:
    """A retry may wait longer than the key's renewal margin.

    Each attempt must carry a key that is valid at that moment; reusing the
    first one turns a slow mailbox into a false "sign in again".
    """
    keys = _KeyThatExpires()

    with respx.mock:
        route = respx.get(f"{MESSAGES_URL}/m-1").mock(side_effect=_ExpiresDuringTheRetry())
        async with GraphMailbox(keys) as mailbox:
            body = await mailbox.fetch_body("m-1")

    assert body == "body of m-1"
    assert [call.request.headers["Authorization"] for call in route.calls] == [
        "Bearer key-1",
        "Bearer key-2",
    ]


@pytest.mark.asyncio
async def test_the_sign_in_check_renews_a_key_that_expires_during_a_retry() -> None:
    keys = _KeyThatExpires()

    with respx.mock:
        route = respx.get(url__startswith=f"{MICROSOFT_GRAPH_URL}/").mock(
            side_effect=_ExpiresDuringTheRetry()
        )
        async with GraphProbe(keys) as probe:
            await probe.check_mailbox()

    assert [call.request.headers["Authorization"] for call in route.calls] == [
        "Bearer key-1",
        "Bearer key-2",
    ]
