"""Supabase over plain HTTPS: the Management API and the auth server's settings.

What the service-key client cannot do, all with one personal access token that
is held in memory for one set-up run and never written anywhere:

* **Create the project and read its keys.** The token's organizations
  (``GET /v1/organizations``) and projects (``GET /v1/projects``) are listed, a
  project is created (``POST /v1/projects``) and watched until it is up
  (``GET /v1/projects/{ref}``), and its API keys are read revealed
  (``GET /v1/projects/{ref}/api-keys?reveal=true``) or created
  (``POST`` on the same path).
* **Change the auth settings.** ``PATCH /v1/projects/{ref}/config/auth`` takes
  ``disable_signup``, ``site_url`` and ``uri_allow_list`` (one comma-separated
  string); only the fields the caller set are sent.
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

from tracker.domain.supabase import (
    ApiKey,
    ApiKeyKind,
    AuthSettings,
    NewProject,
    Organization,
    SupabaseProject,
)
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

#: Query that makes the API keys endpoint return the keys themselves.
REVEAL_KEYS: Final[dict[str, str]] = {"reveal": "true"}

#: How a new project's region is asked for: Supabase picks within a group.
SMART_REGION_TYPE: Final[str] = "smartGroup"

#: What Supabase shows beside a key the set-up created.
API_KEY_DESCRIPTION: Final[str] = "Created by Threadline's set-up"

#: What a refusal of a plain read with the token is called.
_TOKEN: Final[str] = "the access token"

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

    async def organizations(self, token: SecretStr) -> tuple[Organization, ...]:
        """List the organizations the token's owner belongs to.

        A read that changes nothing, so it also proves a freshly typed token.

        Args:
            token: A personal access token.

        Returns:
            The organizations, in Supabase's order.

        Raises:
            SourceAuthError: If Supabase refused the token.
            SourceUnavailableError: If Supabase could not be reached.
        """
        response = await self._send(
            "GET", f"{SUPABASE_MANAGEMENT_API_URL}/organizations", _bearer(token), what=_TOKEN
        )
        return tuple(
            Organization(slug=str(item["slug"]), name=str(item.get("name", item["slug"])))
            for item in _json_objects(response)
            if "slug" in item
        )

    async def projects(self, token: SecretStr) -> tuple[SupabaseProject, ...]:
        """List every project the token can see.

        Args:
            token: A personal access token.

        Returns:
            The projects, with their current status.

        Raises:
            SourceAuthError: If Supabase refused the token.
            SourceUnavailableError: If Supabase could not be reached.
        """
        response = await self._send(
            "GET", f"{SUPABASE_MANAGEMENT_API_URL}/projects", _bearer(token), what=_TOKEN
        )
        return tuple(_project(item) for item in _json_objects(response) if "ref" in item)

    async def create_project(self, token: SecretStr, request: NewProject) -> SupabaseProject:
        """Create a project; it comes back still being set up.

        Args:
            token: A personal access token allowed to create projects.
            request: The organization, name, region group and database password.

        Returns:
            The new project, usually with status ``COMING_UP``.

        Raises:
            SourceAuthError: If Supabase refused the token.
            SourceRequestRejectedError: If Supabase refused the request; its
                message carries Supabase's own reason.
            SourceUnavailableError: If the project could not be created.
        """
        body = {
            "name": request.name,
            "organization_slug": request.organization_slug,
            "db_pass": request.database_password.get_secret_value(),
            "region_selection": {"type": SMART_REGION_TYPE, "code": request.region.value},
        }
        response = await self._send(
            "POST",
            f"{SUPABASE_MANAGEMENT_API_URL}/projects",
            _bearer(token),
            what="the access token for creating a project",
            json_body=body,
            once=True,
        )
        project = _project(_json_object(response))
        _log.info("project_created", ref=project.ref, region=request.region.value)
        return project

    async def project(self, token: SecretStr, project_ref: str) -> SupabaseProject:
        """Read one project, with its current status.

        Args:
            token: A personal access token.
            project_ref: The project's identifier.

        Returns:
            The project.

        Raises:
            SourceAuthError: If Supabase refused the token.
            SourceUnavailableError: If Supabase could not be reached.
        """
        response = await self._send("GET", _project_api(project_ref), _bearer(token), what=_TOKEN)
        return _project(_json_object(response))

    async def api_keys(self, project_ref: str, token: SecretStr) -> tuple[ApiKey, ...]:
        """List a project's publishable and secret API keys, revealed.

        Legacy JWT keys are left out.

        Args:
            project_ref: The project's identifier.
            token: A personal access token allowed to read keys and their secrets.

        Returns:
            The keys; a value is ``None`` when Supabase did not reveal it.

        Raises:
            SourceAuthError: If Supabase refused the token.
            SourceUnavailableError: If Supabase could not be reached.
        """
        response = await self._send(
            "GET",
            _api_keys_url(project_ref),
            _bearer(token),
            what="the access token for reading the API keys",
            params=REVEAL_KEYS,
        )
        return tuple(
            key for key in (_api_key(item) for item in _json_objects(response)) if key is not None
        )

    async def create_api_key(
        self, project_ref: str, token: SecretStr, kind: ApiKeyKind, name: str
    ) -> SecretStr:
        """Create one API key and return it.

        Args:
            project_ref: The project's identifier.
            token: A personal access token allowed to create keys.
            kind: Publishable or secret.
            name: The key's name in the dashboard.

        Returns:
            The key.

        Raises:
            SourceAuthError: If Supabase refused the token.
            SourceUnavailableError: If the key could not be created or came back hidden.
        """
        response = await self._send(
            "POST",
            _api_keys_url(project_ref),
            _bearer(token),
            what="the access token for creating an API key",
            params=REVEAL_KEYS,
            json_body={"type": kind.value, "name": name, "description": API_KEY_DESCRIPTION},
        )
        key = _api_key(_json_object(response))
        if key is None or key.value is None:
            raise _unreadable()
        _log.info("api_key_created", kind=kind.value, name=name)
        return key.value

    async def configure_auth(
        self, project_ref: str, token: SecretStr, settings: AuthSettings
    ) -> None:
        """Change a project's auth settings; only the fields that are set are sent.

        Args:
            project_ref: The project's identifier.
            token: A personal access token allowed to change the auth settings.
            settings: The fields to change; ``None`` leaves a field alone.

        Raises:
            SourceAuthError: If Supabase refused the token.
            SourceRequestRejectedError: If Supabase refused a value.
            SourceUnavailableError: If the settings could not be saved.
        """
        body = _auth_body(settings)
        if not body:
            return
        await self._send(
            "PATCH",
            f"{_project_api(project_ref)}/config/auth",
            _bearer(token),
            what="the access token for the auth settings",
            json_body=body,
        )
        _log.info("auth_configured", fields=sorted(body))

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
        params: dict[str, str] | None = None,
        json_body: object | None = None,
        form: dict[str, str] | None = None,
        files: list[tuple[str, tuple[str, bytes, str]]] | None = None,
        once: bool = False,
    ) -> httpx.Response:
        """Send one request and turn every failure into a typed error.

        ``once`` sends it a single time even when Supabase answers "too many
        requests" or a server error: a project created twice would be worse
        than a clear error.
        """
        if self._http is None:
            message = "Supabase client used outside its context manager"
            raise SourceUnavailableError(message)
        try:
            if method == "GET":
                response = await get_with_retries(
                    self._http, url, params=params, headers=headers, source="supabase"
                )
            else:
                response = await request_with_retries(
                    self._http,
                    method,
                    url,
                    params=params,
                    headers=headers,
                    json_body=json_body,
                    data=form,
                    files=files,
                    source="supabase",
                    retry_after_send=False,
                    attempts=1 if once else None,
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


def _json_objects(response: httpx.Response) -> list[dict[str, Any]]:
    """Read a JSON list of objects out of a response, or raise a typed error."""
    try:
        payload: Any = response.json()
    except ValueError as error:
        raise _unreadable() from error
    if not isinstance(payload, list):
        raise _unreadable()
    return [item for item in payload if isinstance(item, dict)]


def _unreadable() -> SourceUnavailableError:
    """Build the error for an answer that is not the expected JSON."""
    return SourceUnavailableError("Supabase answered with something unexpected")


def _project(item: dict[str, Any]) -> SupabaseProject:
    """Read one project out of the Management API's description of it."""
    try:
        return SupabaseProject(
            ref=str(item["ref"]),
            name=str(item.get("name", "")),
            organization_slug=str(item.get("organization_slug", "")),
            status=str(item.get("status", "")),
        )
    except KeyError as error:
        raise _unreadable() from error


