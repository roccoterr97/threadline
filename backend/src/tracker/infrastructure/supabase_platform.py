"""Supabase over plain HTTPS: the Management API and the auth server's settings.

Two things the service-key client cannot do:

* **Apply the database structure.** Supabase's Management API runs a migration
  file when given a personal access token
  (``POST /v1/projects/{ref}/database/migrations``) and lists the ones it has
  applied (``GET`` on the same path). The token is held in memory for one set-up
  run and never written anywhere.
* **Switch on "Refresh now".** The same token deploys the ``refresh-now`` Edge
  Function from the repository's files
  (``POST /v1/projects/{ref}/functions/deploy?slug=...``, a multipart upload)
  and saves its settings (``POST /v1/projects/{ref}/secrets``).
* **Read whether sign-ups are open.** The auth server publishes its public
  settings at ``/auth/v1/settings``; the publishable key is enough to read them.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from types import TracebackType
from typing import Any, Final, Self

import httpx
from pydantic import SecretStr

from tracker.shared.constants.collection import HTTP_TIMEOUT_SECONDS
from tracker.shared.constants.setup import (
    SERVICE_ERROR_DETAIL_LENGTH,
    SUPABASE_MANAGEMENT_API_URL,
)
from tracker.shared.errors import (
    SourceAuthError,
    SourceRequestRejectedError,
    SourceUnavailableError,
)
from tracker.shared.http import get_with_retries, request_with_retries
from tracker.shared.logging import get_logger

#: Statuses meaning "this key or token is not accepted".
REFUSED_STATUSES: Final[frozenset[int]] = frozenset({401, 403})

#: Fields of an error answer that hold Supabase's own explanation, in order of preference.
ERROR_MESSAGE_FIELDS: Final[tuple[str, ...]] = ("message", "msg", "error_description", "error")

#: Media type every Edge Function file is uploaded with.
FUNCTION_FILE_TYPE: Final[str] = "application/typescript"

#: Multipart field names of the deploy endpoint.
_METADATA_FIELD: Final[str] = "metadata"
_FILE_FIELD: Final[str] = "file"

#: Path of the auth server's public settings, below the project address.
AUTH_SETTINGS_PATH: Final[str] = "/auth/v1/settings"

_log = get_logger(__name__)


class SupabasePlatform:
    """Talks to Supabase's Management API and to a project's auth server."""

    def __init__(self, http: httpx.AsyncClient | None = None) -> None:
        """Bind the client to a connection pool, or open its own.

        Args:
            http: An open pool; one is created when omitted.
        """
        self._http = http
        self._owns_pool = http is None

    async def __aenter__(self) -> Self:
        """Open the connection pool when none was given."""
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the pool this client opened."""
        if self._owns_pool and self._http is not None:
            await self._http.aclose()
            self._http = None

    async def signups_disabled(self, project_url: str, publishable_key: SecretStr) -> bool:
        """Read whether strangers are prevented from creating a login.

        The auth server publishes its public settings; the publishable key is
        enough to read them, so this also proves the address and the key match.

        Args:
            project_url: ``https://<project-ref>.supabase.co``.
            publishable_key: The public key.

        Returns:
            ``True`` when sign-ups are switched off.

        Raises:
            SourceAuthError: If Supabase refused the key.
            SourceUnavailableError: If the project could not be reached.
        """
        response = await self._send(
            "GET",
            f"{project_url.rstrip('/')}{AUTH_SETTINGS_PATH}",
            {"apikey": publishable_key.get_secret_value()},
            what="the publishable key",
        )
        return _json_object(response).get("disable_signup") is True

    async def applied_migrations(self, project_ref: str, token: SecretStr) -> frozenset[str]:
        """List the names of the migrations Supabase has recorded as applied.

        Args:
            project_ref: The project's identifier.
            token: A personal access token.

        Returns:
            The recorded names.

        Raises:
            SourceAuthError: If Supabase refused the token.
            SourceUnavailableError: If Supabase could not be reached.
        """
        response = await self._send(
            "GET", _migrations_url(project_ref), _bearer(token), what="the access token"
        )
        try:
            items: Any = response.json()
        except ValueError as error:
            raise _unreadable() from error
        if not isinstance(items, list):
            raise _unreadable()
        return frozenset(
            str(item["name"]) for item in items if isinstance(item, dict) and "name" in item
        )

    async def apply_migration(
        self, project_ref: str, token: SecretStr, name: str, sql: str
    ) -> None:
        """Run one migration file on the project.

        Args:
            project_ref: The project's identifier.
            token: A personal access token.
            name: The file's name without its extension.
            sql: The file's content.

        Raises:
            SourceAuthError: If Supabase refused the token.
            SourceRequestRejectedError: If Supabase refused the file; its
                message carries Supabase's own reason.
            SourceUnavailableError: If the file could not be applied.
        """
        await self._send(
            "POST",
            _migrations_url(project_ref),
            _bearer(token),
            what="the access token",
            json_body={"query": sql, "name": name},
        )
        _log.info("migration_applied", name=name)

    async def set_secrets(
        self, project_ref: str, token: SecretStr, secrets: Mapping[str, SecretStr]
    ) -> None:
        """Save Edge Function settings, replacing any with the same name.

        Args:
            project_ref: The project's identifier.
            token: A personal access token allowed to write function secrets.
            secrets: The settings by name; values are never logged.

        Raises:
            SourceAuthError: If Supabase refused the token.
            SourceUnavailableError: If the settings could not be saved.
        """
        body = [
            {"name": name, "value": value.get_secret_value()} for name, value in secrets.items()
        ]
        await self._send(
            "POST",
            f"{_project_api(project_ref)}/secrets",
            _bearer(token),
            what="the access token for the function's settings",
            json_body=body,
        )
        _log.info("function_secrets_saved", names=sorted(secrets))

    async def deploy_function(
        self,
        project_ref: str,
        token: SecretStr,
        slug: str,
        files: Mapping[str, bytes],
        *,
        verify_jwt: bool,
    ) -> None:
        """Deploy an Edge Function from its source files, replacing an older version.

        Args:
            project_ref: The project's identifier.
            token: A personal access token allowed to deploy functions.
            slug: The function's name in the project.
            files: Its files by relative path; the first one is the entry point.
            verify_jwt: Whether Supabase itself refuses callers without a valid JWT.

        Raises:
            SourceAuthError: If Supabase refused the token.
            SourceUnavailableError: If the function could not be deployed.
        """
        metadata = {"name": slug, "entrypoint_path": next(iter(files)), "verify_jwt": verify_jwt}
        await self._send(
            "POST",
            f"{_project_api(project_ref)}/functions/deploy?slug={slug}",
            _bearer(token),
            what="the access token for deploying the function",
            form={_METADATA_FIELD: json.dumps(metadata)},
            files=[
                (_FILE_FIELD, (path, content, FUNCTION_FILE_TYPE))
                for path, content in files.items()
            ],
        )
        _log.info("function_deployed", slug=slug)

    async def _send(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        *,
        what: str,
        json_body: object | None = None,
        form: dict[str, str] | None = None,
        files: list[tuple[str, tuple[str, bytes, str]]] | None = None,
    ) -> httpx.Response:
        """Send one request and turn every failure into a typed error."""
        if self._http is None:
            message = "Supabase client used outside its context manager"
            raise SourceUnavailableError(message)
        try:
            if method == "GET":
                response = await get_with_retries(
                    self._http, url, headers=headers, source="supabase"
                )
            else:
                response = await request_with_retries(
                    self._http,
                    method,
                    url,
                    headers=headers,
                    json_body=json_body,
                    data=form,
                    files=files,
                    source="supabase",
                    retry_after_send=False,
                )
        except httpx.HTTPError as error:
            _log.error("supabase_unreachable", error_type=type(error).__name__)
            message = "Supabase could not be reached"
            raise SourceUnavailableError(message) from error
        return _checked(response, what)


