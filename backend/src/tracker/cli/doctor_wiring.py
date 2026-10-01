"""Builds the doctor's checks from the configuration, and prints the report.

This is the composition root for ``tracker doctor``: the only place that knows
which concrete client each check receives.

The doctor runs the checks side by side, so what two checks share has to be
safe to share:

* The database, structure, owner and secret-store checks use the one database
  client, which blocks instead of waiting. Each therefore finishes before the
  next check starts; they are deliberately not moved to threads, where they
  would overlap on that client.
* The three Microsoft checks share one authenticator, which renews the key
  under a lock: whichever asks first renews, and the other two reuse that key.
* Every other check opens a connection of its own.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import timedelta
from typing import Final

from pydantic import SecretStr
from supabase import Client

from tracker.infrastructure.database import create_database_client, probe_database
from tracker.infrastructure.imap.reader import ImapMailbox, MailboxSurvey
from tracker.infrastructure.imap.session import ImapSession
from tracker.infrastructure.linkedin.client import LinkedInSnapshotClient
from tracker.infrastructure.microsoft.auth import MicrosoftAuthenticator
from tracker.infrastructure.microsoft.probe import GraphProbe
from tracker.infrastructure.secret_store import SecretStore
from tracker.infrastructure.smtp import SmtpMailer
from tracker.infrastructure.supabase_admin import SupabaseAdmin
from tracker.infrastructure.supabase_platform import SupabasePlatform
from tracker.infrastructure.web_probe import WebProbe
from tracker.repositories import build_repositories
from tracker.services.collection.mailboxes import imap_account, saved_app_password
from tracker.services.database_structure import list_migration_files
from tracker.services.doctor.checks import (
    CalendarCheck,
    DashboardCheck,
    DatabaseCheck,
    ImapMailboxCheck,
    LinkedInExpiryCheck,
    LinkedInKeyCheck,
    MailboxCheck,
    MicrosoftKeyCheck,
    MigrationsCheck,
    NotConnectedCheck,
    OwnerCheck,
    RefreshNowCheck,
    SecretStoreCheck,
    SignUpsCheck,
    SmtpLoginCheck,
)
from tracker.services.doctor.models import Check, CheckResult, CheckStatus, ok, problem, skipped
from tracker.services.doctor.service import DoctorReport, DoctorService
from tracker.services.setup.step_refresh import function_url
from tracker.services.setup.values import project_ref
from tracker.services.summary.sender import smtp_account
from tracker.shared.clock import SystemClock
from tracker.shared.config import Settings, get_settings
from tracker.shared.constants.collection import INITIAL_WINDOW_DAYS
from tracker.shared.constants.mailbox import IMAP_PRESETS, DeliveryRoute
from tracker.shared.constants.retry import HEALTHCHECK_ATTEMPTS, HEALTHCHECK_DELAY_SECONDS
from tracker.shared.constants.setup import (
    MIGRATIONS_DIRECTORY,
    SECRET_PROBE_NAME,
    SECRET_PROBE_VALUE,
    SUPABASE_SIGN_IN_PAGE,
)
from tracker.shared.errors import ConfigurationError, TrackerError

CONFIGURATION: Final[str] = "Configuration"

#: How the settings library words an absent value.
_PYDANTIC_MISSING: Final[str] = "Field required"

#: Every check that needs the configuration, named for the "skipped" lines.
DEPENDENT_CHECKS: Final[tuple[str, ...]] = (
    "Database",
    "Database structure",
    "Dashboard owner",
    "Secret store",
    "Microsoft sign-in",
    "Mailbox",
    "Calendar",
    "IMAP mailbox",
    "Summary e-mail",
    "LinkedIn key",
    "LinkedIn expiry date",
    "Dashboard address",
    "Refresh now",
    "Sign-ups switched off",
)

_LABELS: Final[dict[CheckStatus, str]] = {
    CheckStatus.OK: "ok     ",
    CheckStatus.WARNING: "warning",
    CheckStatus.PROBLEM: "PROBLEM",
    CheckStatus.SKIPPED: "skipped",
}


async def run_doctor(load_settings: Callable[[], Settings] = get_settings) -> DoctorReport:
    """Check every connection once.

    Args:
        load_settings: Reads the configuration; replaced in tests.

    Returns:
        One result per check, the configuration first.
    """
    try:
        settings = load_settings()
        client = create_database_client(settings)
        store = SecretStore(
            build_repositories(client).app_secrets, settings.token_encryption_key, SystemClock()
        )
    except ConfigurationError as error:
        return _configuration_failed(error)
    async with AsyncExitStack() as stack:
        authenticator = await stack.enter_async_context(
            MicrosoftAuthenticator.for_settings(store, SystemClock(), settings)
        )
        graph = await stack.enter_async_context(GraphProbe(authenticator))
        platform = await stack.enter_async_context(SupabasePlatform())
        checks = _checks(settings, _Clients(client, store, authenticator, graph, platform))
        report = await DoctorService(checks).run()
    first = ok(CONFIGURATION, "every required setting is present")
    return DoctorReport((first, *report.results))


def render(report: DoctorReport) -> tuple[str, ...]:
    """Turn the report into lines, one per check, and a closing sentence."""
    lines = [_line(result) for result in report.results]
    problems = sum(result.status is CheckStatus.PROBLEM for result in report.results)
    if problems:
        lines.append(f"{problems} problem(s) found. Fix them in the order shown, then run")
        lines.append("'uv run tracker doctor' again.")
    else:
        lines.append("Everything Threadline needs is working.")
    return tuple(lines)


def _line(result: CheckResult) -> str:
    """One line: status, what was checked, what was found, what to do."""
    text = f"{_LABELS[result.status]}  {result.name}: {result.detail}"
    return f"{text}. Fix: {result.fix}" if result.fix else text


def _configuration_failed(error: TrackerError) -> DoctorReport:
    """Report a broken configuration, and every other check as not run."""
    detail = error.message.removeprefix("invalid configuration: ").replace(
        f" ({_PYDANTIC_MISSING})", " (missing)"
    )
    fix = (
        "run 'uv run tracker setup'; on GitHub, add the missing secrets with "
        "'uv run tracker setup github'"
    )
    first = problem(CONFIGURATION, f"missing or wrong: {detail}", fix)
    rest = (skipped(name, "needs the configuration first") for name in DEPENDENT_CHECKS)
    return DoctorReport((first, *rest))


@dataclass(frozen=True, slots=True)
class _Clients:
    """The open clients the checks share."""

    database: Client
    store: SecretStore
    authenticator: MicrosoftAuthenticator
    graph: GraphProbe
    platform: SupabasePlatform


def _checks(settings: Settings, clients: _Clients) -> tuple[Check, ...]:
    """Build every check on its client."""
    client = clients.database
    admin = SupabaseAdmin(client)
    token = settings.linkedin_access_token

    def ping() -> None:
        probe_database(
            client, attempts=HEALTHCHECK_ATTEMPTS, delay_seconds=HEALTHCHECK_DELAY_SECONDS
        )

    async def signups_disabled() -> bool:
        return await clients.platform.signups_disabled(
            settings.supabase_url, settings.supabase_anon_key
        )

    return (
        DatabaseCheck(ping),
        MigrationsCheck(admin, list_migration_files(MIGRATIONS_DIRECTORY)),
        OwnerCheck(admin),
        SecretStoreCheck(clients.store, SECRET_PROBE_NAME, SECRET_PROBE_VALUE),
        *_outlook_checks(settings, clients),
        ImapMailboxCheck(
            _imap_survey(settings, clients.store), IMAP_PRESETS[settings.imap_provider].label
        ),
        SmtpLoginCheck(
            _smtp_verify(settings, clients.store), IMAP_PRESETS[settings.imap_provider].label
        ),
        LinkedInKeyCheck(_linkedin_check(token) if token else None),
        LinkedInExpiryCheck(token is not None, settings.linkedin_token_expires_on, SystemClock()),
        DashboardCheck(WebProbe().status_of, settings.dashboard_base_url),
        RefreshNowCheck(WebProbe().status_of_post, function_url(settings.supabase_url)),
        SignUpsCheck(signups_disabled, _sign_in_page(settings.supabase_url)),
    )


def _outlook_checks(settings: Settings, clients: _Clients) -> tuple[Check, ...]:
    """The Microsoft sign-in, mailbox and calendar checks, or why they do not apply."""
    if settings.outlook_enabled:
        return (
            MicrosoftKeyCheck(clients.authenticator.access_token),
            MailboxCheck(clients.graph),
            CalendarCheck(clients.graph),
        )
    detail = "Outlook is not connected (optional when another mailbox is)"
    return (
        NotConnectedCheck("Microsoft sign-in", detail),
        NotConnectedCheck("Mailbox", detail),
        NotConnectedCheck("Calendar", "the calendar is read from Outlook only"),
    )


def _imap_survey(
    settings: Settings, store: SecretStore
) -> Callable[[], Awaitable[MailboxSurvey]] | None:
    """Sign in to the IMAP mailbox read-only and look at its inbox, when there is one."""
    if not settings.imap_enabled:
        return None

    async def survey() -> MailboxSurvey:
        account = imap_account(settings)
        session = ImapSession(account, saved_app_password(store, account))
        since = SystemClock().now() - timedelta(days=INITIAL_WINDOW_DAYS)
        async with ImapMailbox(session) as mailbox:
            return await mailbox.survey(since)

    return survey


def _smtp_verify(settings: Settings, store: SecretStore) -> Callable[[], Awaitable[None]] | None:
    """Sign in to the summary's sending server, when the summary goes by SMTP."""
    if settings.summary_route is not DeliveryRoute.SMTP:
        return None

    async def verify() -> None:
        account = smtp_account(settings)
        mailer = SmtpMailer(account, saved_app_password(store, imap_account(settings)))
        # The sign-in blocks until the mail server answers. On this thread it
        # would freeze the checks still waiting, long enough for their requests
        # to time out. The mailer and its connection are used nowhere else, and
        # the password is read before the hand-over, so the thread shares nothing.
        await asyncio.to_thread(mailer.verify)

    return verify


def _linkedin_check(token: SecretStr) -> Callable[[], Awaitable[None]]:
    """Make one small LinkedIn call with the configured key."""

    async def check() -> None:
        async with LinkedInSnapshotClient(token) as client:
            await client.check_access()

    return check


def _sign_in_page(url: str) -> str:
    """Supabase's sign-in settings page for this project."""
    try:
        return SUPABASE_SIGN_IN_PAGE.format(ref=project_ref(url))
    except TrackerError:
        return "Supabase > Authentication > Sign In / Providers"
