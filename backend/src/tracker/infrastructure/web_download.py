"""Downloads one file over HTTPS into memory, never more than a set size.

The set-up uses it for the prebuilt dashboard and its checksum, which GitHub
serves from a release (after a redirect to its file storage). The answer is
read piece by piece and dropped as soon as it grows past the limit, so a
wrong or hostile file can never fill the memory. Nothing is written to disk.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Final

import httpx

from tracker.shared.constants.collection import HTTP_TIMEOUT_SECONDS
from tracker.shared.constants.retry import SOURCE_REQUEST_ATTEMPTS, SOURCE_REQUEST_DELAY_SECONDS
from tracker.shared.errors import (
    DownloadTooLargeError,
    SourceRequestRejectedError,
    SourceUnavailableError,
)
from tracker.shared.http import RETRYABLE_STATUSES
from tracker.shared.logging import get_logger

_log = get_logger(__name__)

#: The status of a file that was found.
_FOUND: Final[int] = 200


class WebDownload:
    """Fetches a whole file, following redirects, with bounded linear retries."""

    def __init__(
        self,
        http: httpx.AsyncClient | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        """Bind the downloader to a connection pool, or let it open one per call.

        Args:
            http: An open pool; a short-lived one is used when omitted.
            sleep: How to wait between attempts; replaced in tests.
        """
        self._http = http
        self._sleep = asyncio.sleep if sleep is None else sleep

    async def fetch(self, url: str, max_bytes: int) -> bytes:
        """Download a file.

        Args:
            url: Its address.
            max_bytes: The most it may weigh.

        Returns:
            Its content.

        Raises:
            DownloadTooLargeError: If it is larger than ``max_bytes``.
            SourceRequestRejectedError: If the address holds no such file.
            SourceUnavailableError: If it could not be downloaded.
        """
        if self._http is not None:
            return await self._attempts(self._http, url, max_bytes)
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS, follow_redirects=True) as http:
            return await self._attempts(http, url, max_bytes)

    async def _attempts(self, http: httpx.AsyncClient, url: str, max_bytes: int) -> bytes:
        """Try a few times when the failure looks temporary."""
        for attempt in range(1, SOURCE_REQUEST_ATTEMPTS + 1):
            try:
                return await _download(http, url, max_bytes)
            except _TemporaryDownloadError as failure:
                _log.warning("download_retried", attempt=attempt, reason=failure.reason)
                if attempt < SOURCE_REQUEST_ATTEMPTS:
                    await self._sleep(SOURCE_REQUEST_DELAY_SECONDS)
        message = f"{url} could not be downloaded"
        raise SourceUnavailableError(message)


class _TemporaryDownloadError(Exception):
    """A failure worth one more attempt: the connection, or a busy server."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


async def _download(http: httpx.AsyncClient, url: str, max_bytes: int) -> bytes:
    """Read the answer piece by piece, stopping once it grows past the limit."""
    try:
        async with http.stream("GET", url, follow_redirects=True) as response:
            _check_status(response.status_code, url)
            received = bytearray()
            async for piece in response.aiter_bytes():
                received.extend(piece)
                if len(received) > max_bytes:
                    message = f"{url} is larger than {max_bytes} bytes"
                    raise DownloadTooLargeError(message)
            return bytes(received)
    except httpx.HTTPError as error:
        raise _TemporaryDownloadError(type(error).__name__) from error


def _check_status(status: int, url: str) -> None:
    """Accept a found file; say why anything else is not one."""
    if status == _FOUND:
        return
    if status in RETRYABLE_STATUSES:
        raise _TemporaryDownloadError(f"status {status}")
    _log.error("download_refused", status=status)
    message = f"{url} answered status {status}"
    raise SourceRequestRejectedError(message)
