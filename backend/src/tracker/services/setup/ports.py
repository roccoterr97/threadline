"""What the set-up needs from the outside world, as small interfaces.

Every step talks to the terminal, the ``.env`` file and the services only
through these, so each step is tested without a terminal or a network.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, time
from typing import Protocol

from pydantic import SecretStr

from tracker.domain.daily_start import DailyStartStatus
from tracker.domain.linkedin_sign_in import LinkedInApp, LinkedInGrant
from tracker.domain.supabase import (
    ApiKey,
    ApiKeyKind,
    AuthSettings,
    NewProject,
    Organization,
    SealedAccessToken,
    SupabaseProject,
)
from tracker.infrastructure.claude_setup_token import (
    ClaudeCodeState,
    ClaudeKeyListener,
    ClaudeKeyScreen,
)
from tracker.infrastructure.github_cli import GitHubRepository, WorkflowRun
from tracker.infrastructure.imap.connection import StoreAccess
from tracker.infrastructure.imap.reader import MailboxSurvey
from tracker.infrastructure.imap.session import ImapAccount
from tracker.infrastructure.microsoft.connection import MicrosoftAccess, ShowCode
from tracker.infrastructure.netlify_api import NetlifyDeploy, NetlifySite
from tracker.infrastructure.smtp import SmtpAccount
from tracker.infrastructure.web_probe import WebPage
from tracker.services.database_structure import MigrationFile, StructureProbe
from tracker.services.profile.choice import Choice, SavedChoice
from tracker.shared.clock import Clock
from tracker.shared.constants.github import WorkflowMode

__all__ = [
    "ApiKey",
    "ApiKeyKind",
    "AuthSettings",
    "ChoiceStore",
    "ClaudeCodeState",
    "ClaudeKeyListener",
    "ClaudeKeyMakerPort",
    "ClaudeKeyScreen",
    "EnvStore",
    "GitHubApiPort",
    "GitHubPort",
    "GitPort",
    "LinkedInPort",
    "MailboxPort",
    "MicrosoftPort",
    "NewProject",
    "Organization",
    "PlatformPort",
    "SetupGateways",
    "SetupIO",
    "SupabaseAdminPort",
    "SupabaseProject",
    "TextFilePort",
]


class SetupIO(Protocol):
    """The conversation with the person running the set-up."""

    def say(self, text: str) -> None:
        """Show one line."""
        ...

    def ask(self, prompt: str, *, default: str | None = None, exact: bool = False) -> str:
        """Ask for a value that may be shown on screen.

        Where a suggestion is offered, "y", "yes" or "ok" keep it, as people
        type those out of habit from the yes/no questions. ``exact`` turns that
        off for an answer such as a name, where "y" could be meant as typed.
        """
        ...

    def ask_secret(self, prompt: str) -> str:
        """Ask for a value without showing what is typed."""
        ...

    def confirm(self, prompt: str, *, default: bool) -> bool:
        """Ask a yes/no question."""
        ...

    def pause(self, prompt: str) -> None:
        """Wait until the person presses Enter."""
        ...

    def open_page(self, url: str) -> None:
        """Open a page in the browser; never fails when there is no browser."""
        ...

    def copy(self, value: str) -> bool:
        """Put a value on the clipboard; ``False`` when there is no clipboard."""
        ...


class EnvStore(Protocol):
    """The ``.env`` file."""

    def get(self, name: str) -> str | None:
        """Return a value, or ``None`` when it is absent or empty."""
        ...

    def set(self, name: str, value: str) -> None:
        """Write a value, replacing the line that holds it."""
        ...

    def names(self) -> tuple[str, ...]:
        """Return the names that hold a value, in file order."""
        ...


class SupabaseAdminPort(StructureProbe, Protocol):
    """Service-key work on the project."""

    def check_service_key(self) -> None:
        """Make one call only the secret key may make."""
        ...

    def owner_ids(self) -> tuple[str, ...]:
        """List the logins recorded as the dashboard owner."""
        ...

    def add_owner(self, user_id: str) -> None:
        """Record a login as the dashboard owner."""
        ...

    def find_user_id(self, email: str) -> str | None:
        """Find a login by address."""
        ...

    def user_email(self, user_id: str) -> str | None:
        """Read the address a login signs in with."""
        ...

    def create_confirmed_user(self, email: str) -> str | None:
        """Create a login; ``None`` when it already existed."""
        ...

    def save_daily_schedule(self, run_at: time, time_zone: str) -> None:
        """Write the daily time and its zone into the settings row."""
        ...

    def save_daily_start(self, function_url: str, key: SecretStr) -> None:
        """Save the timer's address and key, and make sure the timer exists."""
        ...

    def daily_start_status(self) -> DailyStartStatus:
        """Read whether the on-time morning start is switched on."""
        ...


