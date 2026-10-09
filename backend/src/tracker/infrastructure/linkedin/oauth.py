"""LinkedIn's sign-in endpoints: the consent page's address, the key exchange, the key check.

Every refusal is turned into a :class:`~tracker.shared.errors.LinkedInSignInError`
with a plain sentence and the kind of problem, so the set-up can say what to do
next. The Client Secret, the one-time code and the key travel in form fields
only, and none of them is ever logged.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Final
from urllib.parse import urlencode

import httpx
from pydantic import SecretStr

from tracker.domain.linkedin_sign_in import LinkedInApp, LinkedInGrant, SignInProblem
from tracker.shared.clock import Clock
from tracker.shared.constants.collection import HTTP_TIMEOUT_SECONDS
from tracker.shared.constants.linkedin_sign_in import (
    ACCESS_TOKEN_URL,
    APP_DETAIL_ERRORS,
    AUTHORIZATION_URL,
    INTROSPECT_URL,
    REDIRECT_URL,
    SCOPE,
)
from tracker.shared.errors import LinkedInSignInError, SourceUnavailableError
from tracker.shared.http import request_with_retries
from tracker.shared.logging import get_logger

#: LinkedIn's answer when the Client ID or Client Secret is wrong.
_UNAUTHORISED_STATUS: Final[int] = 401

#: The lowest status that is LinkedIn's own fault rather than the request's.
_SERVER_ERROR_STATUS: Final[int] = 500

_SOURCE: Final[str] = "linkedin_sign_in"

_log = get_logger(__name__)


def authorization_url(client_id: str, state: str, redirect_url: str = REDIRECT_URL) -> str:
    """Build the address of LinkedIn's consent page for the owner's application.

    Args:
        client_id: The application's Client ID.
        state: The random value LinkedIn sends back with its answer.
        redirect_url: Where LinkedIn sends the answer; must match the Auth tab exactly.

    Returns:
        The address to open in the browser.
    """
    query = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_url,
        "state": state,
        "scope": SCOPE,
    }
    return f"{AUTHORIZATION_URL}?{urlencode(query)}"


class LinkedInOAuthApi:
    """Trades LinkedIn's one-time code for a key, and reads a key's expiry."""

    def __init__(self, clock: Clock, http: httpx.AsyncClient | None = None) -> None:
        """Bind the client to a clock and, optionally, a connection pool.

        Args:
            clock: Turns "valid for so many seconds" into a moment.
            http: An open pool; a short-lived one is used per call when omitted.
        """
        self._clock = clock
        self._http = http

    async def exchange(
        self, app: LinkedInApp, code: str, redirect_url: str = REDIRECT_URL
    ) -> LinkedInGrant:
        """Trade the one-time code for the key.

        A code works once, so a request that may have reached LinkedIn is
        never sent again: a second try would only be refused.

        Args:
            app: The application's Client ID and Secret.
            code: The one-time code LinkedIn sent to this computer.
            redirect_url: The address the code was sent to.

        Returns:
            The key, with when it stops working when LinkedIn said.

        Raises:
            LinkedInSignInError: If LinkedIn refused the code or the application.
            SourceUnavailableError: If LinkedIn could not be reached.
        """
        fields = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_url,
            "client_id": app.client_id,
            "client_secret": app.client_secret.get_secret_value(),
        }
        response = await self._post(ACCESS_TOKEN_URL, fields, retry_after_send=False)
        payload = _json_object(response)
        if response.status_code != httpx.codes.OK:
            raise _exchange_refusal(response.status_code, payload)
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            _log.error("linkedin_exchange_without_key")
            message = "LinkedIn answered without a key. Try again"
            raise LinkedInSignInError(message, SignInProblem.OTHER)
        return LinkedInGrant(SecretStr(token), self._expiry(payload.get("expires_in")))

    async def expiry_of(self, app: LinkedInApp, token: SecretStr) -> datetime | None:
        """Ask LinkedIn when a key stops working.

        Args:
            app: The application the key was made for.
            token: The key.

        Returns:
            The moment it stops working, or ``None`` when LinkedIn does not know
            the key, it belongs to another application, or no date came back.

        Raises:
            LinkedInSignInError: If LinkedIn refused the Client ID or Secret.
            SourceUnavailableError: If LinkedIn could not be reached.
        """
        fields = {
            "client_id": app.client_id,
            "client_secret": app.client_secret.get_secret_value(),
            "token": token.get_secret_value(),
        }
        response = await self._post(INTROSPECT_URL, fields, retry_after_send=True)
        if response.status_code == _UNAUTHORISED_STATUS:
            raise _app_details_refused()
        if response.status_code != httpx.codes.OK:
            _log.warning("linkedin_introspection_refused", status=response.status_code)
            return None
        payload = _json_object(response)
        expires_at = payload.get("expires_at")
        if payload.get("active") is not True or not isinstance(expires_at, int):
            return None
        return datetime.fromtimestamp(expires_at, tz=UTC)

    def _expiry(self, expires_in: object) -> datetime | None:
        """Turn "valid for so many seconds" into the moment it ends."""
        if not isinstance(expires_in, int) or expires_in <= 0:
            return None
        return self._clock.now() + timedelta(seconds=expires_in)

    async def _post(
        self, url: str, fields: dict[str, str], *, retry_after_send: bool
    ) -> httpx.Response:
        """Send one form, on the shared pool or a short-lived one."""
        if self._http is not None:
            return await _send(self._http, url, fields, retry_after_send=retry_after_send)
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as http:
            return await _send(http, url, fields, retry_after_send=retry_after_send)


async def _send(
    http: httpx.AsyncClient, url: str, fields: dict[str, str], *, retry_after_send: bool
) -> httpx.Response:
    """Post one form to LinkedIn, mapping an unreachable LinkedIn to a typed error."""
    try:
        response = await request_with_retries(
            http,
            "POST",
            url,
            data=fields,
            source=_SOURCE,
            retry_after_send=retry_after_send,
        )
    except httpx.HTTPError as error:
        _log.error("linkedin_sign_in_unreachable", error_type=type(error).__name__)
        message = "LinkedIn could not be reached. Check the internet connection and try again"
        raise SourceUnavailableError(message) from error
    if response.status_code >= _SERVER_ERROR_STATUS:
        _log.error("linkedin_sign_in_server_error", status=response.status_code)
        message = f"LinkedIn had a problem of its own (status {response.status_code}). Try again"
        raise SourceUnavailableError(message)
    return response


def _exchange_refusal(status: int, payload: dict[str, Any]) -> LinkedInSignInError:
    """Say in plain words why LinkedIn would not trade the code for a key."""
    error = str(payload.get("error") or "")
    _log.warning("linkedin_exchange_refused", status=status, error=error)
    if status == _UNAUTHORISED_STATUS and error != "invalid_request":
        return _app_details_refused()
    if error in APP_DETAIL_ERRORS:
        message = (
            "LinkedIn did not accept the Client ID, the Client Secret or the address on "
            "the Auth tab, or the answer took more than 30 minutes. Check all three on "
            "the Auth tab"
        )
        return LinkedInSignInError(message, SignInProblem.APP_DETAILS)
    message = "LinkedIn's answer had already been used or had expired. Try again"
    return LinkedInSignInError(message, SignInProblem.OTHER)


def _app_details_refused() -> LinkedInSignInError:
    """The error for a Client ID or Client Secret LinkedIn does not accept."""
    message = (
        "LinkedIn did not accept the Client ID or the Client Secret. Copy both again "
        "from the application's Auth tab"
    )
    return LinkedInSignInError(message, SignInProblem.APP_DETAILS)


def _json_object(response: httpx.Response) -> dict[str, Any]:
    """Read a JSON object from LinkedIn's answer, or an empty one when it is not JSON."""
    try:
        payload: Any = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}
