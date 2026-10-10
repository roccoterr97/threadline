"""Fakes for the set-up: a scripted conversation, an in-memory ``.env`` and services.

Nothing here touches a terminal, a file outside the test folder or the network.
"""

from __future__ import annotations

import hashlib
import os
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from pydantic import SecretStr

from tracker.domain.categories import Category
from tracker.domain.daily_start import DailyStartStatus
from tracker.domain.linkedin_sign_in import LinkedInApp, LinkedInGrant, SignInProblem
from tracker.domain.supabase import (
    ApiKey,
    ApiKeyKind,
    AuthSettings,
    NewProject,
    Organization,
    SealedAccessToken,
    SupabaseProject,
)
from tracker.infrastructure.claude_setup_token import ClaudeCodeState, ClaudeKeyScreen
from tracker.infrastructure.github_cli import GitHubRepository, WorkflowRun
from tracker.infrastructure.imap.connection import StoreAccess
from tracker.infrastructure.imap.reader import MailboxSurvey
from tracker.infrastructure.imap.session import ImapAccount
from tracker.infrastructure.microsoft.connection import MicrosoftAccess, ShowCode
from tracker.infrastructure.netlify_api import NetlifyDeploy, NetlifySite
from tracker.infrastructure.smtp import SmtpAccount
from tracker.infrastructure.web_probe import WebPage
from tracker.services.database_structure import KNOWN_MIGRATIONS, MigrationFile
from tracker.services.profile.applier import ApplyReport, CategoryChanges
from tracker.services.profile.choice import Choice, Effect, SavedChoice
from tracker.services.setup.context import SetupContext
from tracker.services.setup.dashboard_package import pack
from tracker.services.setup.ports import SetupGateways
from tracker.services.setup.supabase_session import TokenRoute
from tracker.services.setup.workflow_schedule import Schedule, write_schedule
from tracker.shared.clock import FixedClock
from tracker.shared.constants.dashboard import ARCHIVE_NAME, CHECKSUM_NAME, RELEASE_ASSET_URL
from tracker.shared.constants.github import DAILY_RUN_TITLE, WORKFLOW_FILE, WorkflowMode
from tracker.shared.constants.setup import SUPABASE_BROWSER_SIGN_IN_PAGE
from tracker.shared.errors import (
    ClaudeKeyNotMadeError,
    DatabaseStructureMissingError,
    DatabaseUnavailableError,
    LinkedInSignInError,
    MailboxPasswordError,
    SiteNameTakenError,
    SourceAuthError,
    SourcePermissionError,
    SourceRequestRejectedError,
    SourceUnavailableError,
    WorkflowNotEnabledError,
    WorkflowNotStartedError,
)

PROJECT_URL = "https://abcdefghijklmnop.supabase.co"
PROJECT_REF = "abcdefghijklmnop"
GOOD_PUBLISHABLE = "sb_publishable_good"
GOOD_SECRET = "sb_secret_good"
GOOD_TOKEN = "sbp_good"
#: A scoped Supabase token: it may list and create projects, but Supabase answers
#: "too little access" to everything inside a project, as it does for revealing keys.
NARROW_TOKEN = "sbp_fc_scoped"
#: The answer that picks a pasted Supabase token over the browser sign-in.
PASTE = str(TokenRoute.PASTE.value)
#: The code the Supabase sign-in page shows in the fake.
GOOD_CODE = "a1b2c3d4"
GOOD_LINKEDIN = "linkedin-good"
GOOD_CLIENT_ID = "78linkedinapp1"
GOOD_CLIENT_SECRET = "WPL_AP1.good-secret"
#: When the key LinkedIn hands out stops working, in the fake.
LINKEDIN_KEY_EXPIRES_AT = datetime(2027, 9, 24, 7, 0, tzinfo=UTC)
OWNER_EMAIL = "you@example.com"
#: The title GitHub shows on a refresh, from the workflow's run-name.
REFRESH_RUN_TITLE = "Threadline refresh"
GOOD_APP_PASSWORD = "wxyzwxyzwxyzwxyz"
GOOD_GITHUB_TOKEN = "github_pat_good"
NEW_PROJECT_REF = "newprojectrefabcdefg"
ORGANIZATION = Organization(slug="made-up-org", name="Made-up organization")


def good_keys() -> list[ApiKey]:
    """The keys a new project has: one publishable, one secret, and a legacy one left out."""
    return [
        ApiKey(ApiKeyKind.PUBLISHABLE, "default", SecretStr(GOOD_PUBLISHABLE)),
        ApiKey(ApiKeyKind.SECRET, "default", SecretStr(GOOD_SECRET)),
    ]


GOOD_NETLIFY_TOKEN = "nfp_good"

#: The built dashboard as the release workflow publishes it (made-up content).
BUILT_SITE: dict[str, bytes] = {
    "index.html": b'<!doctype html><script src="/config.js"></script>',
    "assets/index-a1b2c3.js": b"console.info('dashboard')",
    "_headers": b"/*\n  X-Frame-Options: DENY\n",
    "_redirects": b"/* /index.html 200\n",
}
ARCHIVE_URL = RELEASE_ASSET_URL.format(name=ARCHIVE_NAME)
CHECKSUM_URL = RELEASE_ASSET_URL.format(name=CHECKSUM_NAME)


def release_downloads(site: Mapping[str, bytes] | None = None) -> dict[str, bytes]:
    """The two release files, by address: the zipped site and its SHA-256 line."""
    archive = pack(BUILT_SITE if site is None else site)
    checksum = f"{hashlib.sha256(archive).hexdigest()}  {ARCHIVE_NAME}\n".encode()
    return {ARCHIVE_URL: archive, CHECKSUM_URL: checksum}


#: The key the set-up makes for the on-time morning start's timer.
DAILY_START_KEY = "daily-start-key-0123456789abcdefghijklmnopqrstuv"


