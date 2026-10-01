"""Which mailboxes the owner set up, each ready to be opened by the collector."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from pydantic import SecretStr

from tracker.infrastructure.imap.reader import ImapMailbox
from tracker.infrastructure.imap.session import ImapAccount, ImapSession
from tracker.infrastructure.microsoft.auth import MicrosoftAuthenticator
from tracker.infrastructure.microsoft.client import GraphMailbox
from tracker.infrastructure.secret_store import SecretStore, imap_password_name
from tracker.repositories import Repositories
from tracker.services.collection.mailbox import MailboxReader, MailboxSource
from tracker.shared.clock import Clock
from tracker.shared.config import Settings
from tracker.shared.constants.mailbox import IMAP_PRESETS, MailSource
from tracker.shared.errors import MailboxPasswordError


def configured_mailboxes(
    repositories: Repositories, settings: Settings, clock: Clock
) -> tuple[MailboxSource, ...]:
    """List the mailboxes the owner set up, in the order they are read.

    Args:
        repositories: Where the encrypted sign-in key and app password are kept.
        settings: The process configuration.
        clock: Supplies the current instant for key renewal.

    Returns:
        One source per configured mailbox: Outlook first, then the IMAP one.
    """
    sources: list[MailboxSource] = []
    if settings.outlook_enabled:
        sources.append(
            MailboxSource(MailSource.OUTLOOK, lambda: _outlook(repositories, settings, clock))
        )
    if settings.imap_enabled:
        sources.append(MailboxSource(MailSource.IMAP, lambda: _imap(repositories, settings, clock)))
    return tuple(sources)


def imap_account(settings: Settings) -> ImapAccount:
    """Describe the configured IMAP mailbox.

    Args:
        settings: The process configuration; its IMAP mailbox must be set up.

    Returns:
        Where the mailbox is and who signs in to it.
    """
    preset = IMAP_PRESETS[settings.imap_provider]
    host, port = settings.imap_server
    return ImapAccount(
        host=host,
        port=port,
        username=settings.imap_username or "",
        label=preset.label,
        company=preset.company,
    )


def saved_app_password(store: SecretStore, account: ImapAccount) -> SecretStr:
    """Read the IMAP mailbox's app password from the encrypted store.

    Args:
        store: The encrypted store.
        account: The mailbox.

    Returns:
        The app password.

    Raises:
        MailboxPasswordError: If none has been saved yet.
    """
    password = store.get_secret(imap_password_name(account.username))
    if password is None:
        message = f"no app password is saved for your {account.label}"
        raise MailboxPasswordError(message)
    return SecretStr(password)


@asynccontextmanager
async def _outlook(
    repositories: Repositories, settings: Settings, clock: Clock
) -> AsyncIterator[MailboxReader]:
    """Sign in to Microsoft and open the mailbox over Graph."""
    store = SecretStore(repositories.app_secrets, settings.token_encryption_key, clock)
    authenticator = MicrosoftAuthenticator.for_settings(store, clock, settings)
    async with authenticator, GraphMailbox(authenticator) as mailbox:
        yield mailbox


@asynccontextmanager
async def _imap(
    repositories: Repositories, settings: Settings, clock: Clock
) -> AsyncIterator[MailboxReader]:
    """Sign in to the IMAP mailbox with its saved app password."""
    store = SecretStore(repositories.app_secrets, settings.token_encryption_key, clock)
    account = imap_account(settings)
    session = ImapSession(account, saved_app_password(store, account))
    async with ImapMailbox(session) as mailbox:
        yield mailbox
