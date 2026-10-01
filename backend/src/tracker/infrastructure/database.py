"""The single Supabase client.

Python reaches the database over HTTPS with Supabase's query builder, never
with a direct PostgreSQL connection: the scheduled cloud session is only allowed
to make web requests. The client is created once, connection attempts are
bounded and linear, and exhaustion fails fast with one clean error line.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from functools import lru_cache

from pydantic import SecretStr
from supabase import Client, SupabaseException, create_client

from tracker.repositories.app_secrets import AppSecretRepository
from tracker.shared.config import Settings, get_settings
from tracker.shared.constants.retry import CONNECT_ATTEMPTS, CONNECT_DELAY_SECONDS
from tracker.shared.errors import ConfigurationError, DatabaseUnavailableError, TrackerError
from tracker.shared.logging import get_logger

_log = get_logger(__name__)


def create_database_client(settings: Settings) -> Client:
    """Build a Supabase client from the given settings.

    Args:
        settings: The process configuration.

    Returns:
        A client authenticated with the service key, which bypasses the
        row-level security rules the dashboard relies on.

    Raises:
        ConfigurationError: If the address or the key is not usable.
    """
    return connect(settings.supabase_url, settings.supabase_service_role_key)


def connect(url: str, service_key: SecretStr) -> Client:
    """Build a Supabase client from an address and a secret key.

    Args:
        url: ``https://<project-ref>.supabase.co``.
        service_key: The secret key.

    Returns:
        A client that bypasses the row-level security rules.

    Raises:
        ConfigurationError: If the address or the key is not usable.
    """
    try:
        return create_client(url, service_key.get_secret_value())
    except SupabaseException as error:
        message = "SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not usable"
        raise ConfigurationError(message) from error


@lru_cache(maxsize=1)
def get_database_client() -> Client:
    """Return the process-wide Supabase client, creating it on first use.

    Returns:
        The shared client.
    """
    return create_database_client(get_settings())


def reset_database_client_cache() -> None:
    """Forget the cached client so the next call builds a new one."""
    get_database_client.cache_clear()


def probe_database(
    client: Client,
    *,
    attempts: int = CONNECT_ATTEMPTS,
    delay_seconds: float = CONNECT_DELAY_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Check that the database answers, retrying a bounded number of times.

    Args:
        client: The client to test.
        attempts: How many times to try before giving up.
        delay_seconds: How long to wait between two attempts.
        sleep: Injected so tests do not wait.

    Raises:
        DatabaseUnavailableError: If every attempt failed.
    """
    probe = AppSecretRepository(client)
    # This function is the retry loop. Letting the request retry as well would
    # multiply the two and turn a fail-fast check into a long wait.
    probe.request_attempts = 1
    last_error: DatabaseUnavailableError | None = None
    for attempt in range(1, attempts + 1):
        try:
            probe.list(limit=1)
        except DatabaseUnavailableError as error:
            last_error = error
            _log.warning("database_probe_failed", attempt=attempt, attempts=attempts)
            if attempt < attempts:
                sleep(delay_seconds)
            continue
        return
    message = f"database did not answer after {attempts} attempts"
    raise DatabaseUnavailableError(message) from last_error


def ensure_database_or_exit() -> Client:
    """Fail fast at start-up when the database cannot be reached.

    Returns:
        The shared client, once it has answered.

    Raises:
        SystemExit: With status 1 after logging one clean error line.
    """
    try:
        client = get_database_client()
        probe_database(client)
    except TrackerError as error:
        _log.error("database_unreachable", code=error.code, detail=error.message)
        raise SystemExit(1) from error
    return client
