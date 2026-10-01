"""The set-up's view of an IMAP mailbox: check an app password live, and keep it.

It puts together what Threadline already has — the read-only IMAP reader, the
summary's SMTP mailer and the encrypted store — so the set-up can try a
password before saving it, without knowing how any of them works.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from pydantic import SecretStr
from supabase import Client

from tracker.infrastructure.imap.reader import ImapMailbox, MailboxSurvey
from tracker.infrastructure.imap.session import (
    ImapAccount,
    ImapConnector,
    ImapSession,
    connect_tls,
)
from tracker.infrastructure.secret_store import SecretStore, imap_password_name
from tracker.infrastructure.smtp import SmtpAccount, SmtpConnector, SmtpMailer, connect_smtp
from tracker.repositories.app_secrets import AppSecretRepository
from tracker.shared.clock import Clock


@dataclass(frozen=True, slots=True)
class StoreAccess:
    """What reaching the encrypted store needs.

    Attributes:
        supabase_url: The project address, where the password is stored.
        service_key: The secret key of that project.
        encryption_key: Locks the stored password.
    """

    supabase_url: str
    service_key: SecretStr
    encryption_key: SecretStr


class ImapConnection:
    """Checks an app password live and stores it encrypted, for the set-up."""

    def __init__(
        self,
        connect: Callable[[str, SecretStr], Client],
        clock: Clock,
        connect_imap: ImapConnector = connect_tls,
        smtp_connector: SmtpConnector = connect_smtp,
    ) -> None:
        """Bind the connection to a database client factory and a clock.

        Args:
            connect: Builds a Supabase client from an address and a secret key.
            clock: Supplies the rotation time of the stored password.
            connect_imap: Opens an IMAP connection; replaced in tests.
            smtp_connector: Opens an SMTP connection; replaced in tests.
        """
        self._connect = connect
        self._clock = clock
        self._connect_imap = connect_imap
        self._smtp_connector = smtp_connector

    async def has_password(self, access: StoreAccess, username: str) -> bool:
        """Tell whether an app password is stored for a mailbox.

        Args:
            access: What reaching the store needs.
            username: The mailbox's sign-in name.

        Returns:
            ``True`` when one is stored.
        """
        stored = self._repository(access).find_by_name(imap_password_name(username))
        return stored is not None

    async def check(
        self, account: ImapAccount, password: SecretStr, since: datetime
    ) -> MailboxSurvey:
        """Sign in, open the inbox read-only and count the window's messages.

        Args:
            account: The mailbox.
            password: The app password to try.
            since: Start of the window to count.

        Returns:
            What the mailbox holds.

        Raises:
            MailboxPasswordError: If the provider refused the password.
            SourceUnavailableError: If the server could not be reached.
        """
        session = ImapSession(account, password, connect=self._connect_imap)
        async with ImapMailbox(session) as mailbox:
            return await mailbox.survey(since)

    async def check_sending(self, account: SmtpAccount, password: SecretStr) -> None:
        """Sign in to the server the summary is sent through, then leave without sending.

        Args:
            account: The sending server and the sign-in name.
            password: The app password, which opens both servers.

        Raises:
            MailboxPasswordError: If the server refused the password.
            SourceUnavailableError: If the server could not be reached.
        """
        mailer = SmtpMailer(account, password, connect=self._smtp_connector)
        await asyncio.to_thread(mailer.verify)

    async def save_password(self, access: StoreAccess, username: str, password: SecretStr) -> None:
        """Store an app password, encrypted, replacing any earlier one.

        Args:
            access: What reaching the store needs.
            username: The mailbox's sign-in name.
            password: The app password, already checked.
        """
        store = SecretStore(self._repository(access), access.encryption_key, self._clock)
        store.put_secret(imap_password_name(username), password.get_secret_value())

    def _repository(self, access: StoreAccess) -> AppSecretRepository:
        """Build the secrets table's repository for the saved project."""
        return AppSecretRepository(self._connect(access.supabase_url, access.service_key))
