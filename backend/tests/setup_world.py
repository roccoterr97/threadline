"""Fakes for the set-up: a scripted conversation, an in-memory ``.env`` and services.

Nothing here touches a terminal, a file outside the test folder or the network.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from pydantic import SecretStr

from tracker.infrastructure.github_cli import GitHubRepository
from tracker.infrastructure.imap.connection import StoreAccess
from tracker.infrastructure.imap.reader import MailboxSurvey
from tracker.infrastructure.imap.session import ImapAccount
from tracker.infrastructure.microsoft.connection import MicrosoftAccess, ShowCode
from tracker.infrastructure.smtp import SmtpAccount
from tracker.services.database_structure import KNOWN_MIGRATIONS, MigrationFile
from tracker.services.profile.applier import ApplyReport, CategoryChanges
from tracker.services.profile.choice import Choice, Effect, SavedChoice
from tracker.services.setup.context import SetupContext
from tracker.services.setup.ports import SetupGateways
from tracker.shared.clock import FixedClock
from tracker.shared.constants.github import WORKFLOW_FILE
from tracker.shared.errors import (
    MailboxPasswordError,
    SourceAuthError,
    SourceRequestRejectedError,
    SourceUnavailableError,
)

PROJECT_URL = "https://abcdefghijklmnop.supabase.co"
PROJECT_REF = "abcdefghijklmnop"
GOOD_PUBLISHABLE = "sb_publishable_good"
GOOD_SECRET = "sb_secret_good"
GOOD_TOKEN = "sbp_good"
GOOD_LINKEDIN = "linkedin-good"
OWNER_EMAIL = "you@example.com"
GOOD_APP_PASSWORD = "wxyzwxyzwxyzwxyz"
GOOD_GITHUB_TOKEN = "github_pat_good"


class ScriptedIO:
    """Answers questions from a script and records everything said."""

    def __init__(self, answers: list[str | bool] | None = None, *, clipboard: bool = True) -> None:
        self.answers: deque[str | bool] = deque(answers or [])
        self.said: list[str] = []
        self.opened: list[str] = []
        self.copied: list[str] = []
        self.secret_prompts: list[str] = []
        self.clipboard = clipboard
        self.on_pause: Callable[[str], None] | None = None

    def say(self, text: str) -> None:
        self.said.append(text)

    def ask(self, prompt: str, *, default: str | None = None) -> str:
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

    def has_columns(self, table: str, columns: str) -> bool:
        return self._marker_present(table, columns)

    def accepts_value(self, table: str, column: str, value: str) -> bool:
        if self._still_text(table, column):
            return True
        return self._marker_present(table, f"{column}={value}")

    def is_enum_column(self, table: str, column: str) -> bool:
        return SCHEMA_MIGRATION in self.present and not self._still_text(table, column)

    def _still_text(self, table: str, column: str) -> bool:
        migration = TEXT_UNTIL.get((table, column))
        return migration is not None and migration not in self.present

    def check_service_key(self) -> None:
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

    def create_confirmed_user(self, email: str) -> str | None:
        if email in self.users:
            return None
        self.users[email] = f"user-{len(self.users) + 1}"
        return self.users[email]

    def _marker_present(self, table: str, detail: str) -> bool:
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
    return f"{getattr(marker, 'column', '')}={getattr(marker, 'value', '')}" == detail


@dataclass
class FakePlatform:
    """Supabase's Management API and public auth settings."""

    signups_off: list[bool] = field(default_factory=lambda: [True])
    recorded: set[str] = field(default_factory=set)
    applied: list[str] = field(default_factory=list)
    fail_on: str | None = None
    rejections: dict[str, int] = field(default_factory=dict)
    admin: FakeAdmin | None = None
    secrets: dict[str, str] = field(default_factory=dict)
    deployed: list[tuple[str, tuple[str, ...], bool]] = field(default_factory=list)

    async def signups_disabled(self, project_url: str, publishable_key: SecretStr) -> bool:
        if publishable_key.get_secret_value() != GOOD_PUBLISHABLE:
            message = "Supabase did not accept the publishable key"
            raise SourceAuthError(message)
        return self.signups_off.pop(0) if len(self.signups_off) > 1 else self.signups_off[0]

    async def applied_migrations(self, project_ref: str, token: SecretStr) -> frozenset[str]:
        if token.get_secret_value() != GOOD_TOKEN:
            message = "Supabase did not accept the access token"
            raise SourceAuthError(message)
        return frozenset(self.recorded)

    async def apply_migration(
        self, project_ref: str, token: SecretStr, name: str, sql: str
    ) -> None:
        if name == self.fail_on:
            message = "Supabase answered status 500"
            raise SourceUnavailableError(message)
        if self.rejections.get(name, 0) > 0:
            self.rejections[name] -= 1
            message = "Supabase refused it (status 400: version already exists)"
            raise SourceRequestRejectedError(message)
        self.applied.append(name)
        if self.admin is not None:
            self.admin.present.add(name)

    async def set_secrets(
        self, project_ref: str, token: SecretStr, secrets: Mapping[str, SecretStr]
    ) -> None:
        if token.get_secret_value() != GOOD_TOKEN:
            message = "Supabase did not accept the access token for the function's settings"
            raise SourceAuthError(message)
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
        self.deployed.append((slug, tuple(files), verify_jwt))


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
        if password.get_secret_value() != self.good_password:
            message = f"{account.company} refused the app password for sending"
            raise MailboxPasswordError(message)

    async def save_password(self, access: StoreAccess, username: str, password: SecretStr) -> None:
        self.saved[username] = password.get_secret_value()


