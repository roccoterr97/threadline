"""Sending one message from the owner's own mailbox over SMTP, standard library only.

The morning summary goes out from the mailbox Threadline already reads over
IMAP, signed in with the same app password. The connection is encrypted before
the password is sent: TLS from the first byte on port 465, STARTTLS on any
other port, always checking the server's certificate.

Only opening the connection is retried. Once a message may have been handed
over, a second attempt could deliver it twice, so a failure there is reported
instead.
"""

from __future__ import annotations

import smtplib
import ssl
import time
from collections.abc import Callable
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

from pydantic import SecretStr

from tracker.shared.constants.mailbox import SMTP_TIMEOUT_SECONDS, SMTP_TLS_PORT
from tracker.shared.constants.retry import SOURCE_REQUEST_ATTEMPTS, SOURCE_REQUEST_DELAY_SECONDS
from tracker.shared.errors import MailboxPasswordError, SourceUnavailableError
from tracker.shared.logging import get_logger

_log = get_logger(__name__)


class SmtpClient(Protocol):
    """The part of :class:`smtplib.SMTP` the mailer uses."""

    def starttls(self, *, context: ssl.SSLContext) -> object:
        """Upgrade the connection to TLS (sends EHLO first when needed)."""
        ...

    def login(self, user: str, password: str) -> object:
        """Sign in (sends EHLO first when needed)."""
        ...

    def send_message(self, msg: EmailMessage) -> object:
        """Hand one message over."""
        ...

    def quit(self) -> object:
        """End the session."""
        ...


#: Opens a connection: (host, port, timeout in seconds).
SmtpConnector = Callable[[str, int, float], SmtpClient]


def connect_smtp(host: str, port: int, timeout: float) -> SmtpClient:
    """Open a connection: TLS from the first byte on port 465, plain before STARTTLS otherwise.

    Args:
        host: The SMTP server.
        port: Its port.
        timeout: Seconds any one command may take.

    Returns:
        The connected client, not yet signed in.
    """
    if port == SMTP_TLS_PORT:
        return smtplib.SMTP_SSL(host, port, timeout=timeout, context=ssl.create_default_context())
    return smtplib.SMTP(host, port, timeout=timeout)


@dataclass(frozen=True, slots=True)
class SmtpAccount:
    """Where mail is sent from and who signs in.

    Attributes:
        host: The SMTP server.
        port: Its port.
        username: The sign-in name, usually the full address.
        label: The mailbox's name as the owner knows it ("Gmail").
        company: Who runs it ("Google"), for messages.
    """

    host: str
    port: int
    username: str
    label: str
    company: str


class SmtpMailer:
    """Signs in to the owner's SMTP server and, when asked, hands one message over."""

    def __init__(
        self,
        account: SmtpAccount,
        password: SecretStr,
        *,
        connect: SmtpConnector = connect_smtp,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Bind the mailer to a server and its app password.

        Args:
            account: Where mail is sent from.
            password: The app password.
            connect: Opens a connection; replaced in tests.
            sleep: How to wait between connection attempts; replaced in tests.
        """
        self._account = account
        self._password = password
        self._connect = connect
        self._sleep = sleep

    def verify(self) -> None:
        """Connect, encrypt and sign in, then leave without sending anything.

        Raises:
            MailboxPasswordError: If the server refused the app password.
            SourceUnavailableError: If the server could not be reached.
        """
        self._session(None)

    def send(self, message: EmailMessage) -> None:
        """Send one message.

        Args:
            message: The message, with its recipients in its headers.

        Raises:
            MailboxPasswordError: If the server refused the app password.
            SourceUnavailableError: If the server could not be reached or
                refused the message.
        """
        self._session(message)

    def _session(self, message: EmailMessage | None) -> None:
        """Sign in and, when there is one, send the message; always sign out."""
        client = self._open()
        try:
            if self._account.port != SMTP_TLS_PORT:
                client.starttls(context=ssl.create_default_context())
            client.login(self._account.username, self._password.get_secret_value())
            if message is not None:
                client.send_message(message)
        except smtplib.SMTPAuthenticationError:
            message_text = f"{self._account.company} refused the app password for sending"
            raise MailboxPasswordError(message_text) from None
        except (smtplib.SMTPException, OSError) as error:
            raise self._unavailable("smtp_send_failed", error) from None
        finally:
            _quit(client)

    def _open(self) -> SmtpClient:
        """Connect, trying again a bounded number of times."""
        account = self._account
        for attempt in range(1, SOURCE_REQUEST_ATTEMPTS + 1):
            try:
                return self._connect(account.host, account.port, SMTP_TIMEOUT_SECONDS)
            except (smtplib.SMTPException, OSError) as error:
                if attempt == SOURCE_REQUEST_ATTEMPTS:
                    raise self._unavailable("smtp_unreachable", error) from None
                _log.warning("smtp_connect_retry", attempt=attempt, error_type=type(error).__name__)
                self._sleep(SOURCE_REQUEST_DELAY_SECONDS)
        message = "no attempt was made"  # pragma: no cover - SOURCE_REQUEST_ATTEMPTS >= 1
        raise SourceUnavailableError(message)  # pragma: no cover

    def _unavailable(self, event: str, error: Exception) -> SourceUnavailableError:
        """Log one clean line and build the error the owner sees."""
        _log.error(event, host=self._account.host, error_type=type(error).__name__)
        return SourceUnavailableError(f"{self._account.label} could not send the summary")


def _quit(client: SmtpClient) -> None:
    """Sign out; a connection that is already gone is simply forgotten."""
    try:
        client.quit()
    except (smtplib.SMTPException, OSError) as error:
        _log.info("smtp_quit_failed", error_type=type(error).__name__)
