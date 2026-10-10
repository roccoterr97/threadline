"""The checks themselves: one small class per connection.

Each check makes one live call through an injected client and says, in plain
words, what it found. None of them prints, and none of them ever shows a key.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, time
from typing import Final, Protocol

from tracker.domain.daily_start import DailyStartStatus
from tracker.domain.dashboard_link import DashboardAddress
from tracker.infrastructure.imap.reader import MailboxSurvey
from tracker.services.database_structure import (
    MigrationFile,
    StructureProbe,
    StructureReport,
    inspect_structure,
)
from tracker.services.doctor.models import CheckResult, ok, problem, skipped, warning
from tracker.shared.clock import Clock
from tracker.shared.constants.collection import INITIAL_WINDOW_DAYS
from tracker.shared.constants.setup import FUNCTION_MISSING_STATUS, REFRESH_GUARD_STATUSES
from tracker.shared.constants.summary import KEY_REMINDER_DAYS
from tracker.shared.errors import DatabaseStructureMissingError

#: The command that repairs a step, shown in every fix.
SETUP_COMMAND: Final[str] = "uv run tracker setup"

#: Statuses a page answers when it is behind a Vercel login.
_LOGIN_WALL_STATUSES: Final[frozenset[int]] = frozenset({401, 403})

#: First status that counts as "the page did not open".
_FIRST_ERROR_STATUS: Final[int] = 400


def _setup(step: str) -> str:
    """Name the set-up step that repairs something."""
    return f"run '{SETUP_COMMAND} {step}'"


class OwnerSource(Protocol):
    """Lists the logins recorded as the dashboard owner."""

    def owner_ids(self) -> tuple[str, ...]:
        """Return their identifiers."""
        ...


class SecretRoundTrip(Protocol):
    """Writes, reads back and removes a throw-away secret."""

    def round_trips(self, name: str, value: str) -> bool:
        """Return whether the value survived."""
        ...


class GraphReader(Protocol):
    """The two smallest mailbox and calendar reads."""

    async def check_mailbox(self) -> None:
        """Read the inbox folder."""
        ...

    async def calendar_owner(self) -> str:
        """Return the calendar owner's address."""
        ...


@dataclass(slots=True)
class DatabaseCheck:
    """The database answers."""

    ping: Callable[[], None]
    name: str = "Database"
    fix: str = (
        "check SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY; if Supabase paused the "
        "project, restore it on supabase.com"
    )

    async def run(self) -> CheckResult:
        """Ask the database for one row."""
        self.ping()
        return ok(self.name, "reachable")


@dataclass(slots=True)
class MigrationsCheck:
    """Every structure file has been applied."""

    probe: StructureProbe
    files: tuple[MigrationFile, ...]
    name: str = "Database structure"
    fix: str = _setup("database")

    async def run(self) -> CheckResult:
        """Look for each migration's object."""
        if not self.files:
            return problem(self.name, "no migration files found", "run it from the repository")
        report = inspect_structure(self.files, self.probe)
        if report.missing:
            return problem(self.name, f"not applied yet: {', '.join(report.missing)}", self.fix)
        return ok(self.name, _structure_detail(report, len(self.files)))


def _structure_detail(report: StructureReport, total: int) -> str:
    """Say plainly that the structure is in place, and how sure that is.

    A file that leaves nothing the data API can see counts as applied when a
    newer file shows, as the set-up's database step judges it too. Only one
    that may never have run is named.
    """
    unsure = [name for name in report.unconfirmed if report.may_not_have_run(name)]
    if unsure:
        return (
            f"{total - len(unsure)} of {total} structure files applied; cannot tell for "
            f"{', '.join(unsure)} ({_setup('database')} to apply it safely)"
        )
    if not report.unconfirmed:
        return f"all {total} structure files applied"
    return (
        f"all {total} structure files applied ({len(report.unconfirmed)} leave nothing to "
        "check directly; the newer files show they are in)"
    )


@dataclass(slots=True)
class OwnerCheck:
    """Somebody is recorded as the dashboard owner."""

    owners: OwnerSource
    name: str = "Dashboard owner"
    fix: str = _setup("login")

    async def run(self) -> CheckResult:
        """Read the owner table."""
        count = len(self.owners.owner_ids())
        if count == 0:
            return problem(self.name, "nobody may sign in to the dashboard yet", self.fix)
        return ok(self.name, "recorded" if count == 1 else f"{count} logins recorded")


@dataclass(slots=True)
class SecretStoreCheck:
    """A secret can be written, read back and removed."""

    store: SecretRoundTrip
    probe_name: str
    probe_value: str
    name: str = "Secret store"
    fix: str = "check TOKEN_ENCRYPTION_KEY; it must be the key made by 'tracker setup'"

    async def run(self) -> CheckResult:
        """Make the round trip."""
        if not self.store.round_trips(self.probe_name, self.probe_value):
            return problem(self.name, "the value read back was different", self.fix)
        return ok(self.name, "a test value was stored, read back and removed")


