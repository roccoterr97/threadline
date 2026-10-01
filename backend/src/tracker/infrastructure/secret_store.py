"""Encrypted storage for values that change between runs.

The mailbox key renews itself on every run, so it cannot live in ``.env``; an
IMAP mailbox's app password is a password, so it does not belong there either.
Both are kept in ``app_secrets``, encrypted with ``TOKEN_ENCRYPTION_KEY`` — a key that is
deliberately *not* in the database, so a copy of the database alone reveals
nothing.
"""

from __future__ import annotations

import binascii

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr

from tracker.domain.models import AppSecret
from tracker.repositories.app_secrets import AppSecretRepository
from tracker.shared.clock import Clock
from tracker.shared.constants.mailbox import IMAP_PASSWORD_SECRET_PREFIX
from tracker.shared.errors import ConfigurationError

#: Name under which the Microsoft Graph refresh key is stored.
MICROSOFT_REFRESH_TOKEN = "microsoft_refresh_token"


def imap_password_name(username: str) -> str:
    """Name under which one IMAP mailbox's app password is stored.

    Args:
        username: The mailbox's sign-in name.

    Returns:
        A name unique to that mailbox, so several can be kept side by side.
    """
    return IMAP_PASSWORD_SECRET_PREFIX + username.strip().lower()


class SecretStore:
    """Reads and writes encrypted values in ``app_secrets``."""

    def __init__(
        self,
        repository: AppSecretRepository,
        encryption_key: SecretStr,
        clock: Clock,
    ) -> None:
        """Bind the store to its table, its key and a clock.

        Args:
            repository: Data access for ``app_secrets``.
            encryption_key: The Fernet key from ``TOKEN_ENCRYPTION_KEY``.
            clock: Supplies the rotation timestamp.

        Raises:
            ConfigurationError: If the key is not a valid Fernet key.
        """
        self._repository = repository
        self._clock = clock
        self._cipher = _build_cipher(encryption_key)

    def get_secret(self, name: str) -> str | None:
        """Read and decrypt one secret.

        Args:
            name: The secret's name.

        Returns:
            The plain value, or ``None`` when the secret has never been written.

        Raises:
            ConfigurationError: If the stored value cannot be decrypted with the
                current key.
        """
        stored = self._repository.find_by_name(name)
        if stored is None:
            return None
        try:
            return self._cipher.decrypt(stored.encrypted_value.encode()).decode()
        except InvalidToken as error:
            message = f"secret '{name}' does not match the current TOKEN_ENCRYPTION_KEY"
            raise ConfigurationError(message) from error

    def put_secret(self, name: str, value: str) -> AppSecret:
        """Encrypt and store one secret, rotating any value already there.

        The record keeps its identifier across rotations, so the write is
        idempotent and safe to re-run.

        Args:
            name: The secret's name.
            value: The plain value to store.

        Returns:
            The stored record.
        """
        existing = self._repository.find_by_name(name)
        secret = AppSecret(
            name=name,
            encrypted_value=self._cipher.encrypt(value.encode()).decode(),
            rotated_at=self._clock.now(),
        )
        if existing is not None:
            secret.id = existing.id
        written = self._repository.bulk_upsert([secret])
        return written[0] if written else secret

    def delete_secret(self, name: str) -> bool:
        """Remove one secret.

        Args:
            name: The secret's name.

        Returns:
            ``True`` when a row was removed.
        """
        return self._repository.delete_by_name(name) > 0

    def round_trips(self, name: str, value: str) -> bool:
        """Write a throw-away secret, read it back and remove it again.

        Args:
            name: Name of the throw-away secret.
            value: What to write.

        Returns:
            Whether the value read back was the value written.
        """
        self.put_secret(name, value)
        read_back = self.get_secret(name)
        self.delete_secret(name)
        return read_back == value


def _build_cipher(encryption_key: SecretStr) -> Fernet:
    """Build the cipher, refusing a key the library cannot use.

    Args:
        encryption_key: The Fernet key from ``TOKEN_ENCRYPTION_KEY``.

    Returns:
        A cipher bound to that key.

    Raises:
        ConfigurationError: If the key is malformed.
    """
    try:
        return Fernet(encryption_key.get_secret_value().encode())
    except (ValueError, binascii.Error) as error:
        message = "TOKEN_ENCRYPTION_KEY is not a valid Fernet key"
        raise ConfigurationError(message) from error
