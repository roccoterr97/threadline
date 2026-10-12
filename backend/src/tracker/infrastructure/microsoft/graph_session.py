"""One connection to Microsoft Graph, shared by every reader that uses it.

Every read goes through :meth:`GraphSession.get`: it renews the access key
before each attempt, retries what can succeed a second time (Microsoft's
"slow down" answer included, honouring its ``Retry-After``), keeps no more
requests in flight than Microsoft accepts, and turns the answer into a JSON
object or a typed error. The mailbox reader and the Teams chat reader differ
only in what they ask for.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, Final, Protocol, Self

import httpx

from tracker.shared.constants.collection import (
    GRAPH_CONCURRENT_REQUESTS,
    GRAPH_MAX_PAGES,
    HTTP_TIMEOUT_SECONDS,
)
from tracker.shared.errors import SourceAuthError, SourceUnavailableError
from tracker.shared.http import get_with_retries
from tracker.shared.logging import get_logger

#: Where Graph names the next page of a listing.
NEXT_LINK: Final[str] = "@odata.nextLink"

#: Where Graph puts the items of a page.
VALUE: Final[str] = "value"

#: Statuses that mean the key itself was refused, unless a reader says otherwise.
_KEY_REFUSED: Final[frozenset[int]] = frozenset({httpx.codes.UNAUTHORIZED})

_log = get_logger(__name__)


class AccessTokenProvider(Protocol):
    """Supplies a usable key, renewing it when it has expired."""

    async def access_token(self) -> str:
        """Return an access key that is valid right now."""
        ...


class GraphSession:
    """Sends authenticated reads to Graph and reads their answers."""

    def __init__(
        self,
        tokens: AccessTokenProvider,
        *,
        what: str,
        redo_command: str,
        refused_statuses: frozenset[int] = _KEY_REFUSED,
    ) -> None:
        """Bind the session to a key supplier.

        Args:
            tokens: Supplies a valid access key before every attempt.
            what: What is being read, as the owner would name it ("mailbox").
            redo_command: What the owner runs to sign in again.
            refused_statuses: Statuses that mean the sign-in is not allowed to
                read this, rather than a passing fault.
        """
        self._tokens = tokens
        self._what = what
        self._redo_command = redo_command
        self._refused_statuses = refused_statuses
        self._http: httpx.AsyncClient | None = None
        # Callers may ask for many things at once; this is the one place that
        # keeps Graph from being sent more than Microsoft accepts.
        self._slots = asyncio.Semaphore(GRAPH_CONCURRENT_REQUESTS)

    async def __aenter__(self) -> Self:
        """Open the connection pool."""
        self._http = httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS)
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

    async def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        *,
        headers: dict[str, str] | None = None,
        allow_missing: bool = False,
    ) -> dict[str, Any]:
        """Send one authenticated read and return its JSON object.

        Args:
            url: The address to call.
            params: Query parameters, or ``None`` for a ready-made link.
            headers: Extra headers, such as the plain-text preference.
            allow_missing: Whether a 404 is an expected, empty answer.

        Returns:
            The decoded object, empty when a tolerated 404 came back.

        Raises:
            SourceAuthError: If the key was refused.
            SourceUnavailableError: If Graph could not be reached or answered an
                unexpected status.
        """
        if self._http is None:
            message = f"{self._what} client used outside its context manager"
            raise SourceUnavailableError(message)
        # The slot is held through the retries too: a request waiting because
        # Microsoft said "slow down" must not make room for another one.
        async with self._slots:
            try:
                response = await get_with_retries(
                    self._http,
                    url,
                    params=params,
                    headers=headers,
                    fresh_headers=self._authorisation,
                    source=self._what,
                )
            except httpx.HTTPError as error:
                _log.error("graph_unreachable", what=self._what, error_type=type(error).__name__)
                message = f"the {self._what} could not be reached"
                raise SourceUnavailableError(message) from error
        return self._read(response, allow_missing=allow_missing)

    async def pages(
        self,
        url: str,
        params: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> AsyncGenerator[dict[str, Any]]:
        """Read a listing page by page, following ``@odata.nextLink``.

        Args:
            url: The first page's address.
            params: Query parameters for the first page only; Graph repeats
                them inside each ``@odata.nextLink``.
            headers: Extra headers sent with every page.

        Yields:
            Each page's decoded object. A caller may stop early.

        Raises:
            SourceUnavailableError: If the listing never ends.
        """
        next_url: str | None = url
        next_params: dict[str, Any] | None = params
        for _ in range(GRAPH_MAX_PAGES):
            if next_url is None:
                return
            payload = await self.get(next_url, next_params, headers=headers)
            yield payload
            following = payload.get(NEXT_LINK)
            next_url = following if isinstance(following, str) and following else None
            next_params = None
        message = f"{self._what} listing did not end within {GRAPH_MAX_PAGES} pages"
        raise SourceUnavailableError(message)

    async def _authorisation(self) -> dict[str, str]:
        """The authorisation header, with a key valid at this very attempt."""
        return {"Authorization": f"Bearer {await self._tokens.access_token()}"}

    def _read(self, response: httpx.Response, *, allow_missing: bool) -> dict[str, Any]:
        """Turn a Graph response into a payload, or into a typed error.

        Args:
            response: The response to read.
            allow_missing: Whether a 404 is an expected, empty answer.

        Returns:
            The decoded object.

        Raises:
            SourceAuthError: If the key was refused.
            SourceUnavailableError: If the status or the body was unusable.
        """
        if allow_missing and response.status_code == httpx.codes.NOT_FOUND:
            return {}
        if response.status_code in self._refused_statuses:
            _log.error("graph_key_refused", what=self._what, status=response.status_code)
            message = f"the {self._what} key was rejected — run '{self._redo_command}' again"
            raise SourceAuthError(message)
        if not response.is_success:
            _log.error("graph_request_failed", what=self._what, status=response.status_code)
            message = f"the {self._what} answered status {response.status_code}"
            raise SourceUnavailableError(message)
        try:
            payload: Any = response.json()
        except ValueError as error:
            message = f"the {self._what} answered with something that is not JSON"
            raise SourceUnavailableError(message) from error
        if not isinstance(payload, dict):
            message = f"the {self._what} answered with an unexpected payload shape"
            raise SourceUnavailableError(message)
        return payload


def parse_timestamp(raw: Any) -> datetime | None:  # noqa: ANN401 - raw Graph payload
    """Read a Graph timestamp.

    Args:
        raw: A value such as ``2026-09-18T07:14:22Z``.

    Returns:
        The instant in UTC, or ``None`` when the value cannot be read.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        moment = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)