def _api_key(item: dict[str, Any]) -> ApiKey | None:
    """Read one key out of the Management API's description, or ``None`` for a legacy key."""
    kind = item.get("type")
    if kind not in {member.value for member in ApiKeyKind}:
        return None
    value = item.get("api_key")
    return ApiKey(
        kind=ApiKeyKind(kind),
        name=str(item.get("name", "")),
        value=SecretStr(value) if isinstance(value, str) and value else None,
    )


def _auth_body(settings: AuthSettings) -> dict[str, object]:
    """The fields of a PATCH to the auth config; a field left ``None`` is not sent."""
    body: dict[str, object] = {}
    if settings.disable_signup is not None:
        body["disable_signup"] = settings.disable_signup
    if settings.site_url is not None:
        body["site_url"] = settings.site_url
    if settings.redirect_urls is not None:
        body["uri_allow_list"] = ",".join(settings.redirect_urls)
    return body


def _project_api(project_ref: str) -> str:
    """Address of a project in the Management API."""
    return f"{SUPABASE_MANAGEMENT_API_URL}/projects/{project_ref}"


def _api_keys_url(project_ref: str) -> str:
    """Address of a project's API keys."""
    return f"{_project_api(project_ref)}/api-keys"


def _migrations_url(project_ref: str) -> str:
    """Address of a project's migration list."""
    return f"{_project_api(project_ref)}/database/migrations"


def _bearer(token: SecretStr) -> dict[str, str]:
    """Authorisation header for a personal access token."""
    return {"Authorization": f"Bearer {token.get_secret_value()}"}