class ScriptedIO:
    """Answers questions from a script and records everything said."""

    def __init__(self, answers: list[str | bool] | None = None, *, clipboard: bool = True) -> None:
        self.answers: deque[str | bool] = deque(answers or [])
        self.said: list[str] = []
        self.defaults: dict[str, str | None] = {}
        self.exact: list[str] = []
        self.opened: list[str] = []
        self.copied: list[str] = []
        self.secret_prompts: list[str] = []
        self.clipboard = clipboard
        self.on_pause: Callable[[str], None] | None = None

    def say(self, text: str) -> None:
        self.said.append(text)

    def ask(self, prompt: str, *, default: str | None = None, exact: bool = False) -> str:
        self.defaults[prompt] = default
        if exact:
            self.exact.append(prompt)
        answer = self._next(prompt)
        if answer == "":
            return default or ""
        return str(answer)

    def ask_secret(self, prompt: str) -> str:
        self.secret_prompts.append(prompt)
        return str(self._next(prompt))

    def confirm(self, prompt: str, *, default: bool) -> bool:
        answer = self._next(prompt)
        return default if answer == "" else bool(answer)

    def pause(self, prompt: str) -> None:
        self.said.append(f"[paused] {prompt}")
        if self.on_pause is not None:
            self.on_pause(prompt)

    def open_page(self, url: str) -> None:
        self.opened.append(url)

    def copy(self, value: str) -> bool:
        if not self.clipboard:
            return False
        self.copied.append(value)
        return True

    def text(self) -> str:
        return "\n".join(self.said)

    def _next(self, prompt: str) -> str | bool:
        if not self.answers:
            message = f"unexpected question: {prompt}"
            raise AssertionError(message)
        return self.answers.popleft()


class MemoryEnv:
    """An in-memory ``.env``."""

    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values: dict[str, str] = dict(values or {})

    def get(self, name: str) -> str | None:
        return self.values.get(name) or None

    def set(self, name: str, value: str) -> None:
        self.values[name] = value

    def names(self) -> tuple[str, ...]:
        return tuple(name for name, value in self.values.items() if value)


#: Columns that were text with a check constraint until a migration made them enums.
TEXT_UNTIL: dict[tuple[str, str], str] = {("run_logs", "trigger"): "0012_refresh_trigger"}

#: The migration that creates every table the probes look at.
SCHEMA_MIGRATION = "0001_schema"


@dataclass
class FakeAdmin:
    """The service-key helper, over sets of present objects.

    It answers like the database would: a column still text before the
    migration that made it an enum filters on any value without complaint.
    """

    present: set[str] = field(default_factory=lambda: set(KNOWN_MIGRATIONS))
    owners: list[str] = field(default_factory=list)
    users: dict[str, str] = field(default_factory=dict)
    key_ok: bool = True
    #: The on-time morning start: the daily time and zone the database holds,
    #: the timer's saved address and key, and whether its job exists.
    schedule: tuple[time, str] | None = None
    daily_start: tuple[str, str] | None = None
    job_scheduled: bool = False
    last_started_on: date | None = None
    #: Makes the next database call fail as an outage.
    daily_start_down: bool = False
    #: How many of the next calls a project that is still waking up does not answer.
    unanswered_calls: int = 0

    def has_columns(self, table: str, columns: str) -> bool:
        return self._marker_present(table, columns)

    def accepts_value(self, table: str, column: str, value: str) -> bool:
        if self._still_text(table, column):
            return True
        return self._marker_present(table, f"{column}={value}")

    def is_enum_column(self, table: str, column: str) -> bool:
        return SCHEMA_MIGRATION in self.present and not self._still_text(table, column)

    def has_row(self, table: str, matches: Mapping[str, str]) -> bool:
        return self._marker_present(table, _row_detail(tuple(matches.items())))

    def _still_text(self, table: str, column: str) -> bool:
        migration = TEXT_UNTIL.get((table, column))
        return migration is not None and migration not in self.present

    def check_service_key(self) -> None:
        self._answers()
        if not self.key_ok:
            message = "Supabase refused the secret key"
            raise SourceAuthError(message)

    def owner_ids(self) -> tuple[str, ...]:
        return tuple(self.owners)

    def add_owner(self, user_id: str) -> None:
        if user_id not in self.owners:
            self.owners.append(user_id)

    def find_user_id(self, email: str) -> str | None:
        return self.users.get(email)

    def user_email(self, user_id: str) -> str | None:
        return next((email for email, known in self.users.items() if known == user_id), None)

    def create_confirmed_user(self, email: str) -> str | None:
        if email in self.users:
            return None
        self.users[email] = f"user-{len(self.users) + 1}"
        return self.users[email]

    def save_daily_schedule(self, run_at: time, time_zone: str) -> None:
        self._daily_start_reachable()
        self.schedule = (run_at, time_zone)

    def save_daily_start(self, function_url: str, key: SecretStr) -> None:
        self._daily_start_reachable()
        self.daily_start = (function_url, key.get_secret_value())
        self.job_scheduled = True

    def daily_start_status(self) -> DailyStartStatus:
        self._daily_start_reachable()
        return DailyStartStatus(
            job_scheduled=self.job_scheduled,
            switched_on=self.daily_start is not None,
            run_at=self.schedule[0] if self.schedule else None,
            time_zone=self.schedule[1] if self.schedule else None,
            last_started_on=self.last_started_on,
        )

    def _daily_start_reachable(self) -> None:
        if self.daily_start_down:
            message = "Supabase did not answer the daily_start request"
            raise DatabaseUnavailableError(message)
        if "0017_daily_start" not in self.present:
            message = "the database does not have the on-time morning start yet"
            raise DatabaseStructureMissingError(message)

    def _answers(self) -> None:
        if self.unanswered_calls > 0:
            self.unanswered_calls -= 1
            message = "Supabase did not answer"
            raise DatabaseUnavailableError(message)

    def _marker_present(self, table: str, detail: str) -> bool:
        self._answers()
        for name, marker in KNOWN_MIGRATIONS.items():
            if marker is not None and _describes(marker, table, detail):
                return name in self.present
        return True


