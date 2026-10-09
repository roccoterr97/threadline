"""Deployment configuration.

:func:`get_settings` is the **only** place in the application that reads
environment variables. Everything else receives a :class:`Settings` instance.
Values come from the process environment first and from the repository's
``.env`` file second; secrets are wrapped in :class:`~pydantic.SecretStr` so a
stray log line cannot print them.
"""

from __future__ import annotations

import re
from calendar import Day
from datetime import UTC, date, tzinfo
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, ValidationError, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from tracker.shared.constants.collection import MICROSOFT_CLIENT_ID, MICROSOFT_DEFAULT_TENANT
from tracker.shared.constants.mailbox import (
    IMAP_PRESETS,
    DeliveryRoute,
    ImapProvider,
    MailSource,
)
from tracker.shared.errors import ConfigurationError
from tracker.shared.time_zones import UTC_ZONE, canonical_zone_name

#: Repository root, four levels above ``src/tracker/shared``.
REPOSITORY_ROOT: Final[Path] = Path(__file__).resolve().parents[4]

#: The single ``.env`` file shared by the backend and the frontend build.
ENV_FILE: Path = REPOSITORY_ROOT / ".env"

#: Where ``tracker setup`` and ``tracker doctor`` write their log lines, so the
#: person following them sees only plain sentences while the details stay at
#: hand for whoever helps them. Kept out of git by the ``*.log`` rule.
SETUP_LOG_FILE: Path = REPOSITORY_ROOT / "backend" / "setup.log"


def in_project(path: Path) -> str:
    """Spell a path from the project's top folder, the way help text names it.

    Args:
        path: A path inside the repository.

    Returns:
        ``work/batches in the project folder``, never the machine's full path.
    """
    return f"{path.relative_to(REPOSITORY_ROOT).as_posix()} in the project folder"


_EMAIL_SEPARATOR: Final[str] = ","

# --- Owner settings ------------------------------------------------------------
# Everything about the person running Threadline. Each has a default that works
# for anybody, so a new owner sets only what differs. Kept in one block.

#: Name the summary and the command-line help use unless ``PRODUCT_NAME`` is set.
DEFAULT_PRODUCT_NAME: Final[str] = "Threadline"

#: Summary subject prefix unless ``SUMMARY_SUBJECT_PREFIX`` is set.
DEFAULT_SUMMARY_SUBJECT_PREFIX: Final[str] = "[Threadline]"

#: Zone "today" is read in unless ``OWNER_TIME_ZONE`` is set.
DEFAULT_TIME_ZONE: Final[str] = UTC_ZONE

_UNKNOWN_ZONE_MESSAGE: Final[str] = (
    "OWNER_TIME_ZONE must be a time-zone name such as Europe/Rome or UTC"
)

#: Days off unless ``OWNER_WEEKEND_DAYS`` is set.
DEFAULT_WEEKEND_DAYS: Final[frozenset[Day]] = frozenset({Day.SATURDAY, Day.SUNDAY})

#: Shortest subject prefix accepted. The mailbox collector ignores every subject
#: that starts with the prefix, so one or two characters would hide real mail.
MIN_SUBJECT_PREFIX_LENGTH: Final[int] = 3

#: What ``OWNER_WEEKEND_DAYS`` says for an owner with no day off.
NO_WEEKEND: Final[str] = "none"

_LIST_SEPARATOR: Final[str] = ","
_ABBREVIATION_LENGTH: Final[int] = 3
_WEEKDAYS_BY_NAME: Final[dict[str, Day]] = {
    **{day.name.lower(): day for day in Day},
    **{day.name[:_ABBREVIATION_LENGTH].lower(): day for day in Day},
}
_ONE_ADDRESS: Final[re.Pattern[str]] = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")
# --- End of owner settings constants -------------------------------------------