class PlatformPort(Protocol):
    """Supabase's Management API and the auth server's public settings."""

    async def signups_disabled(self, project_url: str, publishable_key: SecretStr) -> bool:
        """Read whether strangers are prevented from creating a login."""
        ...

    async def sign_in_token(self, session_id: str, code: str) -> SealedAccessToken:
        """Collect the access token a browser sign-in made, still sealed for this computer."""
        ...

    async def organizations(self, token: SecretStr) -> tuple[Organization, ...]:
        """List the organizations the token's owner belongs to; proves the token."""
        ...

    async def account_email(self, token: SecretStr) -> str | None:
        """Read the Supabase account's own address; ``None`` when Supabase does not say."""
        ...

    async def projects(self, token: SecretStr) -> tuple[SupabaseProject, ...]:
        """List every project the token can see."""
        ...

    async def create_project(self, token: SecretStr, request: NewProject) -> SupabaseProject:
        """Create a project; it comes back still being set up."""
        ...

    async def project(self, token: SecretStr, project_ref: str) -> SupabaseProject:
        """Read one project, with its current status."""
        ...

    async def api_keys(self, project_ref: str, token: SecretStr) -> tuple[ApiKey, ...]:
        """List a project's API keys, revealed."""
        ...

    async def create_api_key(
        self, project_ref: str, token: SecretStr, kind: ApiKeyKind, name: str
    ) -> SecretStr:
        """Create one API key and return it."""
        ...

    async def configure_auth(
        self, project_ref: str, token: SecretStr, settings: AuthSettings
    ) -> None:
        """Change a project's auth settings; only the fields that are set are sent."""
        ...

    async def redirect_urls(self, project_ref: str, token: SecretStr) -> tuple[str, ...]:
        """Read the addresses a login link may land on."""
        ...

    async def applied_migrations(self, project_ref: str, token: SecretStr) -> frozenset[str]:
        """List the migrations Supabase has recorded as applied."""
        ...

    async def apply_migration(
        self, project_ref: str, token: SecretStr, name: str, sql: str
    ) -> None:
        """Run one migration file."""
        ...

    async def set_secrets(
        self, project_ref: str, token: SecretStr, secrets: Mapping[str, SecretStr]
    ) -> None:
        """Save Edge Function settings, replacing any with the same name."""
        ...

    async def deploy_function(
        self,
        project_ref: str,
        token: SecretStr,
        slug: str,
        files: Mapping[str, bytes],
        *,
        verify_jwt: bool,
    ) -> None:
        """Deploy an Edge Function from its files; the first one is the entry point."""
        ...


class MicrosoftPort(Protocol):
    """Signing in to the mailbox and calendar."""

    async def is_signed_in(self, access: MicrosoftAccess) -> bool:
        """Tell whether a key is stored already."""
        ...

    async def sign_in(self, access: MicrosoftAccess, show_code: ShowCode) -> str:
        """Run the one-time-code sign-in and return the signed-in address."""
        ...


class MailboxPort(Protocol):
    """Checking and keeping a standard (IMAP) mailbox's app password."""

    async def has_password(self, access: StoreAccess, username: str) -> bool:
        """Tell whether an app password is stored for a mailbox."""
        ...

    async def check(
        self, account: ImapAccount, password: SecretStr, since: datetime
    ) -> MailboxSurvey:
        """Sign in read-only and count the inbox's messages since a moment."""
        ...

    async def check_sending(self, account: SmtpAccount, password: SecretStr) -> None:
        """Sign in to the summary's sending server, then leave without sending."""
        ...

    async def save_password(self, access: StoreAccess, username: str, password: SecretStr) -> None:
        """Store an app password, encrypted."""
        ...


class LinkedInPort(Protocol):
    """Making the LinkedIn key with the owner's own application, and keeping its secret."""

    async def sign_in(
        self,
        app: LinkedInApp,
        show_page: Callable[[str], None],
        keep_waiting: Callable[[], bool],
    ) -> LinkedInGrant:
        """Open LinkedIn's consent page, wait for the owner's "Allow" and return the key."""
        ...

    async def expiry_of(self, app: LinkedInApp, token: SecretStr) -> datetime | None:
        """Ask LinkedIn when a key stops working; ``None`` when it does not say."""
        ...

    async def saved_client_secret(self, access: StoreAccess) -> SecretStr | None:
        """Read the application's Client Secret from the encrypted store."""
        ...

    async def save_client_secret(self, access: StoreAccess, secret: SecretStr) -> None:
        """Keep the application's Client Secret, encrypted."""
        ...