def _describes(marker: object, table: str, detail: str) -> bool:
    """Whether a known marker is the one being asked about."""
    if getattr(marker, "table", None) != table:
        return False
    columns = getattr(marker, "columns", None)
    if columns is not None:
        return columns == detail
    matches = getattr(marker, "matches", None)
    if matches is not None:
        return _row_detail(matches) == detail
    return f"{getattr(marker, 'column', '')}={getattr(marker, 'value', '')}" == detail


def _row_detail(matches: tuple[tuple[str, str], ...]) -> str:
    """The values a row probe asks for, written as one string."""
    return ",".join(f"{column}={value}" for column, value in matches)


@dataclass
class FakePlatform:
    """Supabase's Management API and public auth settings.

    Every Management API call refuses any token but ``GOOD_TOKEN``, as Supabase would;
    ``NARROW_TOKEN`` is let through only to the organization and project calls.
    """

    signups_off: list[bool] = field(default_factory=lambda: [True])
    recorded: set[str] = field(default_factory=set)
    applied: list[str] = field(default_factory=list)
    fail_on: str | None = None
    rejections: dict[str, int] = field(default_factory=dict)
    admin: FakeAdmin | None = None
    secrets: dict[str, str] = field(default_factory=dict)
    deployed: list[tuple[str, tuple[str, ...], bool]] = field(default_factory=list)
    organization_list: list[Organization] = field(default_factory=lambda: [ORGANIZATION])
    project_list: list[SupabaseProject] = field(default_factory=list)
    created: list[NewProject] = field(default_factory=list)
    #: What each look at a project answers, in turn; the last repeats.
    statuses: list[str] = field(default_factory=lambda: ["COMING_UP", "ACTIVE_HEALTHY"])
    #: How many looks at a project are turned down with "too many requests" first.
    busy_looks: int = 0
    create_refusal: str | None = None
    keys: list[ApiKey] = field(default_factory=good_keys)
    created_keys: list[tuple[ApiKeyKind, str]] = field(default_factory=list)
    auth_changes: list[tuple[str, AuthSettings]] = field(default_factory=list)
    auth_refusal: type[Exception] | None = None
    #: The project's Redirect URLs before the set-up touches them.
    redirect_list: list[str] = field(default_factory=list)
    #: What the public settings answer after sign-ups were switched off, in turn.
    signups_after_change: list[bool] = field(default_factory=lambda: [True])
    #: Whether a migration may be read and applied with the good token.
    migrations_allowed: bool = True
    #: Whether the token may read the applied files but not run one (a 401 or 403 on the POST).
    apply_forbidden: bool = False
    organization_reads: int = 0
    #: How many of the next reads of the public settings a project still waking up misses.
    unanswered_settings: int = 0
    #: Whether creating a project is lost to a timeout after Supabase made it.
    create_times_out: bool = False
    #: Whether ``NARROW_TOKEN`` may list the organizations (and so pass the paste check).
    narrow_may_list: bool = True
    #: The pages the browser opened, shared with the conversation; the sign-in reads its key there.
    opened: list[str] = field(default_factory=list)
    #: Every code typed for a browser sign-in, in turn.
    sign_in_codes: list[str] = field(default_factory=list)
    #: The token a browser sign-in makes.
    sign_in_token_value: str = GOOD_TOKEN
    #: What the sign-in session raises for the right code instead of answering.
    sign_in_failure: Exception | None = None
    #: Whether the sealed token comes back damaged, so it cannot be opened.
    sign_in_damaged: bool = False

    async def sign_in_token(self, session_id: str, code: str) -> SealedAccessToken:
        self.sign_in_codes.append(code)
        if code != GOOD_CODE:
            message = "Supabase did not accept that code"
            raise SourceAuthError(message)
        if self.sign_in_failure is not None:
            raise self.sign_in_failure
        page = next(url for url in self.opened if url.startswith(SUPABASE_BROWSER_SIGN_IN_PAGE))
        query = parse_qs(urlsplit(page).query)
        assert query["session_id"] == [session_id]
        sealed = seal_token(query["public_key"][0], self.sign_in_token_value)
        if not self.sign_in_damaged:
            return sealed
        flipped = bytes.fromhex(sealed.ciphertext_hex)[:-1] + b"\x00"
        return replace(sealed, ciphertext_hex=flipped.hex())

    async def signups_disabled(self, project_url: str, publishable_key: SecretStr) -> bool:
        if self.unanswered_settings > 0:
            self.unanswered_settings -= 1
            message = "Supabase could not be reached"
            raise SourceUnavailableError(message)
        if publishable_key.get_secret_value() != GOOD_PUBLISHABLE:
            message = "Supabase did not accept the publishable key"
            raise SourceAuthError(message)
        return self.signups_off.pop(0) if len(self.signups_off) > 1 else self.signups_off[0]

    async def organizations(self, token: SecretStr) -> tuple[Organization, ...]:
        self.organization_reads += 1
        if self.narrow_may_list:
            _require_known(token, "the access token")
        else:
            _require_good(token, "the access token")
        return tuple(self.organization_list)

    async def projects(self, token: SecretStr) -> tuple[SupabaseProject, ...]:
        _require_known(token, "the access token")
        return tuple(self.project_list)

    async def create_project(self, token: SecretStr, request: NewProject) -> SupabaseProject:
        _require_known(token, "the access token for creating a project")
        if self.create_refusal is not None:
            message = f"Supabase refused it (status 402: {self.create_refusal})"
            raise SourceRequestRejectedError(message)
        self.created.append(request)
        project = SupabaseProject(
            NEW_PROJECT_REF, request.name, request.organization_slug, "COMING_UP"
        )
        self.project_list.append(project)
        if self.create_times_out:
            message = "Supabase could not be reached"
            raise SourceUnavailableError(message)
        return project

    async def project(self, token: SecretStr, project_ref: str) -> SupabaseProject:
        _require_known(token, "the access token")
        if self.busy_looks > 0:
            self.busy_looks -= 1
            message = "Supabase refused it (status 429: Too many requests)"
            raise SourceRequestRejectedError(message)
        found = next(item for item in self.project_list if item.ref == project_ref)
        status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        return SupabaseProject(found.ref, found.name, found.organization_slug, status)

    async def api_keys(self, project_ref: str, token: SecretStr) -> tuple[ApiKey, ...]:
        _require_good(token, "the access token for reading the API keys")
        return tuple(self.keys)

    async def create_api_key(
        self, project_ref: str, token: SecretStr, kind: ApiKeyKind, name: str
    ) -> SecretStr:
        _require_good(token, "the access token for creating an API key")
        self.created_keys.append((kind, name))
        value = GOOD_PUBLISHABLE if kind is ApiKeyKind.PUBLISHABLE else GOOD_SECRET
        return SecretStr(value)

    async def redirect_urls(self, project_ref: str, token: SecretStr) -> tuple[str, ...]:
        self._refuse_auth(token)
        return tuple(self.redirect_list)

    def _refuse_auth(self, token: SecretStr) -> None:
        _require_good(token, "the access token for the auth settings")
        if self.auth_refusal is not None:
            message = "Supabase did not accept the access token for the auth settings"
            raise self.auth_refusal(message)

    async def configure_auth(
        self, project_ref: str, token: SecretStr, settings: AuthSettings
    ) -> None:
        self._refuse_auth(token)
        self.auth_changes.append((project_ref, settings))
        if settings.redirect_urls is not None:
            self.redirect_list = list(settings.redirect_urls)
        if settings.disable_signup:
            self.signups_off = list(self.signups_after_change)

    async def applied_migrations(self, project_ref: str, token: SecretStr) -> frozenset[str]:
        _require_good(token, "the access token")
        if not self.migrations_allowed:
            message = "Supabase did not accept the access token"
            raise SourceAuthError(message)
        return frozenset(self.recorded)

    async def apply_migration(
        self, project_ref: str, token: SecretStr, name: str, sql: str
    ) -> None:
        _require_good(token, "the access token")
        if name == self.fail_on:
            message = "Supabase answered status 500"
            raise SourceUnavailableError(message)
        if self.rejections.get(name, 0) > 0:
            self.rejections[name] -= 1
            message = "Supabase refused it (status 400: version already exists)"
            raise SourceRequestRejectedError(message)
        if self.apply_forbidden:
            message = "Supabase did not accept the access token"
            raise SourceAuthError(message)
        self.applied.append(name)
        if self.admin is not None:
            self.admin.present.add(name)

    async def set_secrets(
        self, project_ref: str, token: SecretStr, secrets: Mapping[str, SecretStr]
    ) -> None:
        _require_good(token, "the access token for the function's settings")
        self.secrets.update({name: value.get_secret_value() for name, value in secrets.items()})

    async def deploy_function(
        self,
        project_ref: str,
        token: SecretStr,
        slug: str,
        files: Mapping[str, bytes],
        *,
        verify_jwt: bool,
    ) -> None:
        _require_good(token, "the access token for deploying the function")
        self.deployed.append((slug, tuple(files), verify_jwt))


