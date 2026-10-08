"""One retry policy for every request to an outside source.

A daily run makes hundreds of requests to LinkedIn and to the mailbox, one
after another. Without retries a single dropped connection ends the whole
collection, which is what happened on 2026-09-19: the mailbox read failed
five minutes in, twice, on a transport error rather than a refusal.

Retries are bounded and linear, as required by the backend standards. Only
failures that can plausibly succeed on a second attempt are retried: transport
errors, the source asking us to slow down, and its own server errors. A refused
key or a missing item is returned to the caller untouched, because retrying it
would only waste time.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Final

import httpx

from tracker.shared.constants.retry import (
    SOURCE_REQUEST_ATTEMPTS,
    SOURCE_REQUEST_DELAY_SECONDS,
    SOURCE_RETRY_AFTER_CAP_SECONDS,
)
from tracker.shared.logging import get_logger

_log = get_logger(__name__)

#: Statuses worth trying again: "too many requests" and the source's own faults.
RETRYABLE_STATUSES: Final[frozenset[int]] = frozenset({408, 425, 429, 500, 502, 503, 504})


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """Read a ``Retry-After`` header expressed in seconds.

    Args:
        response: The answer that asked us to wait.

    Returns:
        The capped wait, or ``None`` when the header is absent or not a number.
    """
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        seconds = float(raw)
    except ValueError:
        # The header may also hold a date. Falling back to the fixed delay is
        # simpler than parsing it, and the cap applies either way.
        return None
    return min(max(seconds, 0.0), SOURCE_RETRY_AFTER_CAP_SECONDS)


#: Failures that happened before the request reached the source, so nothing can
#: have been acted on and trying again is always safe.
CONNECT_ERRORS: Final[tuple[type[httpx.HTTPError], ...]] = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
)


async def request_with_retries(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    fresh_headers: Callable[[], Awaitable[dict[str, str]]] | None = None,
    data: dict[str, str] | None = None,
    json_body: object | None = None,
    files: list[tuple[str, tuple[str, bytes, str]]] | None = None,
    source: str,
    retry_after_send: bool = True,
    attempts: int | None = None,
    delay: float | None = None,
    sleep: Callable[[float], Awaitable[None]] | None = None,
) -> httpx.Response:
    """Send one request, trying again when the failure looks temporary.

    Args:
        client: The open connection pool to send through.
        method: The HTTP method, such as ``GET`` or ``POST``.
        url: The address to call.
        params: Query parameters, or ``None`` for a ready-made link.
        headers: Headers to send, including authorisation.
        fresh_headers: Builds headers again before every attempt, such as an
            access key: a retry can outlast the key's renewal margin, and a
            key read once before the first attempt would then be refused.
        data: Form fields, for a request that carries a body.
        json_body: A JSON body, for a request that carries one instead.
        files: Files to upload as ``(field, (file name, content, type))``;
            together with ``data`` they make a multipart body.
        source: Name of the source, used in the log line only.
        retry_after_send: Whether a failure *after* the request was sent may be
            retried. True for a plain read. False for anything that changes
            something at the source: a sign-in refresh rotates the key, so a
            lost answer means the retry would present a key that is already
            spent, and a clear "could not be reached" is better than a
            misleading "sign in again".
        attempts: How many times to try in total; the configured default when
            omitted. At least one.
        delay: Seconds between two attempts; the configured default when
            omitted.
        sleep: How to wait; replaced in tests so they never really wait.

    The three defaults are read when the call is made, not when this module is
    imported, so a test can shorten them for the whole suite.

    Returns:
        The last answer received, successful or not. Statuses the caller has to
        interpret, such as a refused key, are returned rather than raised.

    Raises:
        httpx.HTTPError: If every attempt failed at the transport level.
    """
    attempts = SOURCE_REQUEST_ATTEMPTS if attempts is None else attempts
    delay = SOURCE_REQUEST_DELAY_SECONDS if delay is None else delay
    sleep = asyncio.sleep if sleep is None else sleep
    last_error: httpx.HTTPError | None = None
    for attempt in range(1, max(attempts, 1) + 1):
        attempt_headers = headers
        if fresh_headers is not None:
            attempt_headers = {**(headers or {}), **await fresh_headers()}
        try:
            response = await client.request(
                method,
                url,
                params=params,
                headers=attempt_headers,
                data=data,
                json=json_body,
                files=files,
            )
        except httpx.HTTPError as error:
            if not retry_after_send and not isinstance(error, CONNECT_ERRORS):
                raise
            last_error = error
            wait = delay
        else:
            if response.status_code not in RETRYABLE_STATUSES:
                return response
            last_error = None
            wait = _retry_after_seconds(response) or delay
            if attempt == attempts:
                return response
        _log.warning(
            "source_request_retried",
            source=source,
            attempt=attempt,
            attempts=attempts,
            reason=type(last_error).__name__ if last_error else "status",
        )
        if attempt == attempts:
            break
        await sleep(wait)
    if last_error is not None:
        raise last_error
    message = "no attempt was made"  # pragma: no cover - guarded by max(attempts, 1)
    raise RuntimeError(message)  # pragma: no cover


async def get_with_retries(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    fresh_headers: Callable[[], Awaitable[dict[str, str]]] | None = None,
    source: str,
    attempts: int | None = None,
    delay: float | None = None,
    sleep: Callable[[float], Awaitable[None]] | None = None,
) -> httpx.Response:
    """Send one GET, trying again when the failure looks temporary.

    Reading changes nothing at the source, so every temporary failure is
    retried. See :func:`request_with_retries` for the arguments.

    Returns:
        The last answer received, successful or not.
    """
    return await request_with_retries(
        client,
        "GET",
        url,
        params=params,
        headers=headers,
        fresh_headers=fresh_headers,
        source=source,
        attempts=attempts,
        delay=delay,
        sleep=sleep,
    )
