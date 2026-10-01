"""What the set-up needs from the outside world, as small interfaces.

Every step talks to the terminal, the ``.env`` file and the services only
through these, so each step is tested without a terminal or a network.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from pydantic import SecretStr

from tracker.infrastructure.imap.connection import StoreAccess
from tracker.infrastructure.imap.reader import MailboxSurvey
from tracker.infrastructure.imap.session import ImapAccount
from tracker.infrastructure.microsoft.connection import MicrosoftAccess, ShowCode
from tracker.services.database_structure import MigrationFile, StructureProbe
from tracker.services.profile.choice import Choice, SavedChoice
from tracker.shared.clock import Clock


class SetupIO(Protocol):
    """The conversation with the person running the set-up."""

    def say(self, text: str) -> None:
        """Show one line."""
        ...

    def ask(self, prompt: str, *, default: str | None = None) -> str:
        """Ask for a value that may be shown on screen."""
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

    def create_confirmed_user(self, email: str) -> str | None:
        """Create a login; ``None`` when it already existed."""
        ...


class PlatformPort(Protocol):
    """Supabase's Management API and the auth server's public settings."""

    async def signups_disabled(self, project_url: str, publishable_key: SecretStr) -> bool:
        """Read whether strangers are prevented from creating a login."""
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

    async def save_password(self, access: StoreAccess, username: str, password: SecretStr) -> None:
        """Store an app password, encrypted."""
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
    """The GitHub CLI: the repository's Actions secrets and variables."""

    def ready(self) -> bool:
        """Tell whether the CLI is installed and signed in."""
        ...

    def repository(self) -> str | None:
        """Name the repository as ``owner/name``, or ``None`` when unknown."""
        ...

    def set_secret(self, repository: str, name: str, value: SecretStr) -> None:
        """Save one secret, its value never shown or passed as an argument."""
        ...

    def set_variable(self, repository: str, name: str, value: str) -> None:
        """Save one variable."""
        ...

    def create_private_copy(self, name: str) -> None:
        """Create a private repository from this folder, link it as ``origin`` and push."""
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


class TextFilePort(Protocol):
    """One text file of the repository."""

    def read(self) -> str:
        """Return its content."""
        ...

    def write(self, text: str) -> None:
        """Replace its content."""
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
        status_of: Opens a web address and returns its status.
        status_of_post: Sends an empty POST with no sign-in and returns the status.
        make_encryption_key: Generates a new encryption key.
        migrations: The structure files, in order.
        clock: Today's date, for the LinkedIn expiry date.
        workflow: The GitHub Actions workflow file, which holds the daily time.
        git: Commits and pushes that file, when the owner says yes.
        github: Saves the Actions secrets and variables with the GitHub CLI.
        sleep: Waits a number of seconds; tests replace it so they never wait.
        local_time_zone: Names the time zone this computer is set to.
        github_api: Reads the workflow with a token, without starting it.
        refresh_function: Reads the "Refresh now" function's files, entry point first.
    """

    admin_for: Callable[[str, SecretStr], SupabaseAdminPort]
    choices_for: Callable[[str, SecretStr], ChoiceStore]
    platform: PlatformPort
    microsoft: MicrosoftPort
    mailbox: MailboxPort
    check_linkedin: Callable[[SecretStr], Awaitable[None]]
    status_of: Callable[[str], Awaitable[int]]
    status_of_post: Callable[[str], Awaitable[int]]
    make_encryption_key: Callable[[], str]
    migrations: tuple[MigrationFile, ...]
    clock: Clock
    workflow: TextFilePort
    git: GitPort
    github: GitHubPort
    sleep: Callable[[float], Awaitable[None]]
    local_time_zone: Callable[[], str]
    github_api: GitHubApiPort
    refresh_function: Callable[[], dict[str, bytes]]
