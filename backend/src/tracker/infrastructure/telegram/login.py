"""Logging in to Telegram once, on the owner's computer, during the set-up.

Telegram sends a code to the owner's Telegram app; an account with two-step
verification also needs its password. The password is passed straight to
Telethon, which proves it to Telegram without sending it; it is never kept,
logged or written anywhere. What comes out is the saved login (a Telethon
string session), which the set-up keeps as a secret.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import Final, cast

from pydantic import SecretStr
from telethon import TelegramClient, errors, types
from telethon.sessions import StringSession

from tracker.domain.telegram import TelegramApp, TelegramLogin, TelegramLoginProblem
from tracker.infrastructure.telegram.connection import build_client, disconnect
from tracker.shared.errors import SourceUnavailableError, TelegramLoginError
from tracker.shared.logging import get_logger

#: Telegram's answers to a login, by the problem the set-up tells apart.
_PROBLEMS: Final[tuple[tuple[tuple[type[Exception], ...], TelegramLoginProblem], ...]] = (
    ((errors.ApiIdInvalidError, errors.ApiIdPublishedFloodError), TelegramLoginProblem.APP_REFUSED),
    (
        (
            errors.PhoneNumberInvalidError,
            errors.PhoneNumberBannedError,
            errors.PhoneNumberUnoccupiedError,
        ),
        TelegramLoginProblem.PHONE_REFUSED,
    ),
    ((errors.PhoneCodeInvalidError, errors.PhoneCodeEmptyError), TelegramLoginProblem.CODE_WRONG),
    ((errors.PhoneCodeExpiredError,), TelegramLoginProblem.CODE_EXPIRED),
    ((errors.PasswordHashInvalidError,), TelegramLoginProblem.PASSWORD_WRONG),
    (
        (errors.FloodError, errors.PhoneNumberFloodError, errors.PhonePasswordFloodError),
        TelegramLoginProblem.TOO_MANY_TRIES,
    ),
)

#: What the person is told for each problem.
_MESSAGES: Final[dict[TelegramLoginProblem, str]] = {
    TelegramLoginProblem.APP_REFUSED: "Telegram did not accept the api_id and api_hash",
    TelegramLoginProblem.PHONE_REFUSED: "Telegram did not accept that phone number",
    TelegramLoginProblem.CODE_WRONG: "That is not the code Telegram sent",
    TelegramLoginProblem.CODE_EXPIRED: "That code has expired or was used already",
    TelegramLoginProblem.PASSWORD_WRONG: "That is not your two-step verification password",
    TelegramLoginProblem.TOO_MANY_TRIES: (
        "Telegram asked for a pause after too many tries - wait a few hours, then run "
        "'uv run tracker setup telegram' again"
    ),
}

_log = get_logger(__name__)


class TelethonLogin:
    """One login in progress, on one connected client."""

    def __init__(self, client: TelegramClient) -> None:
        """Bind the login to a connected client with no saved login yet."""
        self._client = client
        self._phone = ""

    async def send_code(self, phone: str) -> None:
        """Ask Telegram to send a login code to the account with this phone number."""
        with _login_errors():
            await self._client.send_code_request(phone)
        self._phone = phone

    async def enter_code(self, code: str) -> bool:
        """Log in with the code; ``True`` when the account also needs its password."""
        with _login_errors():
            try:
                await self._client.sign_in(phone=self._phone, code=code)
            except errors.SessionPasswordNeededError:
                return True
        return False

    async def enter_password(self, password: SecretStr) -> None:
        """Finish the login with the two-step verification password, used once."""
        with _login_errors():
            await self._client.sign_in(password=password.get_secret_value())

    async def finish(self) -> TelegramLogin:
        """Hand back the saved login and the account's name."""
        with _login_errors():
            me = cast("types.User", await self._client.get_me())
        name = " ".join(part for part in (me.first_name, me.last_name) if part)
        session = cast("StringSession", self._client.session).save()
        return TelegramLogin(session=SecretStr(session), account_name=name or str(me.id))


class TelethonLoginGateway:
    """Starts logins with the owner's application, one connection each."""

    def __init__(self, make_client: Callable[[TelegramApp], TelegramClient] | None = None) -> None:
        """Bind the gateway to how a client is made.

        Args:
            make_client: Builds a client with no saved login; replaced in tests.
        """
        self._make_client = make_client or _new_client

    @asynccontextmanager
    async def open(self, app: TelegramApp) -> AsyncIterator[TelethonLogin]:
        """Connect to Telegram for one login, and disconnect afterwards.

        Raises:
            SourceUnavailableError: If Telegram could not be reached.
        """
        client = self._make_client(app)
        try:
            with _login_errors():
                await client.connect()
            yield TelethonLogin(client)
        finally:
            await disconnect(client)


def _new_client(app: TelegramApp) -> TelegramClient:
    """Build a real client with no saved login."""
    return build_client(app, "")


@contextmanager
def _login_errors() -> Iterator[None]:
    """Turn what Telegram answers to a login into errors the step can act on.

    Raises:
        TelegramLoginError: If Telegram refused something the person typed.
        SourceUnavailableError: If Telegram could not be reached or refused otherwise.
    """
    try:
        yield
    except errors.RPCError as error:
        _log.warning("telegram_login_refused", error_type=type(error).__name__)
        problem = next((problem for kinds, problem in _PROBLEMS if isinstance(error, kinds)), None)
        if problem is None:
            message = "Telegram refused the login"
            raise SourceUnavailableError(message) from None
        raise TelegramLoginError(_MESSAGES[problem], problem) from None
    except OSError as error:
        _log.warning("telegram_unreachable", error_type=type(error).__name__)
        message = "Telegram could not be reached"
        raise SourceUnavailableError(message) from None
