"""One signed-in, read-only IMAP connection, with retries.

The session offers only what reading needs: list the folders, open one with
EXAMINE (the read-only form of SELECT), search it, and fetch with
``BODY.PEEK`` so the server never marks a message as read. There is no method
that stores flags, copies, moves or deletes, so no caller can do any of that.

A dropped connection is reopened and the command tried again, a bounded number
of times, as the repository's retry policy requires. A refused password is
never retried.
"""

from __future__ import annotations

import imaplib
import re
import ssl
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final, Protocol

from pydantic import SecretStr

from tracker.infrastructure.imap.parser import FetchRecord, parse_fetch
from tracker.shared.constants.mailbox import IMAP_TIMEOUT_SECONDS
from tracker.shared.constants.retry import SOURCE_REQUEST_ATTEMPTS, SOURCE_REQUEST_DELAY_SECONDS
from tracker.shared.errors import MailboxPasswordError, SourceUnavailableError
from tracker.shared.logging import get_logger

_OK: Final[str] = "OK"

#: imaplib hands a literal over as a pair; a quoted name has two quote marks.
_PAIR: Final[int] = 2

#: One line of a LIST answer: ``(<attributes>) <delimiter> <name>``.
_LIST_LINE: Final[re.Pattern[str]] = re.compile(
    r'^\((?P<attributes>[^)]*)\)\s+(?:"(?:[^"\\]|\\.)*"|NIL)\s*(?P<name>.*)$',
    re.IGNORECASE,
)

#: What a folder name or search value may never contain: a line break would
#: end the command and start another one.
_LINE_BREAKS: Final[re.Pattern[str]] = re.compile(r"[\r\n]")

#: Failures of the connection itself, as opposed to a refusal by the server.
_TRANSPORT_ERRORS: Final[tuple[type[Exception], ...]] = (imaplib.IMAP4.abort, OSError)

#: Answers are tuples of a status and a data list, as imaplib returns them.
Answer = tuple[str, Sequence[object]]

_log = get_logger(__name__)


class ImapClient(Protocol):
    """The part of :class:`imaplib.IMAP4` the session uses — and nothing that writes."""

    def login(self, user: str, password: str) -> Answer:
        """Sign in."""
        ...

    def capability(self) -> Answer:
        """List what the server offers."""
        ...

    def list(self, directory: str = ..., pattern: str = ...) -> Answer:
        """List the folders."""
        ...

    def select(self, mailbox: str = ..., readonly: bool = ...) -> Answer:
        """Open a folder; always called with ``readonly=True`` (EXAMINE)."""
        ...

    def uid(self, command: str, *args: str) -> Answer:
        """Run a UID command; only SEARCH and FETCH are ever sent."""
        ...

    def logout(self) -> Answer:
        """End the session."""
        ...


#: Opens a connection: (host, port, timeout in seconds).
ImapConnector = Callable[[str, int, float], ImapClient]


def connect_tls(host: str, port: int, timeout: float) -> ImapClient:
    """Open a TLS connection, checking the server's certificate.

    Args:
        host: The IMAP server.
        port: Its TLS port.
        timeout: Seconds any one command may take.

    Returns:
        The connected client, not yet signed in.
    """
    context = ssl.create_default_context()
    return imaplib.IMAP4_SSL(host, port, ssl_context=context, timeout=timeout)


@dataclass(frozen=True, slots=True)
class ImapAccount:
    """Where a mailbox is and who signs in to it.

    Attributes:
        host: The IMAP server.
        port: Its TLS port.
        username: The sign-in name, usually the full address.
        label: The mailbox's name as the owner knows it ("Gmail").
        company: Who runs it ("Google"), for messages.
    """

    host: str
    port: int
    username: str
    label: str
    company: str


@dataclass(frozen=True, slots=True)
class Folder:
    """One folder of the mailbox.

    Attributes:
        name: The name exactly as the server spells it (possibly encoded).
        attributes: Its attributes, lower-cased, such as the Sent folder marker.
    """

    name: str
    attributes: frozenset[str]