def seal_token(public_key_hex: str, token: str) -> SealedAccessToken:
    """Seal a token for a sign-in's public key, as Supabase does: ECDH, then AES-256-GCM."""
    supabase_key = ec.generate_private_key(ec.SECP256R1())
    their_key = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), bytes.fromhex(public_key_hex)
    )
    shared_secret = supabase_key.exchange(ec.ECDH(), their_key)
    nonce = os.urandom(12)
    sealed = AESGCM(shared_secret).encrypt(nonce, token.encode(), None)
    public_point = supabase_key.public_key().public_bytes(
        Encoding.X962, PublicFormat.UncompressedPoint
    )
    return SealedAccessToken(
        ciphertext_hex=sealed.hex(), public_key_hex=public_point.hex(), nonce_hex=nonce.hex()
    )


def _require_known(token: SecretStr, what: str) -> None:
    """Refuse any token but the good one or the scoped one."""
    if token.get_secret_value() != NARROW_TOKEN:
        _require_good(token, what)


def _require_good(token: SecretStr, what: str) -> None:
    """Refuse any token but the good one, in Supabase's words."""
    if token.get_secret_value() == NARROW_TOKEN:
        message = f"Supabase says {what} has too little access"
        raise SourcePermissionError(message)
    if token.get_secret_value() != GOOD_TOKEN:
        message = f"Supabase did not accept {what}"
        raise SourceAuthError(message)


@dataclass
class FakeMicrosoft:
    """The mailbox sign-in."""

    signed_in: bool = False
    address: str = OWNER_EMAIL
    refuse: bool = False
    accesses: list[MicrosoftAccess] = field(default_factory=list)

    async def is_signed_in(self, access: MicrosoftAccess) -> bool:
        return self.signed_in

    async def sign_in(self, access: MicrosoftAccess, show_code: ShowCode) -> str:
        self.accesses.append(access)
        show_code("https://microsoft.example/link", "CODE-123")
        if self.refuse:
            message = "Microsoft sign-in was not completed in time - run it again"
            raise SourceAuthError(message)
        self.signed_in = True
        return self.address