#: What an empty Microsoft sign-in setting falls back to.
_MICROSOFT_DEFAULTS: Final[dict[str, str]] = {
    "microsoft_client_id": MICROSOFT_CLIENT_ID,
    "microsoft_tenant": MICROSOFT_DEFAULT_TENANT,
}


# --- Mailboxes --------------------------------------------------------------

#: Mailboxes read unless ``MAIL_SOURCES`` says otherwise: Outlook, as before
#: other mailboxes existed, so an existing set-up keeps working unchanged.
DEFAULT_MAIL_SOURCES: Final[tuple[MailSource, ...]] = (MailSource.OUTLOOK,)

#: Highest TCP port number.
_MAX_PORT: Final[int] = 65_535

#: What a server name may never contain.
_NOT_A_HOST: Final[re.Pattern[str]] = re.compile(r"[\s/:@]")


class AppEnv(StrEnum):
    """Which deployment the process is running as."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    """Verbosity of the structured logger."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class Settings(BaseSettings):
    """Everything Threadline reads from the environment."""

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        # A line copied from .env.example as "NAME=" means "not set", not "".
        env_ignore_empty=True,
    )

    app_env: AppEnv = AppEnv.DEVELOPMENT
    log_level: LogLevel = LogLevel.INFO

    supabase_url: str = Field(description="https://<project-ref>.supabase.co")
    supabase_service_role_key: SecretStr
    supabase_anon_key: SecretStr
    token_encryption_key: SecretStr

    #: Optional: without it, or without a LinkedIn key, LinkedIn is skipped.
    owner_linkedin_profile_url: str | None = None
    owner_email_addresses: Annotated[tuple[str, ...], NoDecode]

    linkedin_access_token: SecretStr | None = None
    linkedin_token_expires_on: date | None = None

    #: Where the dashboard is published. Until it is, the summary carries no
    #: links rather than pointing at an address that is not the owner's.
    dashboard_base_url: str | None = None

    # --- Owner settings --------------------------------------------------------
    #: Where the summary goes; the first owner address when unset.
    summary_recipient: str | None = None
    #: The owner's name, for when an address such as ``jd123@`` does not spell it.
    owner_display_name: str | None = None
    #: IANA zone that decides what "today" is, such as ``Europe/Rome``.
    owner_time_zone: str = DEFAULT_TIME_ZONE
    #: Days that are not working days when a follow-up date is worked out.
    owner_weekend_days: Annotated[frozenset[Day], NoDecode] = DEFAULT_WEEKEND_DAYS
    #: What Threadline calls itself in the summary and the command-line help.
    product_name: str = DEFAULT_PRODUCT_NAME
    #: How every summary subject starts, and how the mailbox recognises one.
    summary_subject_prefix: str = DEFAULT_SUMMARY_SUBJECT_PREFIX

    @field_validator("summary_recipient")
    @classmethod
    def _require_one_address(cls, value: str | None) -> str | None:
        """Accept exactly one e-mail address, or nothing."""
        cleaned = (value or "").strip().lower()
        if not cleaned:
            return None
        if not _ONE_ADDRESS.match(cleaned):
            message = "SUMMARY_RECIPIENT must be exactly one e-mail address"
            raise ValueError(message)
        return cleaned

    @field_validator("owner_display_name", "owner_linkedin_profile_url")
    @classmethod
    def _blank_means_unset(cls, value: str | None) -> str | None:
        """Treat a value of only spaces as not set, and tidy the spacing."""
        cleaned = " ".join((value or "").split())
        return cleaned or None

    @field_validator("owner_time_zone")
    @classmethod
    def _require_known_zone(cls, value: str) -> str:
        """Accept an IANA zone name this machine knows, in any case; keep its real spelling."""
        cleaned = value.strip() or DEFAULT_TIME_ZONE
        canonical = canonical_zone_name(cleaned)
        if canonical is None:
            raise ValueError(_UNKNOWN_ZONE_MESSAGE)
        _load_time_zone(canonical)
        return canonical

    @field_validator("owner_weekend_days", mode="before")
    @classmethod
    def _parse_weekend(cls, value: Any) -> Any:  # noqa: ANN401 - raw env input
        """Read a comma-separated list of days, such as ``sat,sun`` or ``fri,sat``."""
        if not isinstance(value, str):
            return value
        names = [part.strip().lower() for part in value.split(_LIST_SEPARATOR) if part.strip()]
        if not names:
            return DEFAULT_WEEKEND_DAYS
        if names == [NO_WEEKEND]:
            return frozenset()
        unknown = [name for name in names if name not in _WEEKDAYS_BY_NAME]
        if unknown:
            message = "OWNER_WEEKEND_DAYS must list days such as sat,sun, or say none"
            raise ValueError(message)
        days = frozenset(_WEEKDAYS_BY_NAME[name] for name in names)
        if len(days) == len(Day):
            message = "OWNER_WEEKEND_DAYS must leave at least one working day"
            raise ValueError(message)
        return days

    @field_validator("product_name")
    @classmethod
    def _require_product_name(cls, value: str) -> str:
        """Keep the name on one line, and refuse one made only of spaces."""
        cleaned = " ".join(value.split())
        if not cleaned:
            message = "PRODUCT_NAME must not be blank"
            raise ValueError(message)
        return cleaned

    @field_validator("summary_subject_prefix")
    @classmethod
    def _require_distinctive_prefix(cls, value: str) -> str:
        """Refuse a prefix short enough to match real mail."""
        cleaned = " ".join(value.split())
        if len(cleaned) < MIN_SUBJECT_PREFIX_LENGTH:
            message = (
                f"SUMMARY_SUBJECT_PREFIX must be at least {MIN_SUBJECT_PREFIX_LENGTH} "
                "characters, such as [Threadline]"
            )
            raise ValueError(message)
        return cleaned

    @property
    def summary_recipient_address(self) -> str:
        """Where the summary goes: the configured recipient, else the first owner address."""
        return self.summary_recipient or self.owner_email_addresses[0]

    @property
    def owner_zone(self) -> tzinfo:
        """The owner's time zone, ready for date arithmetic."""
        return _load_time_zone(self.owner_time_zone)

    @property
    def linkedin_enabled(self) -> bool:
        """Whether LinkedIn is set up: the owner's profile and a key are both present."""
        has_profile = self.owner_linkedin_profile_url is not None
        return has_profile and self.linkedin_access_token is not None

    # --- End of owner settings --------------------------------------------------

    # --- Microsoft sign-in application (begin) -------------------------------
    #: Which registered application the mailbox sign-in uses. The default is a
    #: public open-source one; your own registration can replace it.
    microsoft_client_id: str = MICROSOFT_CLIENT_ID
    #: Which Microsoft accounts may sign in: ``consumers`` (personal accounts),
    #: ``common``, ``organizations`` or a directory identifier.
    microsoft_tenant: str = MICROSOFT_DEFAULT_TENANT

    @field_validator("microsoft_client_id", "microsoft_tenant")
    @classmethod
    def _plain_identifier(cls, value: str, info: ValidationInfo) -> str:
        """Fall back to the default when empty; reject anything that is not a plain name."""
        cleaned = value.strip()
        if not cleaned:
            return _MICROSOFT_DEFAULTS[info.field_name or ""]
        if "/" in cleaned or " " in cleaned:
            message = "must be a plain identifier such as 'consumers'"
            raise ValueError(message)
        return cleaned

    # --- Microsoft sign-in application (end) ---------------------------------

    # --- Mailboxes (begin) --------------------------------------------------
    #: Which mailboxes are read: ``outlook``, ``imap`` or both. At least one.
    mail_sources: Annotated[tuple[MailSource, ...], NoDecode] = DEFAULT_MAIL_SOURCES
    #: The IMAP mailbox's provider; ``custom`` means IMAP_HOST names the server.
    imap_provider: ImapProvider = ImapProvider.CUSTOM
    #: The IMAP server, when it is not the provider's usual one.
    imap_host: str | None = Field(default=None, validate_default=True)
    #: The IMAP server's port, when it is not the provider's usual one.
    imap_port: int | None = None
    #: The name the IMAP mailbox signs in with, usually its full address. Its
    #: app password is kept encrypted in the database, never here.
    imap_username: str | None = Field(default=None, validate_default=True)

    # --- Sending the summary (begin) ----------------------------------------
    #: How the summary is sent: ``smtp`` or ``gmail_connector``. Unset means
    #: ``smtp`` when an IMAP mailbox is read, else ``gmail_connector``.
    summary_delivery: DeliveryRoute | None = None
    #: The server that sends mail, when it is not the provider's usual one.
    smtp_host: str | None = None
    #: Its port, when it is not the provider's usual one.
    smtp_port: int | None = None
    # --- Sending the summary (end) ------------------------------------------

    @field_validator("mail_sources", mode="before")
    @classmethod
    def _parse_mail_sources(cls, value: Any) -> Any:  # noqa: ANN401 - raw env input
        """Read a comma-separated list such as ``outlook,imap``."""
        if not isinstance(value, str):
            return value
        names = [part.strip().lower() for part in value.split(_LIST_SEPARATOR) if part.strip()]
        known = {source.value: source for source in MailSource}
        if not names or any(name not in known for name in names):
            message = "MAIL_SOURCES must name at least one mailbox: outlook, imap or both"
            raise ValueError(message)
        return tuple(dict.fromkeys(known[name] for name in names))

    @field_validator("imap_provider", mode="before")
    @classmethod
    def _tidy_provider(cls, value: Any) -> Any:  # noqa: ANN401 - raw env input
        """Accept the provider however it is capitalised, such as ``Gmail``."""
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("imap_host")
    @classmethod
    def _require_host_for_custom(cls, value: str | None, info: ValidationInfo) -> str | None:
        """Accept a plain server name; insist on one for a custom provider."""
        cleaned = (value or "").strip().lower() or None
        if cleaned is not None and _NOT_A_HOST.search(cleaned):
            message = "IMAP_HOST must be a server name such as imap.example.com"
            raise ValueError(message)
        custom = info.data.get("imap_provider") is ImapProvider.CUSTOM
        if cleaned is None and custom and _reads_imap(info):
            message = "IMAP_HOST is needed when IMAP_PROVIDER is custom"
            raise ValueError(message)
        return cleaned

    @field_validator("imap_port", "smtp_port")
    @classmethod
    def _require_valid_port(cls, value: int | None, info: ValidationInfo) -> int | None:
        """Accept a real port number, or nothing."""
        if value is not None and not 0 < value <= _MAX_PORT:
            message = f"{(info.field_name or '').upper()} must be a port number such as 993"
            raise ValueError(message)
        return value

    @field_validator("smtp_host")
    @classmethod
    def _require_plain_smtp_host(cls, value: str | None) -> str | None:
        """Accept a plain server name, or nothing."""
        cleaned = (value or "").strip().lower() or None
        if cleaned is not None and _NOT_A_HOST.search(cleaned):
            message = "SMTP_HOST must be a server name such as smtp.example.com"
            raise ValueError(message)
        return cleaned

    @field_validator("summary_delivery", mode="before")
    @classmethod
    def _tidy_delivery(cls, value: Any) -> Any:  # noqa: ANN401 - raw env input
        """Accept the route however it is capitalised, such as ``SMTP``."""
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("imap_username")
    @classmethod
    def _require_username_for_imap(cls, value: str | None, info: ValidationInfo) -> str | None:
        """Insist on a sign-in name when an IMAP mailbox is to be read."""
        cleaned = (value or "").strip() or None
        if cleaned is None and _reads_imap(info):
            message = "IMAP_USERNAME is needed when MAIL_SOURCES includes imap"
            raise ValueError(message)
        return cleaned

    @property
    def outlook_enabled(self) -> bool:
        """Whether the Microsoft mailbox (and with it the calendar) is read."""
        return MailSource.OUTLOOK in self.mail_sources

    @property
    def imap_enabled(self) -> bool:
        """Whether a standard mailbox is read over IMAP."""
        return MailSource.IMAP in self.mail_sources

    @property
    def imap_server(self) -> tuple[str, int]:
        """The IMAP server and port: the provider's usual ones unless set."""
        preset = IMAP_PRESETS[self.imap_provider]
        return self.imap_host or preset.host, self.imap_port or preset.port

    @property
    def summary_route(self) -> DeliveryRoute:
        """How the summary is sent: as configured, else by SMTP when an IMAP mailbox is read."""
        if self.summary_delivery is not None:
            return self.summary_delivery
        return DeliveryRoute.SMTP if self.imap_enabled else DeliveryRoute.GMAIL_CONNECTOR

    @property
    def smtp_server(self) -> tuple[str, int]:
        """The sending server and port: the provider's usual ones unless set."""
        preset = IMAP_PRESETS[self.imap_provider]
        return self.smtp_host or preset.smtp_host, self.smtp_port or preset.smtp_port

    # --- Mailboxes (end) ----------------------------------------------------

    @field_validator("supabase_url")
    @classmethod
    def _require_https_url(cls, value: str) -> str:
        """Reject a database address that is not an HTTPS Supabase endpoint."""
        cleaned = value.strip().rstrip("/")
        if not cleaned.startswith("https://"):
            message = "SUPABASE_URL must start with https://"
            raise ValueError(message)
        return cleaned

    @field_validator("owner_email_addresses", mode="before")
    @classmethod
    def _split_email_addresses(cls, value: Any) -> Any:  # noqa: ANN401 - raw env input
        """Split a comma-separated list of the owner's own addresses."""
        if not isinstance(value, str):
            return value
        addresses = tuple(
            part.strip().lower() for part in value.split(_EMAIL_SEPARATOR) if part.strip()
        )
        if not addresses:
            message = "OWNER_EMAIL_ADDRESSES must list at least one address"
            raise ValueError(message)
        return addresses


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and cache the process configuration.

    Returns:
        The validated settings for this process.

    Raises:
        ConfigurationError: If a required value is missing or malformed. The
            message names the offending variables only — never their values.
    """
    try:
        return Settings(_env_file=ENV_FILE)  # pyright: ignore[reportCallIssue]
    except ValidationError as error:
        message = f"invalid configuration: {_describe(error)}"
        raise ConfigurationError(message) from error


def _reads_imap(info: ValidationInfo) -> bool:
    """Whether the sources validated so far include an IMAP mailbox."""
    return MailSource.IMAP in info.data.get("mail_sources", ())


def _load_time_zone(name: str) -> tzinfo:
    """Turn an IANA zone name into a time zone.

    ``UTC`` needs no time-zone database, so it works on a machine without one.

    Args:
        name: A zone name such as ``Europe/Rome`` or ``UTC``.

    Returns:
        The time zone.

    Raises:
        ValueError: If this machine does not know the zone. Pydantic turns it
            into the validation failure :func:`get_settings` reports.
    """
    if name == DEFAULT_TIME_ZONE:
        return UTC
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError(_UNKNOWN_ZONE_MESSAGE) from error


def reset_settings_cache() -> None:
    """Forget the cached settings so the next call re-reads the environment."""
    get_settings.cache_clear()


def _describe(error: ValidationError) -> str:
    """Summarise a validation failure without echoing any value."""
    problems = sorted(
        f"{'.'.join(str(part) for part in item['loc']).upper()} ({item['msg']})"
        for item in error.errors()
    )
    return "; ".join(problems)
