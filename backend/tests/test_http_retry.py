"""One dropped connection must not end a collection of hundreds of requests."""

from __future__ import annotations

import httpx
import pytest

from tracker.shared.http import get_with_retries, request_with_retries


class _Sleeper:
    """Records what would have been waited, without waiting."""

    def __init__(self) -> None:
        self.waits: list[float] = []

    async def __call__(self, seconds: float) -> None:
        """Pretend to wait."""
        self.waits.append(seconds)


def _client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler)


@pytest.mark.asyncio
async def test_a_dropped_connection_is_tried_again() -> None:
    calls = {"n": 0}

    def handle(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.ReadError("connection dropped", request=request)
        return httpx.Response(200, json={"ok": True})

    sleeper = _Sleeper()
    async with _client(httpx.MockTransport(handle)) as client:
        response = await get_with_retries(
            client, "https://example.test/x", source="mailbox", sleep=sleeper
        )

    assert response.status_code == 200
    assert calls["n"] == 3
    assert len(sleeper.waits) == 2


@pytest.mark.asyncio
async def test_giving_up_raises_the_transport_error() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadError("connection dropped", request=request)

    sleeper = _Sleeper()
    async with _client(httpx.MockTransport(handle)) as client:
        with pytest.raises(httpx.ReadError):
            await get_with_retries(
                client, "https://example.test/x", source="mailbox", attempts=3, sleep=sleeper
            )

    assert len(sleeper.waits) == 2


@pytest.mark.asyncio
async def test_being_asked_to_slow_down_is_honoured_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The suite-wide fixture removes every wait; this test is about the wait
    # itself, so it restores the real cap.
    monkeypatch.setattr("tracker.shared.http.SOURCE_RETRY_AFTER_CAP_SECONDS", 60.0)
    calls = {"n": 0}

    def handle(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "7"})
        return httpx.Response(200, json={"ok": True})

    sleeper = _Sleeper()
    async with _client(httpx.MockTransport(handle)) as client:
        response = await get_with_retries(
            client, "https://example.test/x", source="mailbox", sleep=sleeper
        )

    assert response.status_code == 200
    assert sleeper.waits == [7.0]


@pytest.mark.asyncio
async def test_an_unreasonable_wait_is_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("tracker.shared.http.SOURCE_RETRY_AFTER_CAP_SECONDS", 60.0)

    def handle(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, headers={"Retry-After": "99999"})

    sleeper = _Sleeper()
    async with _client(httpx.MockTransport(handle)) as client:
        response = await get_with_retries(
            client, "https://example.test/x", source="mailbox", attempts=2, sleep=sleeper
        )

    assert response.status_code == 503
    assert sleeper.waits == [60.0]


@pytest.mark.asyncio
async def test_a_refused_key_is_never_retried() -> None:
    calls = {"n": 0}

    def handle(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401)

    sleeper = _Sleeper()
    async with _client(httpx.MockTransport(handle)) as client:
        response = await get_with_retries(
            client, "https://example.test/x", source="mailbox", sleep=sleeper
        )

    assert response.status_code == 401
    assert calls["n"] == 1
    assert sleeper.waits == []


@pytest.mark.asyncio
async def test_a_sign_in_is_retried_only_before_it_was_sent() -> None:
    """A refresh rotates the key, so a lost answer must not be sent twice.

    A connection that never opened cannot have rotated anything, so that one is
    safe to try again.
    """
    calls = {"connect": 0, "read": 0}

    def connect_fails(request: httpx.Request) -> httpx.Response:
        calls["connect"] += 1
        if calls["connect"] < 2:
            raise httpx.ConnectTimeout("never opened", request=request)
        return httpx.Response(200, json={"ok": True})

    def read_fails(request: httpx.Request) -> httpx.Response:
        calls["read"] += 1
        raise httpx.ReadError("answer lost", request=request)

    sleeper = _Sleeper()
    async with _client(httpx.MockTransport(connect_fails)) as client:
        response = await request_with_retries(
            client, "POST", "https://example.test/token",
            source="microsoft sign-in", retry_after_send=False, sleep=sleeper,
        )
    assert response.status_code == 200
    assert calls["connect"] == 2

    async with _client(httpx.MockTransport(read_fails)) as client:
        with pytest.raises(httpx.ReadError):
            await request_with_retries(
                client, "POST", "https://example.test/token",
                source="microsoft sign-in", retry_after_send=False, sleep=sleeper,
            )
    assert calls["read"] == 1
