"""What every step shares: the conversation, the ``.env`` file, the services."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Final

from pydantic import SecretStr

from tracker.services.setup.ports import (
    ChoiceStore,
    EnvStore,
    SetupGateways,
    SetupIO,
    SupabaseAdminPort,
)
from tracker.shared.errors import SourceAuthError, ValidationFailedError

#: How many times a value may be typed again after a refusal.
MAX_ATTEMPTS: Final[int] = 3


@dataclass(slots=True)
class SetupSession:
    """What is kept in memory for one ``tracker setup`` run and never written anywhere.

    Attributes:
        supabase_token: The Supabase access token, once it has been accepted.
        supabase_token_name: The name Supabase lists the token under, when a
            browser sign-in made it, so the end of the run can say it may go.
        build_dashboard_here: Build the dashboard on this computer with Node.js
            instead of downloading the ready-made one; only asked for with
            ``tracker setup dashboard --build-here``.
    """

    supabase_token: SecretStr | None = None
    supabase_token_name: str | None = None
    build_dashboard_here: bool = False


@dataclass(frozen=True, slots=True)
class SetupContext:
    """Everything a step works with.

    Attributes:
        io: The conversation.
        env: The ``.env`` file.
        gateways: The outside services.
        session: What this run keeps in memory only; a fresh one each run.
    """

    io: SetupIO
    env: EnvStore
    gateways: SetupGateways
    session: SetupSession = field(default_factory=SetupSession)

    def write(self, name: str, value: str) -> bool:
        """Write one setting, asking first before changing a different value.

        Args:
            name: The setting's name.
            value: Its new value. Never shown.

        Returns:
            Whether the file now holds ``value``.
        """
        current = self.env.get(name)
        if current == value:
            return True
        if current is not None and not self.io.confirm(
            f"{name} already has a value. Replace it?", default=False
        ):
            self.io.say(f"Kept the existing {name}.")
            return False
        self.env.set(name, value)
        self.io.say(f"Saved {name} in .env.")
        return True

    def require(self, name: str, step: str) -> str:
        """Read a setting an earlier step wrote.

        Args:
            name: The setting's name.
            step: The step that writes it, for the message.

        Returns:
            The value.

        Raises:
            ValidationFailedError: If it is missing.
        """
        value = self.env.get(name)
        if value is None:
            message = f"{name} is missing - run 'uv run tracker setup {step}' first"
            raise ValidationFailedError(message)
        return value

    def admin(self) -> SupabaseAdminPort:
        """Build the service-key helper from the saved Supabase settings."""
        return self.gateways.admin_for(*self._service_access())

    def choices(self) -> ChoiceStore:
        """Build the category-choice store from the saved Supabase settings."""
        return self.gateways.choices_for(*self._service_access())

    def _service_access(self) -> tuple[str, SecretStr]:
        """Read the project address and the secret key an earlier step saved."""
        url = self.require("SUPABASE_URL", "supabase")
        return url, SecretStr(self.require("SUPABASE_SERVICE_ROLE_KEY", "supabase"))

    def ask_until_valid[T](self, ask: Callable[[], str], clean: Callable[[str], T]) -> T:
        """Ask again, a few times, until the answer passes its check.

        Args:
            ask: Asks the question once.
            clean: Checks and cleans the answer; raises when it is wrong.

        Returns:
            The cleaned answer.

        Raises:
            ValidationFailedError: If every attempt was refused.
        """
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return clean(ask())
            except ValidationFailedError as error:
                if attempt == MAX_ATTEMPTS:
                    raise
                self.io.say(f"  {error.message}. Please try again.")
        message = "no attempt was made"  # pragma: no cover - MAX_ATTEMPTS >= 1
        raise ValidationFailedError(message)  # pragma: no cover

    async def ask_until_accepted[T](
        self, ask: Callable[[], str], accept: Callable[[str], Awaitable[T]]
    ) -> T:
        """Ask again, a few times, until a live check accepts the answer.

        Args:
            ask: Asks the question once.
            accept: Checks the answer live; raises when it is refused.

        Returns:
            What the check returned.

        Raises:
            ValidationFailedError: If the answer was malformed every time.
            SourceAuthError: If the service refused it every time.
        """
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return await accept(ask())
            except (ValidationFailedError, SourceAuthError) as error:
                if attempt == MAX_ATTEMPTS:
                    raise
                self.io.say(f"  {error.message}. Please try again.")
        message = "no attempt was made"  # pragma: no cover - MAX_ATTEMPTS >= 1
        raise ValidationFailedError(message)  # pragma: no cover