class ImapSession:
    """A read-only IMAP session that reconnects when the line drops."""

    def __init__(
        self,
        account: ImapAccount,
        password: SecretStr,
        *,
        connect: ImapConnector = connect_tls,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Bind the session to a mailbox and its app password.

        Args:
            account: Where the mailbox is and who signs in.
            password: The app password.
            connect: Opens a connection; replaced in tests.
            sleep: How to wait between attempts; replaced in tests.
        """
        self._account = account
        self._password = password
        self._connect = connect
        self._sleep = sleep
        self._client: ImapClient | None = None
        self._folder: str | None = None

    def open(self) -> None:
        """Connect and sign in, trying again when the connection fails.

        Raises:
            MailboxPasswordError: If the server refused the app password.
            SourceUnavailableError: If the server could not be reached.
        """
        self._with_retries(lambda _client: None)

    def close(self) -> None:
        """Sign out; a connection that is already gone is simply forgotten."""
        client, self._client, self._folder = self._client, None, None
        if client is None:
            return
        try:
            client.logout()
        except (imaplib.IMAP4.error, OSError) as error:
            _log.info("imap_logout_failed", error_type=type(error).__name__)

    def capabilities(self) -> frozenset[str]:
        """What the server offers once signed in, upper-cased."""
        data = self._run(lambda client: client.capability())
        words = b" ".join(item for item in data if isinstance(item, bytes)).decode(
            "ascii", "replace"
        )
        return frozenset(word.upper() for word in words.split())

    def folders(self) -> list[Folder]:
        """List every folder of the mailbox."""
        data = self._run(lambda client: client.list())
        return [folder for line in data if (folder := _folder(line)) is not None]

    def examine(self, folder: str) -> None:
        """Open a folder read-only, unless it is already the open one.

        Args:
            folder: The folder's name, exactly as :meth:`folders` spelled it.
        """
        if self._folder == folder:
            return
        self._run(lambda client: client.select(quote(folder), readonly=True))
        self._folder = folder

    def search(self, *criteria: str) -> list[int]:
        """Search the open folder.

        Args:
            criteria: IMAP search keys; values must already be quoted.

        Returns:
            The matching UIDs, in ascending order.
        """
        data = self._run(lambda client: client.uid("SEARCH", *criteria))
        found = b" ".join(item for item in data if isinstance(item, bytes)).split()
        return sorted(int(uid) for uid in found if uid.isdigit())

    def fetch(self, uids: Sequence[int], items: str) -> list[FetchRecord]:
        """Fetch items for some messages of the open folder.

        Args:
            uids: The messages.
            items: The FETCH items; every body item is a ``BODY.PEEK``.

        Returns:
            One record per message the server answered for.
        """
        if not uids:
            return []
        numbers = ",".join(str(uid) for uid in uids)
        return parse_fetch(self._run(lambda client: client.uid("FETCH", numbers, items)))

    def _run(self, command: Callable[[ImapClient], Answer]) -> Sequence[object]:
        """Run one command, reconnecting and trying again when the line drops.

        Raises:
            SourceUnavailableError: If the server refused the command or never
                answered.
        """
        try:
            status, data = self._with_retries(command)
        except imaplib.IMAP4.abort:
            raise
        except imaplib.IMAP4.error:
            status, data = "", ()
        if status != _OK:
            message = f"{self._account.label} refused a read-only request"
            raise SourceUnavailableError(message)
        return data

    def _with_retries[T](self, command: Callable[[ImapClient], T]) -> T:
        """Run a command on a signed-in connection, with bounded retries."""
        for attempt in range(1, SOURCE_REQUEST_ATTEMPTS + 1):
            try:
                return command(self._signed_in())
            except _TRANSPORT_ERRORS as error:
                self._forget()
                _log.warning(
                    "imap_connection_dropped",
                    attempt=attempt,
                    error_type=type(error).__name__,
                )
                if attempt < SOURCE_REQUEST_ATTEMPTS:
                    self._sleep(SOURCE_REQUEST_DELAY_SECONDS)
        message = f"{self._account.label} did not answer"
        raise SourceUnavailableError(message)

    def _signed_in(self) -> ImapClient:
        """The open connection, connecting, signing in and reopening the folder if needed."""
        if self._client is not None:
            return self._client
        client = self._connect(self._account.host, self._account.port, IMAP_TIMEOUT_SECONDS)
        try:
            client.login(self._account.username, self._password.get_secret_value())
        except imaplib.IMAP4.abort:
            raise
        except imaplib.IMAP4.error:
            _log.warning("imap_password_refused", host=self._account.host)
            message = f"{self._account.company} refused the app password"
            raise MailboxPasswordError(message) from None
        self._client = client
        folder, self._folder = self._folder, None
        if folder is not None:
            client.select(quote(folder), readonly=True)
            self._folder = folder
        return client

    def _forget(self) -> None:
        """Drop a broken connection without trying to sign out of it."""
        self._client = None


def quote(value: str) -> str:
    """Write a value as an IMAP quoted string.

    Args:
        value: A folder name or a search value, possibly from somebody's inbox.

    Returns:
        The value in double quotes, with quotes and backslashes escaped and
        line breaks removed, so it can never end the command early.
    """
    cleaned = _LINE_BREAKS.sub("", value)
    escaped = cleaned.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _folder(line: object) -> Folder | None:
    """Read one line of a LIST answer."""
    if isinstance(line, tuple) and len(line) == _PAIR:
        head, name = line
        if not isinstance(head, bytes) or not isinstance(name, bytes):
            return None
        parsed = _LIST_LINE.match(head.decode("utf-8", "replace"))
        if parsed is None:
            return None
        return _entry(parsed.group("attributes"), name.decode("utf-8", "replace"))
    if not isinstance(line, bytes):
        return None
    parsed = _LIST_LINE.match(line.decode("utf-8", "replace"))
    if parsed is None:
        return None
    return _entry(parsed.group("attributes"), _unquote(parsed.group("name").strip()))


def _entry(attributes: str, name: str) -> Folder | None:
    """Build a folder from its attributes and name; ``None`` without a name."""
    if not name:
        return None
    return Folder(name=name, attributes=frozenset(attributes.lower().split()))


def _unquote(name: str) -> str:
    """Undo IMAP quoting of a folder name."""
    if len(name) >= _PAIR and name.startswith('"') and name.endswith('"'):
        return name[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return name
