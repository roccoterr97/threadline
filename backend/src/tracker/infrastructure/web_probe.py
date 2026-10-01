"""Whether a web address answers: the published dashboard, and the "Refresh now" function."""

from __future__ import annotations

import httpx

from tracker.shared.constants.collection import HTTP_TIMEOUT_SECONDS
from tracker.shared.errors import SourceUnavailableError
from tracker.shared.http import get_with_retries, request_with_retries
from tracker.shared.logging import get_logger

_log = get_logger(__name__)


class WebProbe:
    """Fetches one page and reports its status, following redirects."""

    def __init__(self, http: httpx.AsyncClient | None = None) -> None:
        """Bind the probe to a connection pool, or let it open one per call.

        Args:
            http: An open pool; a short-lived one is used when omitted.
        """
        self._http = http

    async def status_of(self, url: str) -> int:
        """Fetch a page and return its final status.

        Args:
            url: The address to open.

        Returns:
            The HTTP status after redirects.

        Raises:
            SourceUnavailableError: If the address could not be reached at all.
        """
        if self._http is not None:
            return await self._fetch(self._http, url)
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS, follow_redirects=True) as http:
            return await self._fetch(http, url)

    async def status_of_post(self, url: str) -> int:
        """Send an empty POST with no sign-in and return the status.

        A guarded function refuses it before doing anything, so this changes
        nothing; it only shows whether the function is there.

        Args:
            url: The function's address.

        Returns:
            The HTTP status.

        Raises:
            SourceUnavailableError: If the address could not be reached at all.
        """
        if self._http is not None:
            return await self._post(self._http, url)
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as http:
            return await self._post(http, url)

    @staticmethod
    async def _post(http: httpx.AsyncClient, url: str) -> int:
        """Send the empty POST through the shared retry policy."""
        try:
            response = await request_with_retries(http, "POST", url, source="function")
        except httpx.HTTPError as error:
            _log.error("function_unreachable", error_type=type(error).__name__)
            message = "the Supabase project could not be reached"
            raise SourceUnavailableError(message) from error
        return response.status_code

    @staticmethod
    async def _fetch(http: httpx.AsyncClient, url: str) -> int:
        """Send the request through the shared retry policy."""
        try:
            response = await get_with_retries(http, url, source="dashboard")
        except httpx.HTTPError as error:
            _log.error("dashboard_unreachable", error_type=type(error).__name__)
            message = "the dashboard address could not be reached"
            raise SourceUnavailableError(message) from error
        return response.status_code
