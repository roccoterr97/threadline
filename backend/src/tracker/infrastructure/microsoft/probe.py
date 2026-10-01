"""Two small Graph calls that prove the mailbox and the calendar answer.

Both use permissions Threadline already holds, so checking them never asks
for more: the inbox folder needs Mail.Read, and the calendar's owner — which is
also the signed-in address — needs Calendars.Read.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any, Final, Self

import httpx

from tracker.infrastructure.microsoft.client import AccessTokenProvider
from tracker.shared.constants.collection import HTTP_TIMEOUT_SECONDS, MICROSOFT_GRAPH_URL
from tracker.shared.errors import SourceAuthError, SourceUnavailableError
from tracker.shared.http import get_with_retries
from tracker.shared.logging import get_logger

#: The inbox folder, asking for nothing but its identifier.
INBOX_URL: Final[str] = f"{MICROSOFT_GRAPH_URL}/me/mailFolders/inbox"

#: The default calendar, asking only for its identifier and owner.
CALENDAR_URL: Final[str] = f"{MICROSOFT_GRAPH_URL}/me/calendar"

_REFUSED_STATUSES: Final[frozenset[int]] = frozenset({401, 403})

_log = get_logger(__name__)


class GraphProbe:
    """Makes the two smallest possible reads on Microsoft Graph."""

    def __init__(self, tokens: AccessTokenProvider) -> None:
        """Bind the probe to a key supplier.

        Args:
            tokens: Supplies a valid access key, renewing it when needed.
        """
        self._tokens = tokens
        self._http: httpx.AsyncClient | None = None

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

    async def check_mailbox(self) -> None:
        """Read the inbox folder's identifier.

        Raises:
            SourceAuthError: If Microsoft refused the key.
            SourceUnavailableError: If Microsoft could not be reached.
        """
        await self._get(INBOX_URL, {"$select": "id"}, what="mailbox")

    async def calendar_owner(self) -> str:
        """Read the default calendar's owner, which is the signed-in address.

        Returns:
            The address, lower-cased; empty when Graph does not say.

        Raises:
            SourceAuthError: If Microsoft refused the key.
            SourceUnavailableError: If Microsoft could not be reached.
        """
        payload = await self._get(CALENDAR_URL, {"$select": "id,owner"}, what="calendar")
        owner = payload.get("owner")
        if not isinstance(owner, dict):
            return ""
        return str(owner.get("address") or "").strip().lower()

    async def _get(self, url: str, params: dict[str, str], *, what: str) -> dict[str, Any]:
        """Send one read and return its JSON object."""
        if self._http is None:
            message = "Graph probe used outside its context manager"
            raise SourceUnavailableError(message)
        headers = {"Authorization": f"Bearer {await self._tokens.access_token()}"}
        try:
            response = await get_with_retries(
                self._http, url, params=params, headers=headers, source="microsoft graph"
            )
        except httpx.HTTPError as error:
            _log.error("graph_unreachable", error_type=type(error).__name__, what=what)
            message = "Microsoft could not be reached"
            raise SourceUnavailableError(message) from error
        return _payload(response, what)


def _payload(response: httpx.Response, what: str) -> dict[str, Any]:
    """Return the JSON object of a successful answer, or raise a typed error."""
    if response.status_code in _REFUSED_STATUSES:
        message = f"Microsoft refused to open the {what}"
        raise SourceAuthError(message)
    if not response.is_success:
        message = f"Microsoft answered status {response.status_code} for the {what}"
        raise SourceUnavailableError(message)
    try:
        payload: Any = response.json()
    except ValueError as error:
        message = "Microsoft answered with something that is not JSON"
        raise SourceUnavailableError(message) from error
    return payload if isinstance(payload, dict) else {}
