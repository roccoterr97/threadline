"""Paged reader for the LinkedIn member snapshot.

The snapshot endpoint hands back the member's own message archive one page at a
time. Two of its habits shape this module:

* Pages are numbered from zero and the page *after* the last one answers HTTP
  404. That 404 means "finished", not "broken", so it ends the loop quietly.
* The ``total`` field it reports cannot be trusted, so nothing here reads it.

The reader returns the rows exactly as LinkedIn spelled them. Turning a row into
a message is :mod:`tracker.infrastructure.linkedin.parser`'s job.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from types import TracebackType
from typing import Any, Final, Self

import httpx
from pydantic import SecretStr

from tracker.shared.constants.collection import (
    HTTP_TIMEOUT_SECONDS,
    LINKEDIN_API_VERSION,
    LINKEDIN_INBOX_DOMAIN,
    LINKEDIN_MAX_PAGES,
    LINKEDIN_PAGE_SIZE,
    LINKEDIN_SNAPSHOT_URL,
)
from tracker.shared.errors import SourceAuthError, SourceUnavailableError
from tracker.shared.http import get_with_retries
from tracker.shared.logging import get_logger

#: Status the endpoint answers for the page after the last one.
PAGE_AFTER_LAST_STATUS: Final[int] = 404

#: Status the endpoint answers when the key is expired or wrong.
UNAUTHORISED_STATUS: Final[int] = 401

#: Status the endpoint answers when the key lacks the portability permission.
FORBIDDEN_STATUS: Final[int] = 403

_ELEMENTS_KEY: Final[str] = "elements"
_SNAPSHOT_DATA_KEY: Final[str] = "snapshotData"

_log = get_logger(__name__)


class LinkedInSnapshotClient:
    """Reads the member's message archive, one page at a time.

    Use it as an async context manager so the underlying connection pool is
    always closed::

        async with LinkedInSnapshotClient(token) as client:
            rows = [row async for row in client.inbox_rows()]
    """

    def __init__(self, access_token: SecretStr) -> None:
        """Bind the client to a key.

        Args:
            access_token: The Member Data Portability key from the environment.
        """
        self._access_token = access_token
        self._http: httpx.AsyncClient | None = None

    async def __aenter__(self) -> Self:
        """Open the connection pool."""
        self._http = httpx.AsyncClient(
            timeout=HTTP_TIMEOUT_SECONDS,
            headers={
                "Authorization": f"Bearer {self._access_token.get_secret_value()}",
                "Linkedin-Version": LINKEDIN_API_VERSION,
            },
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the connection pool."""
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def inbox_rows(self) -> AsyncIterator[dict[str, str]]:
        """Yield every archived message row, page after page.

        Yields:
            One raw snapshot row per archived message.

        Raises:
            SourceAuthError: If LinkedIn rejected the key.
            SourceUnavailableError: If LinkedIn could not be reached, answered
                an unexpected status, or sent something that is not JSON.
        """
        rows_read = 0
        seen: set[str] = set()
        for page_index in range(LINKEDIN_MAX_PAGES):
            page = await self._read_page(page_index)
            if page is None:
                _log.info("linkedin_snapshot_read", pages=page_index, rows=rows_read)
                return
            fresh = 0
            for row in page:
                signature = _row_signature(row)
                if signature in seen:
                    continue
                seen.add(signature)
                fresh += 1
                rows_read += 1
                yield row
            # LinkedIn began serving the whole archive twice on 2026-09-19:
            # pages 5 to 9 repeated pages 0 to 4, shuffled, before the 404. A
            # page that adds nothing new means the archive has come round
            # again, so there is nothing further to read.
            if fresh == 0:
                _log.info(
                    "linkedin_snapshot_read",
                    pages=page_index,
                    rows=rows_read,
                    stopped="archive repeated",
                )
                return
        message = f"LinkedIn snapshot did not end within {LINKEDIN_MAX_PAGES} pages"
        raise SourceUnavailableError(message)

    async def check_access(self) -> None:
        """Ask for the first page once, to prove the key works.

        An empty archive counts as working: LinkedIn answers "no data" with the
        same status it uses after the last page.

        Raises:
            SourceAuthError: If the key is wrong or expired, or lacks the data
                portability permission.
            SourceUnavailableError: If LinkedIn could not be reached or
                answered an unexpected status.
        """
        response = await self._request(0)
        status = response.status_code
        if status in {httpx.codes.OK, PAGE_AFTER_LAST_STATUS}:
            return
        if status == UNAUTHORISED_STATUS:
            message = "LinkedIn did not accept the key - it is wrong or has expired"
            raise SourceAuthError(message)
        if status == FORBIDDEN_STATUS:
            message = "LinkedIn accepted the key, but it lacks the data portability permission"
            raise SourceAuthError(message)
        _log.error("linkedin_check_failed", status=status)
        message = f"LinkedIn answered status {status}"
        raise SourceUnavailableError(message)

    async def _read_page(self, page_index: int) -> list[dict[str, str]] | None:
        """Read one page.

        Args:
            page_index: Zero-based page number.

        Returns:
            The page's rows, or ``None`` once the archive is exhausted.

        Raises:
            SourceAuthError: If LinkedIn rejected the key.
            SourceUnavailableError: If the request failed for any other reason.
        """
        response = await self._request(page_index)
        if response.status_code == PAGE_AFTER_LAST_STATUS:
            return None
        if response.status_code == UNAUTHORISED_STATUS:
            message = "LinkedIn key rejected — renew it"
            raise SourceAuthError(message)
        if response.status_code != httpx.codes.OK:
            _log.error("linkedin_request_failed", status=response.status_code, page=page_index)
            message = f"LinkedIn answered status {response.status_code}"
            raise SourceUnavailableError(message)
        return _extract_rows(response, page_index)

    async def _request(self, page_index: int) -> httpx.Response:
        """Ask for one page.

        Args:
            page_index: Zero-based page number.

        Returns:
            The raw response, whatever its status.

        Raises:
            SourceUnavailableError: If the request could not be completed, or if
                the client is used outside its context manager.
        """
        if self._http is None:
            message = "LinkedIn client used outside its context manager"
            raise SourceUnavailableError(message)
        try:
            return await get_with_retries(
                self._http,
                LINKEDIN_SNAPSHOT_URL,
                params={
                    "q": "criteria",
                    "domain": LINKEDIN_INBOX_DOMAIN,
                    "start": page_index,
                    "count": LINKEDIN_PAGE_SIZE,
                },
                source="linkedin",
            )
        except httpx.HTTPError as error:
            _log.error("linkedin_unreachable", error_type=type(error).__name__, page=page_index)
            message = "LinkedIn could not be reached"
            raise SourceUnavailableError(message) from error



