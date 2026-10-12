"""The mailbox the owner chose, held in memory until the database can keep it.

A full run asks for the mailbox while Supabase starts a new project, so the
one to three minutes the project takes are not spent waiting. Its app
password is checked live straight away, but it can only be stored (encrypted,
in the database) once the project is up and its tables exist. Until the
mailbox step saves it, the answer lives here, in this run's memory only: it
is never written to ``.env`` or to any other file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import SecretStr

from tracker.infrastructure.imap.session import ImapAccount
from tracker.shared.constants.mailbox import ImapProvider, MailSource


@dataclass(frozen=True, slots=True)
class CheckedImapMailbox:
    """A mailbox read with an app password that its provider has just accepted.

    Attributes:
        provider: Who runs the mailbox.
        account: Its server and sign-in name.
        password: The app password, accepted live. Never shown or written down.
    """

    provider: ImapProvider
    account: ImapAccount
    password: SecretStr


#: The mailbox chosen: one read with an app password, or Outlook, which signs in through Microsoft.
MailboxAnswer = CheckedImapMailbox | Literal[MailSource.OUTLOOK]