class ChoiceStore(Protocol):
    """Where the owner's category choice is kept."""

    def chosen_preset(self) -> str | None:
        """Return the preset the owner chose, or ``None`` when none was chosen yet."""
        ...

    def save(self, choice: Choice) -> SavedChoice:
        """Save the choice and put the profile into effect."""
        ...


class GitHubPort(Protocol):
    """The GitHub CLI: the repository and its Actions secrets and variables."""

    def installed(self) -> bool:
        """Tell whether the CLI is on this computer, signed in or not."""
        ...

    def ready(self) -> bool:
        """Tell whether the CLI is installed and signed in."""
        ...

    def repository(self) -> GitHubRepository | None:
        """Describe the repository ``origin`` points at, or ``None`` when unknown."""
        ...

    def verify_attestation(
        self, archive: bytes, repository: str, signer_workflow: str, source_ref: str
    ) -> bool:
        """Tell whether the file's signed build provenance names that workflow and ref."""
        ...

    def set_secret(self, repository: str, name: str, value: SecretStr) -> None:
        """Save one secret, its value never shown or passed as an argument."""
        ...

    def set_variable(self, repository: str, name: str, value: str) -> None:
        """Save one variable."""
        ...

    def secret_names(self, repository: str) -> frozenset[str]:
        """List the names of the repository's secrets."""
        ...

    def variable_names(self, repository: str) -> frozenset[str]:
        """List the names of the repository's variables."""
        ...

    def delete_secret(self, repository: str, name: str) -> None:
        """Delete one secret."""
        ...

    def delete_variable(self, repository: str, name: str) -> None:
        """Delete one variable."""
        ...

    def create_private_copy(self, name: str) -> None:
        """Create a private repository from this folder, link it as ``origin`` and push."""
        ...

    def enable_workflow(self, repository: str) -> None:
        """Make sure Actions may run in the repository and the Threadline workflow is active."""
        ...

    def start_workflow(self, repository: str, mode: WorkflowMode) -> None:
        """Start one run of the Threadline workflow in a mode."""
        ...

    def disable_workflow(self, repository: str) -> None:
        """Switch the Threadline workflow off, so it stops starting on its schedule."""
        ...

    def recent_runs(self, repository: str) -> tuple[WorkflowRun, ...]:
        """The newest runs started with 'Run workflow', newest first."""
        ...

    def workflow_run(self, repository: str, run_id: int) -> WorkflowRun:
        """Read where one run is."""
        ...

    def run_notes(self, repository: str, run_id: int, title: str) -> tuple[str, ...]:
        """Read the notes with one title that a run's jobs left."""
        ...


class GitHubApiPort(Protocol):
    """GitHub's REST API, with a token the owner pastes."""

    async def workflow_state(self, repository: str, token: SecretStr) -> str:
        """Read the Threadline workflow's state; proves the token can see it."""
        ...


class GitPort(Protocol):
    """git: the link to GitHub, and the one file the set-up changes."""

    def origin_url(self) -> str | None:
        """Return where ``origin`` points, or ``None`` when there is no such link."""
        ...

    def rename_origin(self, new_name: str) -> None:
        """Keep the current ``origin`` link under another name."""
        ...

    def commit(self, path: str, message: str) -> None:
        """Add and commit one file, without pushing."""
        ...

    def commit_and_push(self, path: str, message: str) -> None:
        """Add, commit and push one file."""
        ...

    def push(self) -> None:
        """Push what is already committed."""
        ...

    def has_uncommitted(self, path: str) -> bool:
        """Tell whether one file differs from the last commit."""
        ...

    def has_unpushed(self, path: str) -> bool:
        """Tell whether a commit that changed one file is not on GitHub yet."""
        ...


class TextFilePort(Protocol):
    """One text file of the repository."""

    def read(self) -> str:
        """Return its content."""
        ...

    def write(self, text: str) -> None:
        """Replace its content."""
        ...