def _row_signature(row: dict[str, str]) -> str:
    """Identify one snapshot row, so a repeat of it can be recognised.

    Args:
        row: One row of the snapshot.

    Returns:
        A stable digest of the whole row.
    """
    material = "\u0000".join(f"{key}={row[key]}" for key in sorted(row))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _extract_rows(response: httpx.Response, page_index: int) -> list[dict[str, str]]:
    """Pull the message rows out of one snapshot page.

    Args:
        response: The successful response.
        page_index: Zero-based page number, for the log line.

    Returns:
        Every row of every element on the page.

    Raises:
        SourceUnavailableError: If the body is not the JSON shape expected.
    """
    try:
        payload: Any = response.json()
    except ValueError as error:
        _log.error("linkedin_payload_unreadable", page=page_index)
        message = "LinkedIn answered with something that is not JSON"
        raise SourceUnavailableError(message) from error
    if not isinstance(payload, dict):
        message = "LinkedIn answered with an unexpected payload shape"
        raise SourceUnavailableError(message)
    rows: list[dict[str, str]] = []
    for element in payload.get(_ELEMENTS_KEY) or []:
        if not isinstance(element, dict):
            continue
        for row in element.get(_SNAPSHOT_DATA_KEY) or []:
            if isinstance(row, dict):
                rows.append({str(key): str(value) for key, value in row.items()})
    return rows