@dataclass
class FakeMailbox:
    """The IMAP mailbox's live check and its encrypted password, in memory."""

    good_password: str = GOOD_APP_PASSWORD
    inbox_messages: int = 42
    sent_folder: str | None = "[Gmail]/Sent Mail"
    saved: dict[str, str] = field(default_factory=dict)
    checked: list[tuple[ImapAccount, str]] = field(default_factory=list)
    smtp_hosts: set[str] = field(default_factory=lambda: {"smtp.mail.example"})
    sending_checked: list[SmtpAccount] = field(default_factory=list)
    #: The sending server turns down even the password the inbox accepts.
    smtp_refuses: bool = False

    async def has_password(self, access: StoreAccess, username: str) -> bool:
        return username in self.saved

    async def check(
        self, account: ImapAccount, password: SecretStr, since: datetime
    ) -> MailboxSurvey:
        self.checked.append((account, password.get_secret_value()))
        if password.get_secret_value() != self.good_password:
            message = f"{account.company} refused the app password"
            raise MailboxPasswordError(message)
        return MailboxSurvey(inbox_messages=self.inbox_messages, sent_folder=self.sent_folder)

    async def check_sending(self, account: SmtpAccount, password: SecretStr) -> None:
        self.sending_checked.append(account)
        if account.host not in self.smtp_hosts:
            message = f"{account.label} could not send the summary"
            raise SourceUnavailableError(message)
        if self.smtp_refuses or password.get_secret_value() != self.good_password:
            message = f"{account.company} refused the app password for sending"
            raise MailboxPasswordError(message)

    async def save_password(self, access: StoreAccess, username: str, password: SecretStr) -> None:
        self.saved[username] = password.get_secret_value()


@dataclass
class FakeLinkedIn:
    """LinkedIn's sign-in with the owner's application, and the encrypted Client Secret.

    A sign-in with the good Client ID and Secret hands out the good key, unless
    a test lines up errors first; any other Client ID or Secret is refused.
    """

    #: Errors the next sign-ins raise, in turn, before they succeed.
    errors: list[LinkedInSignInError | SourceUnavailableError] = field(default_factory=list)
    #: The key a successful sign-in hands out.
    key: str = GOOD_LINKEDIN
    #: How many times a sign-in asks whether to keep waiting before LinkedIn answers.
    slow_answers: int = 0
    #: Whether the key exchange says when the key stops working.
    tells_expiry: bool = True
    #: What the key check answers; ``None`` when LinkedIn does not say.
    introspected: datetime | None = LINKEDIN_KEY_EXPIRES_AT
    #: Whether LinkedIn cannot be reached to read a key's expiry.
    introspection_fails: bool = False
    saved_secret: str | None = None
    #: Whether the database is down when the Client Secret is saved.
    secret_save_fails: bool = False
    #: Whether LinkedIn cannot be reached for the live check of a key.
    check_unreachable: bool = False
    sign_ins: list[LinkedInApp] = field(default_factory=list)
    introspections: list[str] = field(default_factory=list)

    async def sign_in(
        self,
        app: LinkedInApp,
        show_page: Callable[[str], None],
        keep_waiting: Callable[[], bool],
    ) -> LinkedInGrant:
        self.sign_ins.append(app)
        show_page(f"https://www.linkedin.com/oauth/v2/authorization?client_id={app.client_id}")
        for _ in range(self.slow_answers):
            if not keep_waiting():
                message = "No answer came back from LinkedIn"
                raise LinkedInSignInError(message, SignInProblem.NO_ANSWER)
        if self.errors:
            raise self.errors.pop(0)
        if not _good_app(app):
            message = "LinkedIn did not accept the Client ID or the Client Secret"
            raise LinkedInSignInError(message, SignInProblem.APP_DETAILS)
        expires = LINKEDIN_KEY_EXPIRES_AT if self.tells_expiry else None
        return LinkedInGrant(SecretStr(self.key), expires)

    async def expiry_of(self, app: LinkedInApp, token: SecretStr) -> datetime | None:
        self.introspections.append(token.get_secret_value())
        if self.introspection_fails:
            message = "LinkedIn could not be reached"
            raise SourceUnavailableError(message)
        if not _good_app(app):
            message = "LinkedIn did not accept the Client ID or the Client Secret"
            raise LinkedInSignInError(message, SignInProblem.APP_DETAILS)
        return self.introspected

    async def saved_client_secret(self, access: StoreAccess) -> SecretStr | None:
        return SecretStr(self.saved_secret) if self.saved_secret else None

    async def save_client_secret(self, access: StoreAccess, secret: SecretStr) -> None:
        if self.secret_save_fails:
            message = "database request failed on app_secrets.bulk_upsert"
            raise DatabaseUnavailableError(message)
        self.saved_secret = secret.get_secret_value()


def _good_app(app: LinkedInApp) -> bool:
    """Whether the fake LinkedIn knows this Client ID and Secret."""
    secret = app.client_secret.get_secret_value()
    return app.client_id == GOOD_CLIENT_ID and secret == GOOD_CLIENT_SECRET


@dataclass
class FakeChoices:
    """Where the category choice is kept, in memory."""

    preset: str | None = None
    saved: list[Choice] = field(default_factory=list)
    archived: tuple[str, ...] = ()
    renamed: tuple[Category, ...] = ()
    profile_file_wins: bool = False

    def chosen_preset(self) -> str | None:
        return self.preset

    def save(self, choice: Choice) -> SavedChoice:
        self.preset = choice.preset
        self.saved.append(choice)
        changes = CategoryChanges(
            saved=tuple(category.key for category in choice.categories),
            archived=self.archived,
            deleted=(),
            renamed=self.renamed,
        )
        effect = Effect(
            applied=ApplyReport(stages=6, suggestions=len(choice.profile.suggestions())),
            guide=Path("docs/assessment-guide.md"),
        )
        return SavedChoice(changes=changes, effect=effect, profile_file_wins=self.profile_file_wins)


