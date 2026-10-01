"""A made-up IMAP mailbox that behaves like imaplib, and records every command.

No test opens a socket. :class:`FakeImapServer` answers the handful of commands
the reader sends, in the shapes imaplib returns them, and keeps a log so tests
can prove that nothing but EXAMINE, SEARCH and ``BODY.PEEK`` fetches was sent.
"""

from __future__ import annotations

import imaplib
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import format_datetime

from pydantic import SecretStr

from tracker.infrastructure.imap.session import Answer, ImapAccount, ImapClient, ImapSession

APP_PASSWORD = "abcdefghijklmnop"
GMAIL_ACCOUNT = ImapAccount(
    host="imap.gmail.com",
    port=993,
    username="sam.rivera@gmail.example",
    label="Gmail",
    company="Google",
)
OWNER = "sam.rivera@gmail.example"
SENT = "[Gmail]/Sent Mail"

_RANGE = re.compile(r"<0\.(\d+)>")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


@dataclass
class StoredMessage:
    """One message on the fake server."""

    uid: int
    raw: bytes
    arrived: datetime
    thread: str = ""
    gmail_id: str = ""

    @property
    def header_block(self) -> bytes:
        """The header part of the raw message."""
        return self.raw.split(b"\r\n\r\n", 1)[0] + b"\r\n\r\n"


@dataclass
class FakeImapServer:
    """Stands in for ``imaplib.IMAP4_SSL``; every instance is one connection."""

    folders: dict[str, list[StoredMessage]]
    attributes: dict[str, str] = field(default_factory=dict)
    gmail: bool = True
    password: str = APP_PASSWORD
    log: list[tuple[str, ...]] = field(default_factory=list)
    connections: int = 0
    drop_next_command: int = 0
    _open: str = ""

    def connect(self, host: str, port: int, timeout: float) -> ImapClient:
        """The session's connector: every call is a new connection."""
        self.connections += 1
        self.log.append(("CONNECT", host, str(port), str(timeout)))
        return self

    def login(self, user: str, password: str) -> Answer:
        """Accept only the right app password."""
        self.log.append(("LOGIN", user))
        if password != self.password:
            message = "[AUTHENTICATIONFAILED] Invalid credentials (Failure)"
            raise imaplib.IMAP4.error(message)
        return "OK", [b"signed in"]

    def capability(self) -> Answer:
        """Offer Gmail's extension only when this server is Gmail."""
        self._maybe_drop()
        words = "IMAP4rev1 IDLE X-GM-EXT-1" if self.gmail else "IMAP4rev1 IDLE"
        return "OK", [words.encode()]

    def list(self, directory: str = '""', pattern: str = "*") -> Answer:
        """List the folders with their attributes."""
        self.log.append(("LIST", directory, pattern))
        lines = [
            f'({self.attributes.get(name, "\\HasNoChildren")}) "/" "{name}"'.encode()
            for name in self.folders
        ]
        return "OK", lines

    def select(self, mailbox: str = "INBOX", readonly: bool = False) -> Answer:
        """Open a folder, remembering whether it was read-only."""
        self.log.append(("SELECT", mailbox, "readonly" if readonly else "READ-WRITE"))
        name = mailbox.strip('"')
        if name not in self.folders:
            return "NO", [b"no such folder"]
        self._open = name
        return "OK", [str(len(self.folders[name])).encode()]

    def uid(self, command: str, *args: str) -> Answer:
        """Answer SEARCH and FETCH; anything else is logged and refused."""
        self.log.append(("UID", command, *args))
        self._maybe_drop()
        if command == "SEARCH":
            return self._search(args)
        if command == "FETCH":
            return self._fetch(args[0], args[1])
        return "BAD", [b"not supported by the fake"]

    def logout(self) -> Answer:
        """End the connection."""
        self.log.append(("LOGOUT",))
        return "BYE", [b"logged out"]

    def _maybe_drop(self) -> None:
        """Simulate a dropped line for the next few commands."""
        if self.drop_next_command:
            self.drop_next_command -= 1
            message = "socket error: EOF"
            raise imaplib.IMAP4.abort(message)

    def _messages(self) -> list[StoredMessage]:
        return self.folders[self._open]

    def _search(self, criteria: Sequence[str]) -> Answer:
        found = [message for message in self._messages() if _matches(message, criteria)]
        return "OK", [" ".join(str(message.uid) for message in found).encode()]

    def _fetch(self, numbers: str, items: str) -> Answer:
        wanted = {int(number) for number in numbers.split(",")}
        data: list[object] = []
        for sequence, message in enumerate(self._messages(), start=1):
            if message.uid not in wanted:
                continue
            envelope, literal = _answer(message, items, self.gmail)
            data.append((f"{sequence} ({envelope} {{{len(literal)}}}".encode(), literal))
            data.append(b")")
        return "OK", data