@dataclass(slots=True)
class MicrosoftKeyCheck:
    """The stored Microsoft key decrypts and renews."""

    renew: Callable[[], Awaitable[str]]
    name: str = "Microsoft sign-in"
    fix: str = _setup("microsoft")

    async def run(self) -> CheckResult:
        """Renew the access key once."""
        await self.renew()
        return ok(self.name, "the stored key opened and renewed")


@dataclass(slots=True)
class MailboxCheck:
    """The mailbox answers."""

    graph: GraphReader
    name: str = "Mailbox"
    fix: str = _setup("microsoft")

    async def run(self) -> CheckResult:
        """Read the inbox folder."""
        await self.graph.check_mailbox()
        return ok(self.name, "the inbox answered")


@dataclass(slots=True)
class CalendarCheck:
    """The calendar answers, and says whose it is."""

    graph: GraphReader
    name: str = "Calendar"
    fix: str = _setup("microsoft")

    async def run(self) -> CheckResult:
        """Read the calendar's owner."""
        owner = await self.graph.calendar_owner()
        return ok(self.name, f"signed in as {owner}" if owner else "the calendar answered")


@dataclass(slots=True)
class ImapMailboxCheck:
    """The IMAP mailbox signs in, its inbox answers and its Sent folder is found."""

    survey: Callable[[], Awaitable[MailboxSurvey]] | None
    label: str
    name: str = "IMAP mailbox"
    fix: str = f"make a new app password, then {_setup('mailbox')}"

    async def run(self) -> CheckResult:
        """Sign in read-only, count the inbox's recent messages, look for Sent."""
        if self.survey is None:
            return skipped(self.name, "no Gmail or other IMAP mailbox is connected (optional)")
        found = await self.survey()
        detail = (
            f"your {self.label} signed in and the inbox has {found.inbox_messages} "
            f"messages from the last {INITIAL_WINDOW_DAYS} days"
        )
        if found.sent_folder is None:
            return warning(
                self.name,
                f"{detail}, but no Sent folder was found",
                "your own replies cannot be read; tell the project which folder holds them",
            )
        return ok(self.name, f"{detail}; your replies are read from '{found.sent_folder}'")


@dataclass(slots=True)
class SmtpLoginCheck:
    """The summary's sending server takes the app password; nothing is sent."""

    verify: Callable[[], Awaitable[None]] | None
    label: str
    name: str = "Summary e-mail"
    fix: str = f"make a new app password, then {_setup('mailbox')}"

    async def run(self) -> CheckResult:
        """Connect, encrypt and sign in to the SMTP server, then leave."""
        if self.verify is None:
            return skipped(
                self.name,
                "sent only through the Gmail connector of the Claude cloud routine; "
                "a run on GitHub cannot e-mail the summary",
            )
        await self.verify()
        return ok(
            self.name,
            f"your {self.label} accepted the app password for sending (nothing was sent)",
        )


@dataclass(slots=True)
class NotConnectedCheck:
    """A check for a connection the owner chose not to make."""

    name: str
    detail: str
    fix: str = ""

    async def run(self) -> CheckResult:
        """Report the check as not applying."""
        return skipped(self.name, self.detail)


@dataclass(slots=True)
class LinkedInKeyCheck:
    """LinkedIn accepts the key."""

    check_access: Callable[[], Awaitable[None]] | None
    name: str = "LinkedIn key"
    fix: str = _setup("linkedin")

    async def run(self) -> CheckResult:
        """Ask LinkedIn for the first page once."""
        if self.check_access is None:
            return skipped(self.name, "LinkedIn is not connected (optional)")
        await self.check_access()
        return ok(self.name, "LinkedIn accepted the key")


@dataclass(slots=True)
class LinkedInExpiryCheck:
    """The key's expiry date is recorded and not close."""

    has_key: bool
    expires_on: date | None
    clock: Clock
    name: str = "LinkedIn expiry date"
    fix: str = _setup("linkedin")

    async def run(self) -> CheckResult:
        """Compare the date with today."""
        if not self.has_key:
            return skipped(self.name, "LinkedIn is not connected (optional)")
        if self.expires_on is None:
            return problem(self.name, "LINKEDIN_TOKEN_EXPIRES_ON is not set", self.fix)
        days_left = (self.expires_on - self.clock.now().date()).days
        when = self.expires_on.isoformat()
        if days_left < 0:
            return problem(self.name, f"the key expired on {when}", self.fix)
        if days_left <= KEY_REMINDER_DAYS:
            return warning(self.name, f"the key expires on {when}, in {days_left} days", self.fix)
        return ok(self.name, f"the key is valid until {when}")