#: The schedule every test starts from, whatever time the owner chose for the
#: repository's own workflow file.
TEST_SCHEDULE = Schedule(time(7, 0), "UTC")


class FakeWorkflow:
    """The workflow file, in memory; starts as the real one at the test schedule."""

    def __init__(self, text: str | None = None) -> None:
        if text is None:
            text = write_schedule(WORKFLOW_FILE.read_text(encoding="utf-8"), TEST_SCHEDULE)
        self.text = text
        self.writes = 0

    def read(self) -> str:
        return self.text

    def write(self, text: str) -> None:
        self.text = text
        self.writes += 1


@dataclass
class FakeGit:
    """git, recording what it was asked to commit and push."""

    origin: str | None = "https://github.com/you/threadline.git"
    remotes: dict[str, str] = field(default_factory=dict)
    committed: list[tuple[str, str]] = field(default_factory=list)
    pushed: list[tuple[str, str]] = field(default_factory=list)
    #: Whether the workflow file differs from the last commit, and whether a
    #: commit that changed it is not on GitHub yet.
    uncommitted: bool = False
    unpushed: bool = False
    #: Pushes of what was already committed.
    plain_pushes: int = 0
    #: What a commit or a push fails with, when set.
    failure: str | None = None

    def origin_url(self) -> str | None:
        return self.origin

    def has_uncommitted(self, path: str) -> bool:
        return self.uncommitted

    def has_unpushed(self, path: str) -> bool:
        return self.unpushed

    def push(self) -> None:
        self._fail_if_asked()
        self.plain_pushes += 1

    def rename_origin(self, new_name: str) -> None:
        assert self.origin is not None
        self.remotes[new_name] = self.origin
        self.origin = None

    def commit(self, path: str, message: str) -> None:
        self._fail_if_asked()
        self.committed.append((path, message))

    def commit_and_push(self, path: str, message: str) -> None:
        self._fail_if_asked()
        self.pushed.append((path, message))

    def _fail_if_asked(self) -> None:
        if self.failure is not None:
            raise SourceUnavailableError(self.failure)


@dataclass
class FakeGitHub:
    """The GitHub CLI, keeping what it was given in memory."""

    signed_in: bool = True
    is_installed: bool = True
    name: str | None = "you/threadline"
    private: bool = True
    admin: bool = True
    secrets: dict[str, str] = field(default_factory=dict)
    variables: dict[str, str] = field(default_factory=dict)
    created: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    listable: bool = True
    #: Repositories whose workflow was switched on, and the runs started as (repository, mode).
    enabled: list[str] = field(default_factory=list)
    started: list[tuple[str, str]] = field(default_factory=list)
    enable_refused: bool = False
    start_refused: bool = False
    #: Whether GitHub confirms a file's build provenance, and each file it was asked about.
    attestation_ok: bool = True
    attested: list[tuple[bytes, str, str, str]] = field(default_factory=list)
    #: Repositories whose workflow was switched off, and whether GitHub refuses that.
    disabled: list[str] = field(default_factory=list)
    disable_refused: bool = False
    #: Whether GitHub refuses to save a secret or a variable.
    save_refused: bool = False
    #: The workflow's runs, newest last; each run the set-up starts is added.
    runs: list[WorkflowRun] = field(default_factory=list)
    #: When GitHub makes each run the set-up starts.
    run_created_at: datetime = datetime(2026, 9, 29, 7, 0, tzinfo=UTC)
    #: Runs GitHub shows only once the set-up has started its own, such as a
    #: refresh pressed a moment later.
    runs_started_next: list[WorkflowRun] = field(default_factory=list)
    #: The (status, conclusion) a started run is seen in at each look, in turn;
    #: the last one repeats.
    run_states: list[tuple[str, str]] = field(default_factory=lambda: [("in_progress", "")])
    #: The notes titled "Why Claude stopped" that a run's job leaves.
    notes: tuple[str, ...] = ()
    #: Whether GitHub can say how runs are going, and each run looked at.
    runs_readable: bool = True
    looked_at: list[int] = field(default_factory=list)

    def installed(self) -> bool:
        return self.is_installed

    def ready(self) -> bool:
        return self.is_installed and self.signed_in

    def verify_attestation(
        self, archive: bytes, repository: str, signer_workflow: str, source_ref: str
    ) -> bool:
        self.attested.append((archive, repository, signer_workflow, source_ref))
        return self.attestation_ok

    def repository(self) -> GitHubRepository | None:
        if self.name is None:
            return None
        return GitHubRepository(self.name, private=self.private, admin=self.admin)

    def set_secret(self, repository: str, name: str, value: SecretStr) -> None:
        self._refuse_if_asked(name)
        self.secrets[name] = value.get_secret_value()

    def set_variable(self, repository: str, name: str, value: str) -> None:
        self._refuse_if_asked(name)
        self.variables[name] = value

    def _refuse_if_asked(self, name: str) -> None:
        if self.save_refused:
            message = f"the GitHub CLI could not save {name}"
            raise SourceUnavailableError(message)

    def secret_names(self, repository: str) -> frozenset[str]:
        if not self.listable:
            message = "the GitHub CLI could not list the repository's secrets"
            raise SourceUnavailableError(message)
        return frozenset(self.secrets)

    def variable_names(self, repository: str) -> frozenset[str]:
        return frozenset(self.variables)

    def delete_secret(self, repository: str, name: str) -> None:
        del self.secrets[name]
        self.deleted.append(name)

    def delete_variable(self, repository: str, name: str) -> None:
        del self.variables[name]
        self.deleted.append(name)

    def create_private_copy(self, name: str) -> None:
        self.created.append(name)
        self.name = f"you/{name}"
        self.private = True
        self.admin = True

    def enable_workflow(self, repository: str) -> None:
        if self.enable_refused:
            message = (
                f"GitHub would not switch on the workflow in {repository} - open "
                f"https://github.com/{repository}/actions/workflows/threadline-run.yml, "
                "click 'Enable workflow' if it shows, then 'Run workflow'"
            )
            raise WorkflowNotEnabledError(message)
        self.enabled.append(repository)

    def start_workflow(self, repository: str, mode: WorkflowMode) -> None:
        if self.start_refused:
            message = (
                "GitHub did not start the run - open "
                f"https://github.com/{repository}/actions/workflows/threadline-run.yml "
                "and click 'Run workflow' yourself, keeping mode daily"
            )
            raise WorkflowNotStartedError(message)
        self.started.append((repository, mode.value))
        run_id = 1000 + len(self.runs)
        url = f"https://github.com/{repository}/actions/runs/{run_id}"
        title = DAILY_RUN_TITLE if mode == WorkflowMode.DAILY else REFRESH_RUN_TITLE
        run = WorkflowRun(
            id=run_id,
            status="queued",
            conclusion="",
            url=url,
            title=title,
            created_at=self.run_created_at,
        )
        self.runs.append(run)
        self.runs.extend(self.runs_started_next)

    def recent_runs(self, repository: str) -> tuple[WorkflowRun, ...]:
        self._refuse_unless_readable()
        return tuple(reversed(self.runs))

    def workflow_run(self, repository: str, run_id: int) -> WorkflowRun:
        self._refuse_unless_readable()
        self.looked_at.append(run_id)
        states = self.run_states
        status, conclusion = states.pop(0) if len(states) > 1 else states[0]
        run = next(run for run in self.runs if run.id == run_id)
        return replace(run, status=status, conclusion=conclusion)

    def run_notes(self, repository: str, run_id: int, title: str) -> tuple[str, ...]:
        self._refuse_unless_readable()
        return self.notes if title == "Why Claude stopped" else ()

    def _refuse_unless_readable(self) -> None:
        if not self.runs_readable:
            message = "GitHub could not say how the run is going"
            raise SourceUnavailableError(message)

    def disable_workflow(self, repository: str) -> None:
        if self.disable_refused:
            message = f"GitHub would not switch the daily run off - open the page of {repository}"
            raise SourceUnavailableError(message)
        self.disabled.append(repository)


