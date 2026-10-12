"""Making the Telethon client, and turning its errors into Threadline's.

Telethon's own error messages are never shown or chained: they can name the
request that failed, and a failure the owner reads must say what to do, not
what the library saw. Only the error's type is logged.
"""

from __future__ import annotations

import inspect
import struct
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Final

from telethon import TelegramClient, errors
from telethon.sessions import StringSession

from tracker.domain.telegram import TelegramApp
from tracker.shared.constants.telegram import (
    TELEGRAM_APP_VERSION,
    TELEGRAM_DEVICE_MODEL,
    TELEGRAM_FLOOD_WAIT_MAX_SECONDS,
    TELEGRAM_RETRIES,
    TELEGRAM_SYSTEM_VERSION,
    TELEGRAM_TIMEOUT_SECONDS,
)
from tracker.shared.errors import (
    ConfigurationError,
    SourceAuthError,
    SourceUnavailableError,
    TelegramFloodWaitError,
)
from tracker.shared.logging import get_logger

#: What the owner is told when Telegram no longer accepts the saved login.
LOGIN_ENDED: Final[str] = (
    "Telegram no longer accepts Threadline's login - run 'uv run tracker setup telegram' "
    "on your computer to log in again"
)

_UNREADABLE_SESSION: Final[str] = (
    "TELEGRAM_SESSION is not a Telegram login Threadline made - run "
    "'uv run tracker setup telegram' on your computer to log in again"
)

_log = get_logger(__name__)


def build_client(app: TelegramApp, session: str) -> TelegramClient:
    """Make a client for the owner's application, from a saved login or none.

    Updates are switched off, so the client only answers the requests it is
    asked to make. A pause Telegram asks for of up to
    ``TELEGRAM_FLOOD_WAIT_MAX_SECONDS`` is waited out by the client itself; a
    longer one raises.

    Args:
        app: The owner's application.
        session: The saved login, or an empty string to start a new one.

    Returns:
        The client, not connected yet.

    Raises:
        ConfigurationError: If the saved login is not one Telethon can read.
    """
    try:
        string_session = StringSession(session)
    except (ValueError, struct.error):
        raise ConfigurationError(_UNREADABLE_SESSION) from None
    return TelegramClient(
        string_session,
        app.api_id,
        app.api_hash.get_secret_value(),
        timeout=TELEGRAM_TIMEOUT_SECONDS,
        request_retries=TELEGRAM_RETRIES,
        connection_retries=TELEGRAM_RETRIES,
        flood_sleep_threshold=TELEGRAM_FLOOD_WAIT_MAX_SECONDS,
        device_model=TELEGRAM_DEVICE_MODEL,
        system_version=TELEGRAM_SYSTEM_VERSION,
        app_version=TELEGRAM_APP_VERSION,
        receive_updates=False,
    )


async def disconnect(client: TelegramClient) -> None:
    """Disconnect a client; inside a running event loop Telethon hands back what to wait for."""
    pending = client.disconnect()
    if inspect.isawaitable(pending):
        await pending


@contextmanager
def reading_errors() -> Iterator[None]:
    """Turn what Telegram raises while reading into Threadline's errors.

    Raises:
        TelegramFloodWaitError: If Telegram asked for a longer pause than is waited out.
        SourceAuthError: If Telegram ended the saved login, or it is used elsewhere.
        SourceUnavailableError: If Telegram could not be reached or refused a request.
    """
    try:
        yield
    except errors.FloodError as error:
        seconds = getattr(error, "seconds", None)
        _log.warning("telegram_flood_wait", seconds=seconds)
        message = f"Telegram asked Threadline to pause for {seconds} seconds before reading more"
        raise TelegramFloodWaitError(message) from None
    except (errors.UnauthorizedError, errors.AuthKeyError) as error:
        _log.error("telegram_login_ended", error_type=type(error).__name__)
        raise SourceAuthError(LOGIN_ENDED) from None
    except errors.RPCError as error:
        _log.error("telegram_request_refused", error_type=type(error).__name__)
        message = "Telegram refused a request"
        raise SourceUnavailableError(message) from None
    except OSError as error:
        _log.error("telegram_unreachable", error_type=type(error).__name__)
        message = "Telegram could not be reached"
        raise SourceUnavailableError(message) from None