@dataclass
class FakeChoices:
    """Where the category choice is kept, in memory."""

    preset: str | None = None
    saved: list[Choice] = field(default_factory=list)
    archived: tuple[str, ...] = ()
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
        )
        effect = Effect(
            applied=ApplyReport(stages=6, suggestions=len(choice.profile.suggestions())),
            guide=Path("docs/assessment-guide.md"),
        )
        return SavedChoice(changes=changes, effect=effect, profile_file_wins=self.profile_file_wins)


class FakeWorkflow:
    """The workflow file, in memory; starts as the real one."""

    def __init__(self, text: str | None = None) -> None:
        self.text = WORKFLOW_FILE.read_text(encoding="utf-8") if text is None else text
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

    def origin_url(self) -> str | None:
        return self.origin

    def rename_origin(self, new_name: str) -> None:
        assert self.origin is not None
        self.remotes[new_name] = self.origin
        self.origin = None

    def commit(self, path: str, message: str) -> None:
        self.committed.append((path, message))

    def commit_and_push(self, path: str, message: str) -> None:
        self.pushed.append((path, message))


@dataclass
class FakeGitHub:
    """The GitHub CLI, keeping what it was given in memory."""

    signed_in: bool = True
    name: str | None = "you/threadline"
    private: bool = True
    admin: bool = True
    secrets: dict[str, str] = field(default_factory=dict)
    variables: dict[str, str] = field(default_factory=dict)
    created: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    listable: bool = True

    def ready(self) -> bool:
        return self.signed_in

    def repository(self) -> GitHubRepository | None:
        if self.name is None:
            return None
        return GitHubRepository(self.name, private=self.private, admin=self.admin)

    def set_secret(self, repository: str, name: str, value: SecretStr) -> None:
        self.secrets[name] = value.get_secret_value()

    def set_variable(self, repository: str, name: str, value: str) -> None:
        self.variables[name] = value

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
class World:
    """Everything a step test needs."""

    io: ScriptedIO
    env: MemoryEnv
    admin: FakeAdmin
    platform: FakePlatform
    microsoft: FakeMicrosoft
    statuses: dict[str, int]
    linkedin_calls: list[str]
    choices: FakeChoices = field(default_factory=FakeChoices)
    mailbox: FakeMailbox = field(default_factory=FakeMailbox)
    workflow: FakeWorkflow = field(default_factory=FakeWorkflow)
    git: FakeGit = field(default_factory=FakeGit)
    github: FakeGitHub = field(default_factory=FakeGitHub)
    waits: list[float] = field(default_factory=list)
    local_zone: str = "Europe/Paris"
    github_api: FakeGitHubApi = field(default_factory=FakeGitHubApi)
    #: What the "Refresh now" function answers each empty POST, in turn; the last repeats.
    function_statuses: list[int] = field(default_factory=lambda: [404])
    posts: list[str] = field(default_factory=list)

    def context(self) -> SetupContext:
        async def check_linkedin(token: SecretStr) -> None:
            self.linkedin_calls.append(token.get_secret_value())
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
            refresh_function=lambda: {"index.ts": b"serve()", "refresh.ts": b"export {}"},
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
    return World(
        io=ScriptedIO(answers, clipboard=clipboard),
        env=MemoryEnv(env),
        admin=admin,
        platform=FakePlatform(admin=admin),
        microsoft=FakeMicrosoft(),
        statuses={},
        linkedin_calls=[],
    )