def _checked(response: httpx.Response, what: str) -> httpx.Response:
    """Return a successful response, or raise the typed error its status means.

    Supabase's own reason is kept in the error and the log, so a refusal can be
    understood later. It comes from the answer's body only: request headers,
    which hold the token, are never read here.
    """
    if response.is_success:
        return response
    status = response.status_code
    detail = _error_detail(response)
    _log.error("supabase_request_refused", status=status, detail=detail)
    if status in REFUSED_STATUSES:
        message = f"Supabase did not accept {what}"
        raise SourceAuthError(message)
    reason = f"status {status}: {detail}" if detail else f"status {status}"
    if status < httpx.codes.INTERNAL_SERVER_ERROR:
        message = f"Supabase refused it ({reason})"
        raise SourceRequestRejectedError(message)
    message = f"Supabase answered {reason}"
    raise SourceUnavailableError(message)


def _error_detail(response: httpx.Response) -> str:
    """Read Supabase's explanation of a refusal as one short line, or ``""``."""
    try:
        payload: Any = response.json()
    except ValueError:
        payload = response.text
    if isinstance(payload, dict):
        payload = next(
            (payload[name] for name in ERROR_MESSAGE_FIELDS if isinstance(payload.get(name), str)),
            "",
        )
    if not isinstance(payload, str):
        return ""
    return " ".join(payload.split())[:SERVICE_ERROR_DETAIL_LENGTH]


def _json_object(response: httpx.Response) -> dict[str, Any]:
    """Read a JSON object out of a response, or raise a typed error."""
    try:
        payload: Any = response.json()
    except ValueError as error:
        raise _unreadable() from error
    if not isinstance(payload, dict):
        raise _unreadable()
    return payload


def _unreadable() -> SourceUnavailableError:
    """Build the error for an answer that is not the expected JSON."""
    return SourceUnavailableError("Supabase answered with something unexpected")


def _project_api(project_ref: str) -> str:
    """Address of a project in the Management API."""
    return f"{SUPABASE_MANAGEMENT_API_URL}/projects/{project_ref}"


def _migrations_url(project_ref: str) -> str:
    """Address of a project's migration list."""
    return f"{_project_api(project_ref)}/database/migrations"


def _bearer(token: SecretStr) -> dict[str, str]:
    """Authorisation header for a personal access token."""
    return {"Authorization": f"Bearer {token.get_secret_value()}"}
