"""Netlify's REST API, as ``tracker setup dashboard`` uses it.

Five calls, each with a personal access token the owner pastes and that is
held in memory for one set-up run only: read the token's own account (proves
the token works and changes nothing), create a site, look a saved site up,
deploy a zip of the built dashboard, and read a deploy's state. The token
travels in the ``Authorization`` header only and is never logged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

import httpx
from pydantic import SecretStr

from tracker.shared.constants.collection import HTTP_TIMEOUT_SECONDS
from tracker.shared.constants.dashboard import NETLIFY_API_URL, NETLIFY_USER_AGENT
from tracker.shared.constants.setup import SERVICE_ERROR_DETAIL_LENGTH
from tracker.shared.errors import (
    SiteNameTakenError,
    SourceAuthError,
    SourceRequestRejectedError,
    SourceUnavailableError,
)
from tracker.shared.http import request_with_retries
from tracker.shared.logging import get_logger

#: Statuses meaning "this token is not accepted".
_REFUSED_STATUSES: Final[frozenset[int]] = frozenset({401, 403})

#: Netlify's answer for a site or deploy that does not exist (or is not yours).
_NOT_FOUND_STATUS: Final[int] = 404

#: Netlify's answer when a new site's name is already used by another site.
_NAME_TAKEN_STATUS: Final[int] = 422

_ZIP_TYPE: Final[str] = "application/zip"
_HTTPS_PREFIX: Final[str] = "https://"
_HTTP_PREFIX: Final[str] = "http://"

_log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class NetlifySite:
    """A Netlify site.

    Attributes:
        id: Netlify's identifier for it (the "Project ID"); not a secret.
        name: Its name, the first part of ``<name>.netlify.app``.
        address: Its public https address, with no trailing slash.
    """

    id: str
    name: str
    address: str


@dataclass(frozen=True, slots=True)
class NetlifyDeploy:
    """One deploy of a site.

    Attributes:
        id: Netlify's identifier for it.
        state: Where it is, such as ``uploaded``, ``processing``, ``ready`` or ``error``.
        error: Netlify's explanation when it failed, shortened; ``None`` otherwise.
    """

    id: str
    state: str
    error: str | None


class NetlifyApi:
    """Creates a site and publishes the dashboard on it."""

    def __init__(self, http: httpx.AsyncClient | None = None) -> None:
        """Bind the client to a connection pool, or let it open one per call.

        Args:
            http: An open pool; a short-lived one is used when omitted.
        """
        self._http = http

    async def check_token(self, token: SecretStr) -> None:
        """Read the token's own account, which changes nothing.

        Raises:
            SourceAuthError: If Netlify refused the token.
            SourceUnavailableError: If Netlify could not be reached.
        """
        _checked(await self._exchange("GET", "/user", token))

    async def create_site(self, token: SecretStr, name: str) -> NetlifySite:
        """Create an empty site called ``name`` in the token's own team.

        Raises:
            SiteNameTakenError: If another site already has that name.
            SourceAuthError: If Netlify refused the token.
            SourceUnavailableError: If the site could not be created.
        """
        response = await self._exchange("POST", "/sites", token, json_body={"name": name})
        if response.status_code == _NAME_TAKEN_STATUS:
            _log.info("netlify_site_name_taken", name=name)
            message = f"Netlify already has a site called {name}"
            raise SiteNameTakenError(message)
        site = _site(_json_object(_checked(response)))
        _log.info("netlify_site_created", site_id=site.id, name=site.name)
        return site

    async def find_site(self, token: SecretStr, site_id: str) -> NetlifySite | None:
        """Look a site up by its identifier; ``None`` when it is gone or not the token's.

        Raises:
            SourceAuthError: If Netlify refused the token.
            SourceUnavailableError: If Netlify could not be reached.
        """
        response = await self._exchange("GET", f"/sites/{site_id}", token)
        if response.status_code == _NOT_FOUND_STATUS:
            return None
        return _site(_json_object(_checked(response)))

    async def deploy_zip(self, token: SecretStr, site_id: str, archive: bytes) -> NetlifyDeploy:
        """Publish a zip of the whole site as the site's new production deploy.

        Raises:
            SourceAuthError: If Netlify refused the token.
            SourceUnavailableError: If the archive could not be handed over.
        """
        response = await self._exchange("POST", f"/sites/{site_id}/deploys", token, content=archive)
        deploy = _deploy(_json_object(_checked(response)))
        _log.info("netlify_deploy_started", site_id=site_id, deploy_id=deploy.id)
        return deploy

    async def deploy_state(self, token: SecretStr, deploy_id: str) -> NetlifyDeploy:
        """Read where a deploy is.

        Raises:
            SourceAuthError: If Netlify refused the token.
            SourceUnavailableError: If Netlify could not be reached.
        """
        return _deploy(
            _json_object(_checked(await self._exchange("GET", f"/deploys/{deploy_id}", token)))
        )

    async def _exchange(
        self,
        method: str,
        path: str,
        token: SecretStr,
        *,
        json_body: object | None = None,
        content: bytes | None = None,
    ) -> httpx.Response:
        """Send one request and return Netlify's answer, whatever its status.

        Raises:
            SourceUnavailableError: If Netlify could not be reached at all.
        """
        headers = {
            "Authorization": f"Bearer {token.get_secret_value()}",
            "User-Agent": NETLIFY_USER_AGENT,
        }
        if content is not None:
            headers["Content-Type"] = _ZIP_TYPE
        if self._http is not None:
            return await _request(self._http, method, path, headers, json_body, content)
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as http:
            return await _request(http, method, path, headers, json_body, content)


async def _request(
    http: httpx.AsyncClient,
    method: str,
    path: str,
    headers: dict[str, str],
    json_body: object | None,
    content: bytes | None,
) -> httpx.Response:
    """Send through the shared retry policy; a request that changes something is not resent."""
    try:
        return await request_with_retries(
            http,
            method,
            NETLIFY_API_URL + path,
            headers=headers,
            json_body=json_body,
            content=content,
            source="netlify",
            retry_after_send=method == "GET",
        )
    except httpx.HTTPError as error:
        _log.error("netlify_unreachable", error_type=type(error).__name__)
        message = "Netlify could not be reached"
        raise SourceUnavailableError(message) from error


def _checked(response: httpx.Response) -> httpx.Response:
    """Return a successful answer, or raise the typed error its status means.

    Netlify's own reason comes from the answer's body only; the request's
    headers, which hold the token, are never read here.
    """
    if response.is_success:
        return response
    status = response.status_code
    detail = _error_detail(response)
    _log.error("netlify_request_refused", status=status, detail=detail)
    if status in _REFUSED_STATUSES:
        message = "Netlify did not accept the token - it is incomplete, wrong or expired"
        raise SourceAuthError(message)
    reason = f"status {status}: {detail}" if detail else f"status {status}"
    if status < httpx.codes.INTERNAL_SERVER_ERROR:
        message = f"Netlify refused it ({reason})"
        raise SourceRequestRejectedError(message)
    message = f"Netlify answered {reason}"
    raise SourceUnavailableError(message)


def _error_detail(response: httpx.Response) -> str:
    """Read Netlify's explanation of a refusal as one short line, or ``""``."""
    try:
        payload: Any = response.json()
    except ValueError:
        return ""
    message = payload.get("message") if isinstance(payload, dict) else None
    if not isinstance(message, str):
        return ""
    return _short(message)