class NetlifyPort(Protocol):
    """Netlify's API, with a personal access token the owner pastes."""

    async def check_token(self, token: SecretStr) -> None:
        """Read the token's own account; proves the token works and changes nothing."""
        ...

    async def create_site(self, token: SecretStr, name: str) -> NetlifySite:
        """Create an empty site; raises ``SiteNameTakenError`` when the name is used."""
        ...

    async def find_site(self, token: SecretStr, site_id: str) -> NetlifySite | None:
        """Look a site up by its identifier; ``None`` when it is gone."""
        ...

    async def deploy_zip(self, token: SecretStr, site_id: str, archive: bytes) -> NetlifyDeploy:
        """Publish a zip of the whole site as its new version."""
        ...

    async def deploy_state(self, token: SecretStr, deploy_id: str) -> NetlifyDeploy:
        """Read where a deploy is."""
        ...


class LocalBuildPort(Protocol):
    """Building the dashboard on this computer, for contributors with Node.js."""

    def available(self) -> bool:
        """Tell whether the dashboard's source and Node.js 22 or newer are here."""
        ...

    def build(self) -> dict[str, bytes]:
        """Build it and return every built file by its path inside the site."""
        ...


class ClaudeKeyMakerPort(Protocol):
    """Claude Code's ``claude setup-token``, run so the set-up can take the key it prints."""

    def state(self) -> ClaudeCodeState:
        """Tell whether the key can be made on this computer."""
        ...

    def make_key(self, listener: ClaudeKeyListener) -> ClaudeKeyScreen:
        """Run it until it ends, its screen unseen; the key is in what comes back."""
        ...


@dataclass(frozen=True, slots=True)
class SetupGateways:
    """Every outside capability the steps use, injected by the command line.

    Attributes:
        admin_for: Builds the service-key helper for a project address and key.
        choices_for: Builds the category-choice store for a project address and key.
        platform: Supabase's Management API and public auth settings.
        microsoft: The mailbox sign-in.
        mailbox: The IMAP mailbox's live check and its encrypted password.
        check_linkedin: Makes one small LinkedIn call with a key.
        linkedin: Makes the LinkedIn key with the owner's application, and keeps
            the application's secret.
        status_of: Opens a web address and returns its status.
        status_of_post: Sends an empty POST with no sign-in and returns the status.
        make_encryption_key: Generates a new encryption key.
        migrations: The structure files, in order.
        clock: Today's date, for the LinkedIn expiry date.
        workflow: The GitHub Actions workflow file, which holds the daily time.
        git: Commits and pushes that file, when the owner says yes.
        github: Saves the Actions secrets and variables with the GitHub CLI, and
            checks the dashboard download's signed build provenance.
        sleep: Waits a number of seconds; tests replace it so they never wait.
        local_time_zone: Names the time zone this computer is set to, or ``None``
            when it cannot tell.
        github_api: Reads the workflow with a token, without starting it.
        refresh_function: Reads the "Refresh now" function's files, entry point first.
        netlify: Netlify's API, which hosts the dashboard.
        download: Downloads a file into memory, refusing one past a size in bytes.
        local_build: Builds the dashboard with Node.js, when it is installed.
        page_of: Opens a web address and tells its status and whether it is a page.
        site_name_suffix: Makes the random end of a new Netlify site's name.
        make_daily_start_key: Generates a new key for the on-time morning start's timer.
        claude_key_maker: Makes the Claude subscription key with ``claude setup-token``.
    """

    admin_for: Callable[[str, SecretStr], SupabaseAdminPort]
    choices_for: Callable[[str, SecretStr], ChoiceStore]
    platform: PlatformPort
    microsoft: MicrosoftPort
    mailbox: MailboxPort
    check_linkedin: Callable[[SecretStr], Awaitable[None]]
    linkedin: LinkedInPort
    status_of: Callable[[str], Awaitable[int]]
    status_of_post: Callable[[str], Awaitable[int]]
    make_encryption_key: Callable[[], str]
    migrations: tuple[MigrationFile, ...]
    clock: Clock
    workflow: TextFilePort
    git: GitPort
    github: GitHubPort
    sleep: Callable[[float], Awaitable[None]]
    local_time_zone: Callable[[], str | None]
    github_api: GitHubApiPort
    refresh_function: Callable[[], dict[str, bytes]]
    netlify: NetlifyPort
    download: Callable[[str, int], Awaitable[bytes]]
    local_build: LocalBuildPort
    page_of: Callable[[str], Awaitable[WebPage]]
    site_name_suffix: Callable[[], str]
    make_daily_start_key: Callable[[], str]
    claude_key_maker: ClaudeKeyMakerPort