@dataclass
class FakeGitHubApi:
    """GitHub's REST API: knows one good token and the workflow's state."""

    state: str = "active"
    reads: list[str] = field(default_factory=list)

    async def workflow_state(self, repository: str, token: SecretStr) -> str:
        self.reads.append(repository)
        if token.get_secret_value() != GOOD_GITHUB_TOKEN:
            message = "GitHub did not accept the token - it is incomplete, wrong or expired"
            raise SourceAuthError(message)
        return self.state


@dataclass
class FakeNetlify:
    """Netlify's API: one good token, sites in memory, deploy states in turn."""

    taken: set[str] = field(default_factory=set)
    sites: dict[str, NetlifySite] = field(default_factory=dict)
    #: The states the deploy goes through, in turn; the last one repeats.
    states: list[str] = field(default_factory=lambda: ["ready"])
    error: str | None = None
    #: Refuses every new site with this error, as Netlify does for a reason other than the name.
    create_refusal: Exception | None = None
    created: list[str] = field(default_factory=list)
    deployed: list[tuple[str, bytes]] = field(default_factory=list)
    polls: int = 0

    async def check_token(self, token: SecretStr) -> None:
        if token.get_secret_value() != GOOD_NETLIFY_TOKEN:
            message = "Netlify did not accept the token - it is incomplete, wrong or expired"
            raise SourceAuthError(message)

    async def create_site(self, token: SecretStr, name: str) -> NetlifySite:
        await self.check_token(token)
        self.created.append(name)
        if self.create_refusal is not None:
            raise self.create_refusal
        if name in self.taken:
            message = f"Netlify already has a site called {name}"
            raise SiteNameTakenError(message)
        site = NetlifySite(
            id=f"site-{len(self.sites) + 1}", name=name, address=f"https://{name}.netlify.app"
        )
        self.sites[site.id] = site
        return site

    async def find_site(self, token: SecretStr, site_id: str) -> NetlifySite | None:
        await self.check_token(token)
        return self.sites.get(site_id)

    async def deploy_zip(self, token: SecretStr, site_id: str, archive: bytes) -> NetlifyDeploy:
        await self.check_token(token)
        self.deployed.append((site_id, archive))
        return self._deploy()

    async def deploy_state(self, token: SecretStr, deploy_id: str) -> NetlifyDeploy:
        self.polls += 1
        return self._deploy()

    def _deploy(self) -> NetlifyDeploy:
        state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        return NetlifyDeploy(id="deploy-1", state=state, error=self.error)


@dataclass
class FakeLocalBuild:
    """Node.js on this computer: absent unless a test says otherwise."""

    present: bool = False
    files: dict[str, bytes] = field(default_factory=lambda: dict(BUILT_SITE))
    builds: int = 0

    def available(self) -> bool:
        return self.present

    def build(self) -> dict[str, bytes]:
        self.builds += 1
        return self.files


@dataclass
class FakeClaudeKeyMaker:
    """``claude setup-token``: out of reach unless a test says otherwise, as on Windows."""

    state_now: ClaudeCodeState = ClaudeCodeState.UNSUPPORTED
    #: What its screen shows, the key included.
    screen: str = ""
    exit_code: int = 0
    columns: int = 1000
    #: Raised instead of a screen, when set.
    error: ClaudeKeyNotMadeError | None = None
    runs: int = 0

    def state(self) -> ClaudeCodeState:
        return self.state_now

    def make_key(self) -> ClaudeKeyScreen:
        self.runs += 1
        if self.error is not None:
            raise self.error
        return ClaudeKeyScreen(
            text=SecretStr(self.screen), columns=self.columns, exit_code=self.exit_code
        )