@dataclass(slots=True)
class DashboardCheck:
    """The dashboard opens, and the shared one has the owner's personal link."""

    status_of: Callable[[str], Awaitable[int]]
    address: DashboardAddress | None
    name: str = "Dashboard address"
    fix: str = _setup("dashboard")

    async def run(self) -> CheckResult:
        """Open the address once; name the personal link to open it with."""
        address = self.address
        if address is None:
            return skipped(self.name, "DASHBOARD_BASE_URL is not set yet (optional)")
        status = await self.status_of(address.base)
        if status in _LOGIN_WALL_STATUSES:
            detail = "the page asks for a login instead of showing the dashboard"
            return problem(self.name, detail, self.fix)
        if status >= _FIRST_ERROR_STATUS:
            return problem(self.name, f"the page answered status {status}", self.fix)
        if address.shared and address.connect is None:
            detail = (
                "the shared dashboard opens, but your personal link cannot be made: "
                "SUPABASE_URL or SUPABASE_ANON_KEY is not right"
            )
            return problem(self.name, detail, _setup("supabase"))
        return ok(self.name, f"{address.page()} opens")


@dataclass(slots=True)
class RefreshNowCheck:
    """The dashboard's "Refresh now" helper is deployed and guarding."""

    status_of_post: Callable[[str], Awaitable[int]]
    address: str
    name: str = "Refresh now"
    fix: str = _setup("refresh")

    async def run(self) -> CheckResult:
        """Call the helper once with no sign-in; a deployed one refuses that."""
        status = await self.status_of_post(self.address)
        if status in REFRESH_GUARD_STATUSES:
            return ok(self.name, "switched on: the helper answers and asks for a sign-in")
        if status == FUNCTION_MISSING_STATUS:
            return warning(self.name, "not switched on yet (optional)", self.fix)
        return problem(self.name, f"the helper answered status {status}", self.fix)


@dataclass(frozen=True, slots=True)
class WorkflowTime:
    """The daily time the GitHub workflow holds, and the zone it is read in."""

    at: time
    zone: str


@dataclass(slots=True)
class DailyStartCheck:
    """The on-time morning start is switched on, reachable and in step with the workflow.

    It is optional: without it GitHub's own timer starts the daily run, often
    hours late. Its absence is a warning, a half-done set-up a problem.
    """

    read_status: Callable[[], DailyStartStatus]
    status_of_post: Callable[[str], Awaitable[int]]
    address: str
    workflow_time: WorkflowTime | None
    name: str = "On-time morning start"
    fix: str = _setup("refresh")

    async def run(self) -> CheckResult:
        """Read the database's timer, call the function's scheduled path once, compare times."""
        try:
            status = self.read_status()
        except DatabaseStructureMissingError:
            detail = "not switched on: the database needs the newest structure file first"
            return warning(self.name, detail, f"{_setup('database')}, then {self.fix}")
        if not status.switched_on:
            detail = "not switched on (optional): GitHub alone starts the daily run, often late"
            return warning(self.name, detail, self.fix)
        if not status.job_scheduled:
            return problem(self.name, "the database's timer is missing or paused", self.fix)
        answer = await self.status_of_post(self.address)
        if answer not in REFRESH_GUARD_STATUSES:
            return problem(self.name, f"the helper answered status {answer}", self.fix)
        return self._compare_times(status)

    def _compare_times(self, status: DailyStartStatus) -> CheckResult:
        """Warn when the database's daily time is not the workflow's."""
        held = f"{status.run_at:%H:%M} ({status.time_zone})" if status.run_at else "no time"
        wanted = self.workflow_time
        if wanted is not None and not status.matches(wanted.at, wanted.zone):
            in_workflow = f"{wanted.at:%H:%M} ({wanted.zone})"
            detail = f"the database starts it at {held}, the workflow at {in_workflow}"
            return warning(self.name, detail, _setup("schedule"))
        last = status.last_started_on
        since = f"; last started a run on {last.isoformat()}" if last else ""
        return ok(self.name, f"on: Supabase starts the daily run at {held}{since}")


@dataclass(slots=True)
class SignUpsCheck:
    """Strangers cannot create a login."""

    signups_disabled: Callable[[], Awaitable[bool]]
    page: str
    name: str = "Sign-ups switched off"
    fix: str = "switch off 'Allow new users to sign up' in Supabase"

    async def run(self) -> CheckResult:
        """Read the auth server's public settings."""
        if await self.signups_disabled():
            return ok(self.name, "nobody else can create a login")
        detail = "anyone who finds the address could create a login"
        return problem(self.name, detail, f"{self.fix}: {self.page}")