def _short(text: str) -> str:
    """One line of a service's text, cut to the length that is logged and shown."""
    return " ".join(text.split())[:SERVICE_ERROR_DETAIL_LENGTH]


def _json_object(response: httpx.Response) -> dict[str, Any]:
    """Read a JSON object out of an answer, or raise a typed error."""
    try:
        payload: Any = response.json()
    except ValueError as error:
        raise _unreadable() from error
    if not isinstance(payload, dict):
        raise _unreadable()
    return payload


def _text(payload: dict[str, Any], field: str) -> str | None:
    """A non-empty text field of an answer, or ``None``."""
    value = payload.get(field)
    return value if isinstance(value, str) and value else None


def _site(payload: dict[str, Any]) -> NetlifySite:
    """Read a site out of Netlify's answer."""
    site_id, name = _text(payload, "id"), _text(payload, "name")
    address = _text(payload, "ssl_url") or _text(payload, "url")
    if site_id is None or name is None or address is None:
        raise _unreadable()
    if address.startswith(_HTTP_PREFIX):
        address = _HTTPS_PREFIX + address.removeprefix(_HTTP_PREFIX)
    return NetlifySite(id=site_id, name=name, address=address.rstrip("/"))


def _deploy(payload: dict[str, Any]) -> NetlifyDeploy:
    """Read a deploy out of Netlify's answer."""
    deploy_id, state = _text(payload, "id"), _text(payload, "state")
    if deploy_id is None or state is None:
        raise _unreadable()
    error = _text(payload, "error_message")
    return NetlifyDeploy(id=deploy_id, state=state, error=None if error is None else _short(error))


def _unreadable() -> SourceUnavailableError:
    """Build the error for an answer that is not the expected JSON."""
    return SourceUnavailableError("Netlify answered with something unexpected")