@dataclass
class World:
    """Everything a step test needs."""

    io: ScriptedIO
    env: MemoryEnv
    admin: FakeAdmin
    platform: FakePlatform
    microsoft: FakeMicrosoft
    statuses: dict[str, int]
    linkedin_calls: list[str]
    linkedin: FakeLinkedIn = field(default_factory=FakeLinkedIn)
    choices: FakeChoices = field(default_factory=FakeChoices)
    mailbox: FakeMailbox = field(default_factory=FakeMailbox)
    workflow: FakeWorkflow = field(default_factory=FakeWorkflow)
    git: FakeGit = field(default_factory=FakeGit)
    github: FakeGitHub = field(default_factory=FakeGitHub)
    waits: list[float] = field(default_factory=list)
    local_zone: str | None = "Europe/Paris"
    github_api: FakeGitHubApi = field(default_factory=FakeGitHubApi)
    #: What the "Refresh now" function answers each empty POST, in turn; the last repeats.
    function_statuses: list[int] = field(default_factory=lambda: [404])
    posts: list[str] = field(default_factory=list)
    netlify: FakeNetlify = field(default_factory=FakeNetlify)
    local_build: FakeLocalBuild = field(default_factory=FakeLocalBuild)
    #: What each address downloads; any other address is refused.
    downloads: dict[str, bytes] = field(default_factory=release_downloads)
    #: What each address answers when opened, in turn; the last one repeats.
    pages: dict[str, list[WebPage]] = field(default_factory=dict)
    #: The random ends of new site names, in turn.
    suffixes: list[str] = field(default_factory=lambda: ["abc123", "def456", "ghi789"])
    claude: FakeClaudeKeyMaker = field(default_factory=FakeClaudeKeyMaker)

    def context(self) -> SetupContext:
        async def check_linkedin(token: SecretStr) -> None:
            self.linkedin_calls.append(token.get_secret_value())
            if self.linkedin.check_unreachable:
                message = "LinkedIn could not be reached"
                raise SourceUnavailableError(message)
            if token.get_secret_value() != GOOD_LINKEDIN:
                message = "LinkedIn did not accept the key - it is wrong or has expired"
                raise SourceAuthError(message)

        async def status_of(url: str) -> int:
            return self.statuses.get(url, 404)

        async def status_of_post(url: str) -> int:
            self.posts.append(url)
            statuses = self.function_statuses
            return statuses.pop(0) if len(statuses) > 1 else statuses[0]

        async def sleep(seconds: float) -> None:
            self.waits.append(seconds)

        async def download(url: str, max_bytes: int) -> bytes:
            if url not in self.downloads:
                message = f"{url} answered status 404"
                raise SourceRequestRejectedError(message)
            return self.downloads[url]

        async def page_of(url: str) -> WebPage:
            answers = self.pages.get(url, [WebPage(status=404, is_html=False)])
            return answers.pop(0) if len(answers) > 1 else answers[0]

        def admin_for(url: str, key: SecretStr) -> FakeAdmin:
            self.admin.key_ok = key.get_secret_value() == GOOD_SECRET
            return self.admin

        gateways = SetupGateways(
            admin_for=admin_for,
            choices_for=lambda url, key: self.choices,
            platform=self.platform,
            microsoft=self.microsoft,
            mailbox=self.mailbox,
            check_linkedin=check_linkedin,
            linkedin=self.linkedin,
            status_of=status_of,
            status_of_post=status_of_post,
            make_encryption_key=lambda: "generated-key",
            migrations=migration_files(),
            clock=FixedClock(datetime(2026, 9, 29, 7, 0, tzinfo=UTC)),
            workflow=self.workflow,
            git=self.git,
            github=self.github,
            sleep=sleep,
            local_time_zone=lambda: self.local_zone,
            github_api=self.github_api,
            refresh_function=lambda: {
                "index.ts": b"serve()",
                "refresh.ts": b"export {}",
                "daily.ts": b"export {}",
            },
            make_daily_start_key=lambda: DAILY_START_KEY,
            netlify=self.netlify,
            download=download,
            local_build=self.local_build,
            page_of=page_of,
            site_name_suffix=lambda: self.suffixes.pop(0),
            claude_key_maker=self.claude,
        )
        return SetupContext(io=self.io, env=self.env, gateways=gateways)


def migration_files() -> tuple[MigrationFile, ...]:
    """The known migrations, pointing at files that are never read unless applied."""
    return tuple(
        MigrationFile(name=name, path=Path(__file__).parent / "fixtures" / "migration.sql")
        for name in KNOWN_MIGRATIONS
    )


def configured_env() -> dict[str, str]:
    """A ``.env`` where the Supabase and encryption steps are finished."""
    return {
        "SUPABASE_URL": PROJECT_URL,
        "SUPABASE_ANON_KEY": GOOD_PUBLISHABLE,
        "SUPABASE_SERVICE_ROLE_KEY": GOOD_SECRET,
        "TOKEN_ENCRYPTION_KEY": "saved-key",
    }


def make_world(
    answers: list[str | bool] | None = None,
    env: dict[str, str] | None = None,
    *,
    clipboard: bool = True,
) -> World:
    """Build a world with every migration present and nobody signed in."""
    admin = FakeAdmin()
    io = ScriptedIO(answers, clipboard=clipboard)
    return World(
        io=io,
        env=MemoryEnv(env),
        admin=admin,
        platform=FakePlatform(admin=admin, opened=io.opened),
        microsoft=FakeMicrosoft(),
        statuses={},
        linkedin_calls=[],
    )
