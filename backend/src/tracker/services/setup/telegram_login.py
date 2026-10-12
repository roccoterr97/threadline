"""What the Telegram set-up step needs to log in, as small interfaces.

The step asks the person for the phone number, the code and the password
through the set-up's conversation, and hands each to a :class:`TelegramLoginFlow`;
the login itself is the infrastructure's business. So the step is tested with a
fake login and no network.
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Protocol

from pydantic import SecretStr

from tracker.domain.telegram import TelegramApp, TelegramLogin


class TelegramLoginFlow(Protocol):
    """One login in progress, on one connection.

    Each call raises :class:`~tracker.shared.errors.TelegramLoginError` with a
    :class:`~tracker.domain.telegram.TelegramLoginProblem` when Telegram says
    no, so the step can ask again.
    """

    async def send_code(self, phone: str) -> None:
        """Ask Telegram to send a login code to the account with this phone number."""
        ...

    async def enter_code(self, code: str) -> bool:
        """Log in with the code; ``True`` when the account also needs its password."""
        ...

    async def enter_password(self, password: SecretStr) -> None:
        """Finish the login with the two-step verification password, used once."""
        ...

    async def finish(self) -> TelegramLogin:
        """Hand back the saved login and the account's name."""
        ...


class TelegramLoginPort(Protocol):
    """Starts logins with the owner's own application."""

    def open(self, app: TelegramApp) -> AbstractAsyncContextManager[TelegramLoginFlow]:
        """Connect to Telegram for one login, and disconnect afterwards."""
        ...