def _answer(message: StoredMessage, items: str, gmail: bool) -> tuple[str, bytes]:
    """The envelope and literal of one message's FETCH answer."""
    parts = [f"UID {message.uid}"]
    if "INTERNALDATE" in items:
        parts.append(f'INTERNALDATE "{_internal(message.arrived)}"')
    if gmail and "X-GM-THRID" in items:
        parts.append(f"X-GM-THRID {message.thread} X-GM-MSGID {message.gmail_id}")
    if "HEADER.FIELDS" in items:
        parts.append("BODY[HEADER.FIELDS (...)]")
        return " ".join(parts), message.header_block
    limit = _RANGE.search(items)
    parts.append("BODY[]<0>")
    raw = message.raw[: int(limit.group(1))] if limit else message.raw
    return " ".join(parts), raw


def _matches(message: StoredMessage, criteria: Sequence[str]) -> bool:
    """A tiny subset of IMAP SEARCH: SINCE, X-GM-THRID, and the header OR chain."""
    if criteria[0] == "SINCE":
        day = datetime.strptime(criteria[1], "%d-%b-%Y").replace(tzinfo=UTC)
        return message.arrived >= day
    if criteria[0] == "X-GM-THRID":
        return message.thread == criteria[1]
    root = criteria[4].strip('"').encode()
    return root in message.header_block


def _internal(moment: datetime) -> str:
    return f"{moment.day:02d}-{_MONTHS[moment.month - 1]}-{moment.year} {moment:%H:%M:%S} +0000"


def mail(
    *,
    sender: str,
    to: str = OWNER,
    subject: str,
    body: str = "Made-up body text.",
    sent: datetime,
    message_id: str,
    references: str = "",
    in_reply_to: str = "",
    unsubscribe: bool = False,
    html: str = "",
) -> bytes:
    """Build one made-up message as the server would store it."""
    message = EmailMessage()
    message["From"] = sender
    message["To"] = to
    message["Subject"] = subject
    message["Date"] = format_datetime(sent)
    message["Message-ID"] = message_id
    if references:
        message["References"] = references
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
    if unsubscribe:
        message["List-Unsubscribe"] = "<https://news.example/unsubscribe>"
    message.set_content(body)
    if html:
        message.add_alternative(html, subtype="html")
    return message.as_bytes().replace(b"\n", b"\r\n")


def session_on(server: FakeImapServer, password: str = APP_PASSWORD) -> ImapSession:
    """A session connected to the fake server, never really waiting."""
    return ImapSession(
        GMAIL_ACCOUNT,
        SecretStr(password),
        connect=server.connect,
        sleep=lambda _seconds: None,
    )


def writes_sent(server: FakeImapServer) -> list[tuple[str, ...]]:
    """Every logged command that could change the mailbox."""
    changing = {"STORE", "COPY", "MOVE", "EXPUNGE", "APPEND", "DELETE"}
    return [
        entry
        for entry in server.log
        if (entry[0] == "UID" and entry[1] in changing)
        or (entry[0] == "SELECT" and entry[2] != "readonly")
        or (entry[0] == "UID" and entry[1] == "FETCH" and _reads_without_peek(entry[3]))
    ]


def _reads_without_peek(items: str) -> bool:
    """Whether FETCH items would mark a message as read."""
    upper = items.upper()
    return "RFC822" in upper or upper.replace("BODY.PEEK[", "").count("BODY[") > 0
