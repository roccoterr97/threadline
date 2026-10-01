"""Which mailboxes Threadline can read, and the tuning for standard (IMAP) ones.

Microsoft's mailbox is read over Graph (see :mod:`.collection`); every other
mailbox — Gmail, iCloud, Yahoo, Fastmail or any provider that offers IMAP — is
read over IMAP with an app password. The same app password sends the morning
summary over SMTP. The provider presets below are public facts about each
provider, not configuration: the owner only picks one.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class MailSource(StrEnum):
    """The kinds of mailbox Threadline reads."""

    OUTLOOK = "outlook"
    IMAP = "imap"


class DeliveryRoute(StrEnum):
    """How the morning summary reaches the owner.

    ``smtp`` sends it from the owner's own IMAP mailbox with its app password,
    which works anywhere, including GitHub Actions. ``gmail_connector`` leaves
    it to the Gmail connector of a Claude cloud routine, the alternative route.
    """

    SMTP = "smtp"
    GMAIL_CONNECTOR = "gmail_connector"


class ImapProvider(StrEnum):
    """Providers with known IMAP settings, plus one for any other mailbox."""

    GMAIL = "gmail"
    ICLOUD = "icloud"
    YAHOO = "yahoo"
    FASTMAIL = "fastmail"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class ImapPreset:
    """What Threadline knows about one provider.

    Attributes:
        label: The mailbox's name as the owner knows it ("Gmail").
        company: Who runs it, for "Google refused the app password".
        host: The IMAP server, empty for a provider the owner describes.
        port: The IMAP server's port (implicit TLS).
        smtp_host: The server that sends mail, empty for a provider the owner
            describes.
        smtp_port: Its port: 465 is TLS from the first byte, any other is
            upgraded with STARTTLS.
        app_password_page: Where an app password is made, or the provider's help
            page about it when there is no direct link; empty when unknown.
    """

    label: str
    company: str
    host: str
    port: int
    smtp_host: str
    smtp_port: int
    app_password_page: str


#: The port every provider below uses: IMAP over TLS from the first byte.
IMAP_TLS_PORT: Final[int] = 993

#: SMTP over TLS from the first byte (RFC 8314). Any other port is upgraded
#: with STARTTLS before the password is sent.
SMTP_TLS_PORT: Final[int] = 465

#: SMTP submission upgraded with STARTTLS; the only port iCloud offers.
SMTP_STARTTLS_PORT: Final[int] = 587

IMAP_PRESETS: Final[dict[ImapProvider, ImapPreset]] = {
    ImapProvider.GMAIL: ImapPreset(
        label="Gmail",
        company="Google",
        host="imap.gmail.com",
        port=IMAP_TLS_PORT,
        smtp_host="smtp.gmail.com",
        smtp_port=SMTP_TLS_PORT,
        app_password_page="https://myaccount.google.com/apppasswords",
    ),
    ImapProvider.ICLOUD: ImapPreset(
        label="iCloud Mail",
        company="Apple",
        host="imap.mail.me.com",
        port=IMAP_TLS_PORT,
        smtp_host="smtp.mail.me.com",
        smtp_port=SMTP_STARTTLS_PORT,
        app_password_page="https://account.apple.com",
    ),
    ImapProvider.YAHOO: ImapPreset(
        label="Yahoo Mail",
        company="Yahoo",
        host="imap.mail.yahoo.com",
        port=IMAP_TLS_PORT,
        smtp_host="smtp.mail.yahoo.com",
        smtp_port=SMTP_TLS_PORT,
        app_password_page="https://login.yahoo.com/account/security",
    ),
    ImapProvider.FASTMAIL: ImapPreset(
        label="Fastmail",
        company="Fastmail",
        host="imap.fastmail.com",
        port=IMAP_TLS_PORT,
        smtp_host="smtp.fastmail.com",
        smtp_port=SMTP_TLS_PORT,
        app_password_page=(
            "https://www.fastmail.help/hc/en-us/articles/360058752854-App-passwords"
        ),
    ),
    ImapProvider.CUSTOM: ImapPreset(
        label="mailbox",
        company="your mail provider",
        host="",
        port=IMAP_TLS_PORT,
        smtp_host="",
        smtp_port=SMTP_TLS_PORT,
        app_password_page="",
    ),
}

#: Name under which a mailbox's app password is stored, encrypted, in the
#: database; the mailbox's address follows the colon, so several can coexist.
IMAP_PASSWORD_SECRET_PREFIX: Final[str] = "imap_app_password:"

# --- Sending the summary ------------------------------------------------------

#: Seconds one SMTP command may take before the connection is given up.
SMTP_TIMEOUT_SECONDS: Final[float] = 30.0

# --- Reading ------------------------------------------------------------------

#: Seconds one IMAP command may take before the connection is given up.
IMAP_TIMEOUT_SECONDS: Final[float] = 30.0

#: Messages whose headers are asked for in one FETCH command.
IMAP_FETCH_BATCH_SIZE: Final[int] = 100

#: Messages whose bodies are asked for in one FETCH command. Far fewer than
#: headers: a body may be as large as ``IMAP_MAX_FETCH_BYTES``, and the whole
#: answer has to arrive within ``IMAP_TIMEOUT_SECONDS`` and fit in memory.
IMAP_BODY_BATCH_SIZE: Final[int] = 10

#: Days the IMAP SINCE search starts before the window. SINCE compares dates
#: in the server's own time zone, and the window's start is a UTC moment, so
#: one day earlier never misses a message; the exact start is applied after.
IMAP_SINCE_SLACK_DAYS: Final[int] = 1

#: Most messages read from one folder in one search; when more match, only the
#: newest this many are read. The same order of size as the Graph reader's
#: ceiling (50 a page, 200 pages).
IMAP_MAX_MESSAGES_PER_FOLDER: Final[int] = 10_000

#: Bytes of a message fetched for its body. The text comes first in almost
#: every message; this keeps a large attachment from ever being downloaded.
IMAP_MAX_FETCH_BYTES: Final[int] = 1_000_000

#: Characters of body text kept per message; the rest is cut off.
MAX_BODY_CHARACTERS: Final[int] = 50_000

#: The folder every IMAP mailbox has.
IMAP_INBOX: Final[str] = "INBOX"

#: The attribute a server puts on the Sent folder (RFC 6154), in any language.
IMAP_SENT_ATTRIBUTE: Final[str] = "\\sent"

#: Sent-folder names tried, in order, when no folder carries the attribute.
IMAP_SENT_FOLDER_NAMES: Final[tuple[str, ...]] = (
    "Sent",
    "Sent Messages",
    "Sent Items",
    "Sent Mail",
    "[Gmail]/Sent Mail",
    "INBOX.Sent",
    "INBOX/Sent",
)

#: The capability a server advertises when it offers Gmail's thread identifiers.
GMAIL_EXTENSION_CAPABILITY: Final[str] = "X-GM-EXT-1"

#: The headers the metadata pass asks for. Deliberately no body.
IMAP_METADATA_HEADERS: Final[tuple[str, ...]] = (
    "MESSAGE-ID",
    "IN-REPLY-TO",
    "REFERENCES",
    "FROM",
    "TO",
    "REPLY-TO",
    "SUBJECT",
    "DATE",
    "LIST-UNSUBSCRIBE",
)

#: Month abbreviations IMAP dates use, whatever the machine's language.
IMAP_MONTHS: Final[tuple[str, ...]] = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)
