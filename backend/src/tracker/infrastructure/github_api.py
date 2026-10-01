"""GitHub's REST API, as the "Refresh now" set-up uses it: one harmless read.

The set-up proves a fine-grained token can see the workflow by reading the
workflow's description. It never starts the workflow. The token is sent in the
``Authorization`` header only and never logged.
"""

from __future__ import annotations

from typing import Any, Final

import httpx
from pydantic import SecretStr

from tracker.shared.constants.collection import HTTP_TIMEOUT_SECONDS
from tracker.shared.constants.github import (
    GITHUB_API_URL,
    GITHUB_API_VERSION,
    WORKFLOW_API_PATH,
)
from tracker.shared.errors import SourceAuthError, SourceUnavailableError
from tracker.shared.http import get_with_retries
from tracker.shared.logging import get_logger

#: GitHub's answer when the token itself is wrong or expired.
_BAD_TOKEN_STATUS: Final[int] = 401

#: GitHub's answers when the token is valid but cannot see the workflow.
_NOT_VISIBLE_STATUSES: Final[frozenset[int]] = frozenset({403, 404})

_log = get_logger(__name__)


class GitHubApi:
    """Reads what a token can see on GitHub."""

    def __init__(self, http: httpx.AsyncClient | None = None) -> None:
        """Bind the client to a connection pool, or let it open one per call.

        Args:
            http: An open pool; a short-lived one is used when omitted.
        """
        self._http = http

    async def workflow_state(self, repository: str, token: SecretStr) -> str:
        """Read the Threadline workflow's state with a token.

        Args:
            repository: The copy, as ``owner/name``.
            token: The fine-grained token to try.

        Returns:
            GitHub's state for the workflow, such as ``active``.

        Raises:
            SourceAuthError: If the token is wrong or cannot see the workflow.
            SourceUnavailableError: If GitHub could not be reached or answered oddly.
        """
        if self._http is not None:
            return await self._read(self._http, repository, token)
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as http:
            return await self._read(http, repository, token)

    @staticmethod
    async def _read(http: httpx.AsyncClient, repository: str, token: SecretStr) -> str:
        """Send the read and interpret GitHub's answer."""
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token.get_secret_value()}",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        }
        url = GITHUB_API_URL + WORKFLOW_API_PATH.format(repository=repository)
        try:
            response = await get_with_retries(http, url, headers=headers, source="github")
        except httpx.HTTPError as error:
            _log.error("github_unreachable", error_type=type(error).__name__)
            message = "GitHub could not be reached"
            raise SourceUnavailableError(message) from error
        return _state(response, repository)


def _state(response: httpx.Response, repository: str) -> str:
    """Read the workflow's state, or raise the typed error the status means."""
    status = response.status_code
    if status == _BAD_TOKEN_STATUS:
        message = "GitHub did not accept the token - it is incomplete, wrong or expired"
        raise SourceAuthError(message)
    if status in _NOT_VISIBLE_STATUSES:
        _log.warning("github_workflow_not_visible", status=status)
        message = (
            f"the token cannot see the workflow in {repository} - give it access to that "
            "repository with 'Actions: Read and write'"
        )
        raise SourceAuthError(message)
    if not response.is_success:
        message = f"GitHub answered status {status}"
        raise SourceUnavailableError(message)
    try:
        payload: Any = response.json()
    except ValueError as error:
        raise _unreadable() from error
    state = payload.get("state") if isinstance(payload, dict) else None
    if not isinstance(state, str):
        raise _unreadable()
    return state


def _unreadable() -> SourceUnavailableError:
    """Build the error for an answer that is not the expected JSON."""
    return SourceUnavailableError("GitHub answered with something unexpected")
