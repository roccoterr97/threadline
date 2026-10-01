"""Signing in to Microsoft, and renewing the key without the owner.

Personal Microsoft accounts are signed in with the one-time-code flow: the tool
shows a short code, the owner types it on a Microsoft page, and the tool
receives a long-lived key. That key is stored encrypted in the database, because
Microsoft returns a **new** one on every renewal and a value in ``.env`` would
be stale within a day.

The ordering rule this module exists to guarantee:

    **The new long-lived key is saved before the renewed access key is handed
    out.** A crash at any point after a renewal therefore still leaves a working
    key behind. Saving afterwards would burn the old key and leave Threadline
    locked out until the owner signed in again by hand.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import TracebackType
from typing import Any, Final, Self

import httpx

from tracker.infrastructure.secret_store import MICROSOFT_REFRESH_TOKEN, SecretStore
from tracker.shared.clock import Clock
from tracker.shared.config import Settings
from tracker.shared.constants.collection import (
    DEVICE_CODE_MAX_POLLS,
    DEVICE_CODE_POLL_SECONDS,
    HTTP_TIMEOUT_SECONDS,
    MICROSOFT_CLIENT_ID,
    MICROSOFT_DEFAULT_TENANT,
    MICROSOFT_LOGIN_HOST,
    MICROSOFT_SCOPE,
)
from tracker.shared.errors import SourceAuthError, SourceUnavailableError
from tracker.shared.http import request_with_retries
from tracker.shared.logging import get_logger


def login_urls(tenant: str) -> tuple[str, str]:
    """Build the one-time-code and key addresses for one tenant.

    Args:
        tenant: ``consumers``, ``common``, ``organizations`` or a directory id.

    Returns:
        The address that hands out one-time codes, and the one that hands out keys.
    """
    base = f"{MICROSOFT_LOGIN_HOST}/{tenant}/oauth2/v2.0"
    return f"{base}/devicecode", f"{base}/token"


#: Where the one-time code is requested, and where keys are exchanged and
#: renewed, for the default tenant.
DEVICE_CODE_URL, TOKEN_URL = login_urls(MICROSOFT_DEFAULT_TENANT)

#: Grant Microsoft expects while the owner is typing the code.
DEVICE_CODE_GRANT: Final[str] = "urn:ietf:params:oauth:grant-type:device_code"

#: Errors Microsoft answers with while the owner has not finished yet.
PENDING_ERRORS: Final[frozenset[str]] = frozenset({"authorization_pending", "slow_down"})

#: Seconds subtracted from an access key's lifetime, so a key never expires
#: between the moment it is checked and the moment it is used.
EXPIRY_MARGIN_SECONDS: Final[int] = 120

_log = get_logger(__name__)

#: Signature of the sleep function the polling loop uses; injected by tests.
Sleeper = Callable[[float], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class DeviceCodePrompt:
    """What the owner must do to finish signing in.

    Attributes:
        user_code: The short code he types.
        verification_url: The page he types it on.
        device_code: The handle the tool polls with. Not shown to anyone.
        interval_seconds: How long Microsoft asks the tool to wait between polls.
    """

    user_code: str
    verification_url: str
    device_code: str
    interval_seconds: float


@dataclass(frozen=True, slots=True)
class _AccessKey:
    """An access key held in memory for the rest of this process."""

    value: str
    expires_at: datetime


class MicrosoftAuthenticator:
    """Signs in once, then renews the key on its own before every mailbox call."""

    def __init__(
        self,
        secret_store: SecretStore,
        clock: Clock,
        *,
        client_id: str = MICROSOFT_CLIENT_ID,
        tenant: str = MICROSOFT_DEFAULT_TENANT,
    ) -> None:
        """Bind the authenticator to the encrypted store and a clock.

        Args:
            secret_store: Where the long-lived key lives, encrypted.
            clock: Supplies the moment an access key stops being usable.
            client_id: The registered application the sign-in is made through.
            tenant: Which Microsoft accounts may sign in.
        """
        self._secret_store = secret_store
        self._clock = clock
        self._client_id = client_id
        self._device_code_url, self._token_url = login_urls(tenant)
        self._http: httpx.AsyncClient | None = None
        self._access_key: _AccessKey | None = None
        self._renewal = asyncio.Lock()

    @classmethod
    def for_settings(cls, secret_store: SecretStore, clock: Clock, settings: Settings) -> Self:
        """Build an authenticator for the application and tenant in the settings.

        Args:
            secret_store: Where the long-lived key lives, encrypted.
            clock: Supplies the moment an access key stops being usable.
            settings: The process configuration.

        Returns:
            The authenticator.
        """
        return cls(
            secret_store,
            clock,
            client_id=settings.microsoft_client_id,
            tenant=settings.microsoft_tenant,
        )

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

    async def request_device_code(self) -> DeviceCodePrompt:
        """Ask Microsoft for a one-time code to show the owner.

        Returns:
            What the owner must type, and where.

        Raises:
            SourceUnavailableError: If Microsoft could not be reached or
                answered something unusable.
        """
        payload = await self._post(
            self._device_code_url,
            {"client_id": self._client_id, "scope": MICROSOFT_SCOPE},
        )
        try:
            return DeviceCodePrompt(
                user_code=str(payload["user_code"]),
                verification_url=str(payload["verification_uri"]),
                device_code=str(payload["device_code"]),
                interval_seconds=float(payload.get("interval", DEVICE_CODE_POLL_SECONDS)),
            )
        except (KeyError, TypeError, ValueError) as error:
            message = "Microsoft did not return a usable sign-in code"
            raise SourceUnavailableError(message) from error

    async def wait_for_sign_in(
        self,
        prompt: DeviceCodePrompt,
        *,
        sleep: Sleeper = asyncio.sleep,
        max_polls: int = DEVICE_CODE_MAX_POLLS,
    ) -> None:
        """Poll until the owner has typed the code, then store the key.

        Args:
            prompt: What :meth:`request_device_code` returned.
            sleep: Injected so tests do not wait.
            max_polls: How many times to ask before giving up.

        Raises:
            SourceAuthError: If Microsoft refused the sign-in or the owner did
                not finish in time.
            SourceUnavailableError: If Microsoft could not be reached.
        """
        form = {
            "grant_type": DEVICE_CODE_GRANT,
            "client_id": self._client_id,
            "device_code": prompt.device_code,
        }
        for _ in range(max_polls):
            payload = await self._post(self._token_url, form, allow_pending=True)
            if payload.get("error") in PENDING_ERRORS:
                await sleep(prompt.interval_seconds)
                continue
            self._store_keys(payload)
            _log.info("microsoft_sign_in_completed")
            return
        message = "Microsoft sign-in was not completed in time — run it again"
        raise SourceAuthError(message)

    async def access_token(self) -> str:
        """Return a usable access key, renewing it first when needed.

        The renewed long-lived key is written to the encrypted store *before*
        this method returns, so a failure in the caller cannot lose it.

        Several calls can ask at the same moment and all find the key expired.
        Only one renews: Microsoft hands out a new long-lived key on every
        renewal, and with two under way the one saved last need not be the one
        issued last.

        Returns:
            The access key for the mailbox calls that follow.

        Raises:
            SourceAuthError: If nobody has signed in yet, or Microsoft refused
                to renew.
            SourceUnavailableError: If Microsoft could not be reached.
        """
        async with self._renewal:
            cached = self._access_key
            if cached is not None and cached.expires_at > self._clock.now():
                return cached.value
            return await self._renew()

    async def _renew(self) -> str:
        """Exchange the long-lived key for a new pair and store it.

        Returns:
            The new access key.

        Raises:
            SourceAuthError: If nobody has signed in yet, or Microsoft refused
                to renew.
            SourceUnavailableError: If Microsoft could not be reached.
        """
        refresh_token = self._secret_store.get_secret(MICROSOFT_REFRESH_TOKEN)
        if not refresh_token:
            message = "Microsoft sign-in missing — run 'tracker microsoft login' once"
            raise SourceAuthError(message)
        payload = await self._post(
            self._token_url,
            {
                "grant_type": "refresh_token",
                "client_id": self._client_id,
                "scope": MICROSOFT_SCOPE,
                "refresh_token": refresh_token,
            },
        )
        return self._store_keys(payload)

    def _store_keys(self, payload: dict[str, Any]) -> str:
        """Save the rotated long-lived key, then remember the access key.

        Args:
            payload: What the token endpoint answered.

        Returns:
            The access key.

        Raises:
            SourceAuthError: If the answer holds no access key.
        """
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            message = "Microsoft refused to renew the mailbox key — sign in again"
            raise SourceAuthError(message)
        refresh_token = payload.get("refresh_token")
        if isinstance(refresh_token, str) and refresh_token:
            self._secret_store.put_secret(MICROSOFT_REFRESH_TOKEN, refresh_token)
            _log.info("microsoft_key_rotated")
        self._access_key = _AccessKey(
            value=access_token,
            expires_at=self._clock.now() + timedelta(seconds=_lifetime_seconds(payload)),
        )
        return access_token

    async def _post(
        self,
        url: str,
        form: dict[str, str],
        *,
        allow_pending: bool = False,
    ) -> dict[str, Any]:
        """Send one form-encoded request and read its JSON answer.

        Args:
            url: The endpoint to call.
            form: The form fields to send.
            allow_pending: Whether a "still waiting" answer is expected.

        Returns:
            The decoded payload.

        Raises:
            SourceAuthError: If Microsoft refused the request.
            SourceUnavailableError: If Microsoft could not be reached or
                answered something that is not JSON.
        """
        if self._http is None:
            message = "Microsoft client used outside its context manager"
            raise SourceUnavailableError(message)
        try:
            response = await request_with_retries(
                self._http,
                "POST",
                url,
                data=form,
                source="microsoft sign-in",
                retry_after_send=False,
            )
        except httpx.HTTPError as error:
            _log.error("microsoft_unreachable", error_type=type(error).__name__)
            message = "Microsoft could not be reached"
            raise SourceUnavailableError(message) from error
        payload = _decode(response)
        if response.is_success:
            return payload
        error_code = str(payload.get("error", "")) or "unknown"
        if allow_pending and error_code in PENDING_ERRORS:
            return payload
        _log.error("microsoft_request_refused", status=response.status_code, reason=error_code)
        if response.status_code in {httpx.codes.BAD_REQUEST, httpx.codes.UNAUTHORIZED}:
            message = f"Microsoft refused the sign-in ({error_code}) — sign in again"
            raise SourceAuthError(message)
        message = f"Microsoft answered status {response.status_code}"
        raise SourceUnavailableError(message)


def _decode(response: httpx.Response) -> dict[str, Any]:
    """Read a JSON object out of a response.

    Args:
        response: The response to read.

    Returns:
        The decoded object.

    Raises:
        SourceUnavailableError: If the body is not a JSON object.
    """
    try:
        payload: Any = response.json()
    except ValueError as error:
        message = "Microsoft answered with something that is not JSON"
        raise SourceUnavailableError(message) from error
    if not isinstance(payload, dict):
        message = "Microsoft answered with an unexpected payload shape"
        raise SourceUnavailableError(message)
    return payload


def _lifetime_seconds(payload: dict[str, Any]) -> int:
    """Read how long an access key lasts, leaving a safety margin.

    Args:
        payload: What the token endpoint answered.

    Returns:
        Seconds the key may be reused for, never negative.
    """
    try:
        lifetime = int(payload.get("expires_in", 0))
    except (TypeError, ValueError):
        return 0
    return max(lifetime - EXPIRY_MARGIN_SECONDS, 0)
