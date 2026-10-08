"""The doctor: every check on its own, the service around them, and the report."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
import respx
from pydantic import SecretStr

from tests.conftest import TEST_ENCRYPTION_KEY, FakeSupabaseClient, as_client
from tests.setup_world import FakeAdmin, migration_files
from tracker.cli.doctor_wiring import _Clients, _outlook_checks, _smtp_verify, render, run_doctor
from tracker.infrastructure.microsoft.auth import TOKEN_URL, MicrosoftAuthenticator
from tracker.infrastructure.microsoft.probe import CALENDAR_URL, INBOX_URL, GraphProbe
from tracker.infrastructure.secret_store import (
    MICROSOFT_REFRESH_TOKEN,
    SecretStore,
    imap_password_name,
)
from tracker.infrastructure.smtp import SmtpMailer
from tracker.infrastructure.supabase_platform import SupabasePlatform
from tracker.repositories import build_repositories
from tracker.services.database_structure import (
    KNOWN_MIGRATIONS,
    MigrationFile,
    inspect_structure,
    is_applied,
    list_migration_files,
)
from tracker.services.doctor.checks import (
    CalendarCheck,
    DashboardCheck,
    DatabaseCheck,
    LinkedInExpiryCheck,
    LinkedInKeyCheck,
    MailboxCheck,
    MicrosoftKeyCheck,
    MigrationsCheck,
    OwnerCheck,
    RefreshNowCheck,
    SecretStoreCheck,
    SignUpsCheck,
)
from tracker.services.doctor.models import Check, CheckResult, CheckStatus, ok
from tracker.services.doctor.service import OUTAGE_FIX, DoctorService
from tracker.services.setup.step_database import pending_files
from tracker.shared import config
from tracker.shared.clock import FixedClock
from tracker.shared.config import Settings
from tracker.shared.errors import (
    ConfigurationError,
    DatabaseUnavailableError,
    SourceAuthError,
)

pytestmark = pytest.mark.asyncio

TODAY = FixedClock(datetime(2026, 9, 29, 7, 0, tzinfo=UTC))

IMAP_USERNAME = "sam.rivera@gmail.example"

#: Turns of the event loop a made-up check waits for, so every check that is
#: allowed to start has started before the first one answers.
_TURNS_HELD: int = 25


class FakeGraph:
    def __init__(self, owner: str = "you@example.com", *, refuse: bool = False) -> None:
        self.owner = owner
        self.refuse = refuse

    async def check_mailbox(self) -> None:
        if self.refuse:
            message = "Microsoft refused to open the mailbox"
            raise SourceAuthError(message)

    async def calendar_owner(self) -> str:
        return self.owner


class FakeStore:
    def __init__(self, *, survives: bool = True) -> None:
        self.survives = survives

    def round_trips(self, name: str, value: str) -> bool:
        return self.survives


@dataclass(slots=True)
class ScriptedCheck:
    """A check that does whatever the test hands it, then passes."""

    name: str
    work: Callable[[], Awaitable[None]]
    fix: str = "made-up fix"

    async def run(self) -> CheckResult:
        await self.work()
        return ok(self.name, "answered")


class RecordingAdmin:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def owner_ids(self) -> tuple[str, ...]:
        self._calls.append("owner read")
        return ("a",)


class RecordingStore:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def round_trips(self, name: str, value: str) -> bool:
        self._calls.append("secret round trip")
        return True


async def _wait_a_few_turns() -> None:
    """Wait the way a network call does, without touching the wall clock."""
    for _ in range(_TURNS_HELD):
        await asyncio.sleep(0)


@pytest.fixture
def secret_store(fake_client: FakeSupabaseClient, clock: FixedClock) -> SecretStore:
    """A secret store on the in-memory database."""
    repositories = build_repositories(as_client(fake_client))
    return SecretStore(repositories.app_secrets, SecretStr(TEST_ENCRYPTION_KEY), clock)


async def _status(result_check: Check) -> CheckStatus:
    return (await DoctorService([result_check]).run()).results[0].status


# --- Individual checks ----------------------------------------------------------


async def test_database_check_passes_and_fails() -> None:
    def down() -> None:
        message = "database did not answer after 2 attempts"
        raise DatabaseUnavailableError(message)

    assert await _status(DatabaseCheck(lambda: None)) is CheckStatus.OK
    report = await DoctorService([DatabaseCheck(down)]).run()
    assert report.results[0].status is CheckStatus.PROBLEM
    assert report.results[0].fix.startswith(OUTAGE_FIX)
    assert "SUPABASE_URL" in report.results[0].fix


async def test_migrations_check_names_what_is_missing() -> None:
    admin = FakeAdmin(present={"0001_schema", "0002_access_rules"})

    result = await MigrationsCheck(admin, migration_files()).run()

    assert result.status is CheckStatus.PROBLEM
    assert "0003_people_overview" in result.detail
    assert "tracker setup database" in result.fix


async def test_migrations_check_tolerates_unknown_future_files(tmp_path: Path) -> None:
    extra = MigrationFile("0099_future", tmp_path / "0099_future.sql")

    result = await MigrationsCheck(FakeAdmin(), (*migration_files(), extra)).run()

    assert result.status is CheckStatus.OK
    assert "0099_future" in result.detail
    confirmable = sum(marker is not None for marker in KNOWN_MIGRATIONS.values())
    assert f"{confirmable} of {len(KNOWN_MIGRATIONS) + 1}" in result.detail


async def test_migrations_check_without_files_is_a_problem() -> None:
    result = await MigrationsCheck(FakeAdmin(), ()).run()

    assert result.status is CheckStatus.PROBLEM


async def test_owner_check() -> None:
    assert (await OwnerCheck(FakeAdmin(owners=["a"])).run()).status is CheckStatus.OK
    missing = await OwnerCheck(FakeAdmin()).run()
    assert missing.status is CheckStatus.PROBLEM
    assert "tracker setup login" in missing.fix


async def test_secret_store_check() -> None:
    assert (await SecretStoreCheck(FakeStore(), "n", "v").run()).status is CheckStatus.OK
    broken = await SecretStoreCheck(FakeStore(survives=False), "n", "v").run()
    assert broken.status is CheckStatus.PROBLEM


async def test_microsoft_key_check_turns_a_refusal_into_a_fix() -> None:
    async def renewed() -> str:
        return "access"

    async def refused() -> str:
        message = "Microsoft refused the sign-in (invalid_grant) - sign in again"
        raise SourceAuthError(message)

    assert await _status(MicrosoftKeyCheck(renewed)) is CheckStatus.OK
    report = await DoctorService([MicrosoftKeyCheck(refused)]).run()
    assert report.results[0].fix == "run 'uv run tracker setup microsoft'"
    assert "invalid_grant" in report.results[0].detail


async def test_mailbox_and_calendar_checks() -> None:
    calendar = await CalendarCheck(FakeGraph()).run()

    assert calendar.detail == "signed in as you@example.com"
    assert await _status(MailboxCheck(FakeGraph())) is CheckStatus.OK
    assert await _status(MailboxCheck(FakeGraph(refuse=True))) is CheckStatus.PROBLEM


async def test_linkedin_key_check_is_skipped_without_a_key() -> None:
    async def accepted() -> None:
        return None

    assert (await LinkedInKeyCheck(None).run()).status is CheckStatus.SKIPPED
    assert (await LinkedInKeyCheck(accepted).run()).status is CheckStatus.OK


@pytest.mark.parametrize(
    ("expires_on", "status"),
    [
        (date(2027, 1, 1), CheckStatus.OK),
        (date(2026, 10, 3), CheckStatus.WARNING),
        (date(2026, 9, 1), CheckStatus.PROBLEM),
        (None, CheckStatus.PROBLEM),
    ],
)
async def test_linkedin_expiry(expires_on: date | None, status: CheckStatus) -> None:
    result = await LinkedInExpiryCheck(True, expires_on, TODAY).run()

    assert result.status is status


async def test_linkedin_expiry_is_skipped_without_a_key() -> None:
    result = await LinkedInExpiryCheck(False, None, TODAY).run()

    assert result.status is CheckStatus.SKIPPED


@pytest.mark.parametrize(
    ("status", "expected"),
    [(200, CheckStatus.OK), (401, CheckStatus.PROBLEM), (404, CheckStatus.PROBLEM)],
)
async def test_dashboard_check(status: int, expected: CheckStatus) -> None:
    async def status_of(url: str) -> int:
        return status

    result = await DashboardCheck(status_of, "https://you.vercel.app").run()

    assert result.status is expected


async def test_dashboard_check_is_skipped_without_an_address() -> None:
    async def status_of(url: str) -> int:
        raise AssertionError(url)

    assert (await DashboardCheck(status_of, None).run()).status is CheckStatus.SKIPPED


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, CheckStatus.OK),
        (403, CheckStatus.OK),
        (404, CheckStatus.WARNING),
        (500, CheckStatus.PROBLEM),
    ],
)
async def test_refresh_now_check(status: int, expected: CheckStatus) -> None:
    async def status_of_post(url: str) -> int:
        return status

    result = await RefreshNowCheck(status_of_post, "https://p.supabase.co/functions/v1/x").run()

    assert result.status is expected
    if expected is not CheckStatus.OK:
        assert result.fix == "run 'uv run tracker setup refresh'"


async def test_signups_check_points_at_the_settings_page() -> None:
    async def open_signups() -> bool:
        return False

    async def closed() -> bool:
        return True

    result = await SignUpsCheck(open_signups, "https://supabase.example/providers").run()

    assert result.status is CheckStatus.PROBLEM
    assert "https://supabase.example/providers" in result.fix
    assert (await SignUpsCheck(closed, "page").run()).status is CheckStatus.OK


# --- The service ---------------------------------------------------------------


async def test_a_failing_check_does_not_stop_the_next_one() -> None:
    def down() -> None:
        message = "database did not answer"
        raise DatabaseUnavailableError(message)

    report = await DoctorService([DatabaseCheck(down), OwnerCheck(FakeAdmin(owners=["a"]))]).run()

    assert [result.status for result in report.results] == [
        CheckStatus.PROBLEM,
        CheckStatus.OK,
    ]
    assert not report.healthy


async def test_warnings_and_skips_keep_the_report_healthy() -> None:
    report = await DoctorService(
        [LinkedInKeyCheck(None), LinkedInExpiryCheck(True, date(2026, 10, 1), TODAY)]
    ).run()

    assert report.healthy


async def test_results_keep_the_given_order_when_a_later_check_answers_first() -> None:
    answered: list[str] = []

    async def slow() -> None:
        await _wait_a_few_turns()
        answered.append("slow")

    async def quick() -> None:
        answered.append("quick")

    report = await DoctorService([ScriptedCheck("Slow", slow), ScriptedCheck("Quick", quick)]).run()

    assert answered == ["quick", "slow"]
    assert [result.name for result in report.results] == ["Slow", "Quick"]


async def test_checks_wait_side_by_side() -> None:
    waiting = 0
    most_waiting_at_once = 0

    async def answer_slowly() -> None:
        nonlocal waiting, most_waiting_at_once
        waiting += 1
        most_waiting_at_once = max(most_waiting_at_once, waiting)
        await _wait_a_few_turns()
        waiting -= 1

    names = ("Mailbox", "Calendar", "LinkedIn key")
    report = await DoctorService([ScriptedCheck(name, answer_slowly) for name in names]).run()

    assert most_waiting_at_once == len(names)
    assert report.healthy


async def test_a_refusal_and_an_unreachable_service_are_problems_and_the_rest_finish() -> None:
    finished: list[str] = []

    async def refused() -> None:
        message = "Microsoft refused to open the mailbox"
        raise SourceAuthError(message)

    async def unreachable() -> None:
        message = "made-up connection failure"
        raise httpx.ConnectError(message)

    async def slow() -> None:
        await _wait_a_few_turns()
        finished.append("slow")

    report = await DoctorService(
        [
            ScriptedCheck("Slow, before", slow),
            ScriptedCheck("Refused", refused),
            ScriptedCheck("Unreachable", unreachable),
            ScriptedCheck("Slow, after", slow),
        ]
    ).run()

    _, refusal, outage, _ = report.results
    assert [result.status for result in report.results] == [
        CheckStatus.OK,
        CheckStatus.PROBLEM,
        CheckStatus.PROBLEM,
        CheckStatus.OK,
    ]
    assert (refusal.detail, refusal.fix) == ("Microsoft refused to open the mailbox", "made-up fix")
    assert (outage.detail, outage.fix) == ("the service could not be reached", OUTAGE_FIX)
    assert finished == ["slow", "slow"]


# --- What the checks share ------------------------------------------------------


@pytest.mark.parametrize(
    "check",
    [
        DatabaseCheck(lambda: None),
        MigrationsCheck(FakeAdmin(), migration_files()),
        OwnerCheck(FakeAdmin(owners=["a"])),
        SecretStoreCheck(FakeStore(), "n", "v"),
    ],
    ids=lambda check: check.name,
)
async def test_a_database_check_never_waits_so_two_cannot_overlap_on_their_client(
    check: Check,
) -> None:
    steps = check.run()

    # A coroutine that ends on its first step never handed the event loop to
    # another check.
    with pytest.raises(StopIteration) as ended:
        steps.send(None)

    assert ended.value.value.status is CheckStatus.OK


async def test_database_checks_run_in_turn_while_another_check_waits() -> None:
    calls: list[str] = []

    async def mailbox() -> None:
        calls.append("mailbox asked")
        await _wait_a_few_turns()
        calls.append("mailbox answered")

    report = await DoctorService(
        [
            ScriptedCheck("Mailbox", mailbox),
            DatabaseCheck(lambda: calls.append("database pinged")),
            OwnerCheck(RecordingAdmin(calls)),
            SecretStoreCheck(RecordingStore(calls), "n", "v"),
        ]
    ).run()

    assert report.healthy
    assert calls == [
        "mailbox asked",
        "database pinged",
        "owner read",
        "secret round trip",
        "mailbox answered",
    ]


async def test_the_three_microsoft_checks_side_by_side_renew_the_key_once(
    settings: Settings,
    fake_client: FakeSupabaseClient,
    secret_store: SecretStore,
    clock: FixedClock,
) -> None:
    secret_store.put_secret(MICROSOFT_REFRESH_TOKEN, "old-long-lived-key")

    async def renew_slowly(_request: httpx.Request) -> httpx.Response:
        await _wait_a_few_turns()
        return httpx.Response(
            200,
            json={
                "access_token": "made-up-access-key",
                "refresh_token": "new-long-lived-key",
                "expires_in": 3599,
            },
        )

    with respx.mock:
        renewal = respx.post(TOKEN_URL).mock(side_effect=renew_slowly)
        respx.get(INBOX_URL).mock(return_value=httpx.Response(200, json={"id": "i"}))
        respx.get(CALENDAR_URL).mock(
            return_value=httpx.Response(
                200, json={"id": "c", "owner": {"address": "you@example.com"}}
            )
        )
        async with (
            MicrosoftAuthenticator(secret_store, clock) as authenticator,
            GraphProbe(authenticator) as graph,
        ):
            clients = _Clients(
                as_client(fake_client), secret_store, authenticator, graph, SupabasePlatform()
            )
            report = await DoctorService(_outlook_checks(settings, clients)).run()

    assert [(result.name, result.status) for result in report.results] == [
        ("Microsoft sign-in", CheckStatus.OK),
        ("Mailbox", CheckStatus.OK),
        ("Calendar", CheckStatus.OK),
    ]
    assert renewal.call_count == 1
    assert secret_store.get_secret(MICROSOFT_REFRESH_TOKEN) == "new-long-lived-key"


async def test_the_smtp_sign_in_runs_off_the_event_loop(
    valid_environment: None,
    monkeypatch: pytest.MonkeyPatch,
    secret_store: SecretStore,
) -> None:
    monkeypatch.setenv("MAIL_SOURCES", "imap")
    monkeypatch.setenv("IMAP_PROVIDER", "gmail")
    monkeypatch.setenv("IMAP_USERNAME", IMAP_USERNAME)
    config.reset_settings_cache()
    secret_store.put_secret(imap_password_name(IMAP_USERNAME), "made-up-app-password")
    signed_in_on: list[int] = []

    def sign_in(_mailer: SmtpMailer) -> None:
        signed_in_on.append(threading.get_ident())

    monkeypatch.setattr(SmtpMailer, "verify", sign_in)
    verify = _smtp_verify(config.get_settings(), secret_store)

    assert verify is not None
    await verify()

    assert len(signed_in_on) == 1
    assert signed_in_on[0] != threading.get_ident()


# --- Migrations on disk --------------------------------------------------------


def _files(tmp_path: Path, *names: str) -> tuple[MigrationFile, ...]:
    for name in names:
        (tmp_path / f"{name}.sql").write_text("select 1;", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")
    return list_migration_files(tmp_path)


async def test_migration_files_are_listed_in_order(tmp_path: Path) -> None:
    files = _files(tmp_path, "0002_access_rules", "0001_schema")

    assert [item.name for item in files] == ["0001_schema", "0002_access_rules"]
    assert list_migration_files(tmp_path / "absent") == ()


async def test_the_real_migration_folder_is_fully_known() -> None:
    from tracker.shared.constants.setup import MIGRATIONS_DIRECTORY

    names = [item.name for item in list_migration_files(MIGRATIONS_DIRECTORY)]

    assert names[:7] == [
        "0001_schema",
        "0002_access_rules",
        "0003_people_overview",
        "0004_overdue_and_chase",
        "0005_calendar",
        "0006_meeting_time",
        "0007_apply_relevance_answers",
    ]


async def test_unconfirmed_files_after_a_missing_one_are_pending() -> None:
    admin = FakeAdmin(present={"0001_schema", "0002_access_rules"})
    files = migration_files()

    pending = pending_files(files, inspect_structure(files, admin))

    assert [item.name for item in pending][-1] == files[-1].name
    assert pending_files(files, inspect_structure(files, FakeAdmin())) == ()


def _pending_when_applied_up_to(newest: str, *more: MigrationFile) -> list[str]:
    """What the set-up offers a database that has every visible file up to ``newest``."""
    files = (*migration_files(), *more)
    admin = FakeAdmin(present={name for name in KNOWN_MIGRATIONS if name <= newest})
    return [item.name for item in pending_files(files, inspect_structure(files, admin))]


async def test_a_database_at_0014_is_offered_everything_after_it() -> None:
    assert _pending_when_applied_up_to("0014_refresh_cooldown") == [
        "0015_category_names",
        "0016_person_notes",
        "0017_daily_start",
    ]


async def test_a_database_at_0015_is_offered_0016_and_0017() -> None:
    assert _pending_when_applied_up_to("0015_category_names") == [
        "0016_person_notes",
        "0017_daily_start",
    ]


async def test_a_database_at_0016_is_offered_only_the_on_time_start() -> None:
    assert _pending_when_applied_up_to("0016_person_notes") == ["0017_daily_start"]


async def test_the_doctor_says_0016_is_missing_from_a_database_at_0015() -> None:
    admin = FakeAdmin(present=set(KNOWN_MIGRATIONS) - {"0016_person_notes"})

    result = await MigrationsCheck(admin, migration_files()).run()

    assert result.status is CheckStatus.PROBLEM
    assert result.detail == "not applied yet: 0016_person_notes"


async def test_0016_shows_once_the_notes_table_is_there() -> None:
    admin = FakeAdmin()

    assert is_applied("0016_person_notes", admin) is True
    assert admin.has_columns("person_notes", "id,person_id")


async def test_the_doctor_says_0015_is_missing_from_a_database_at_0014() -> None:
    admin = FakeAdmin(present=set(KNOWN_MIGRATIONS) - {"0015_category_names"})

    result = await MigrationsCheck(admin, migration_files()).run()

    assert result.status is CheckStatus.PROBLEM
    assert result.detail == "not applied yet: 0015_category_names"


async def test_0015_shows_once_the_reserved_group_is_renamed() -> None:
    admin = FakeAdmin()

    assert is_applied("0015_category_names", admin) is True
    assert admin.has_row("categories", {"key": "unknown", "group_label": "Not known"})


@pytest.mark.parametrize(
    ("newest", "unseen"),
    [
        ("0006_meeting_time", "0007_apply_relevance_answers"),
        ("0010_status_in_process", "0011_function_access"),
    ],
)
async def test_a_file_that_leaves_no_mark_is_offered_when_nothing_after_it_shows(
    newest: str, unseen: str
) -> None:
    assert _pending_when_applied_up_to(newest)[0] == unseen


async def test_a_file_that_leaves_no_mark_is_taken_as_applied_when_a_later_one_shows() -> None:
    assert _pending_when_applied_up_to("0017_daily_start") == []


async def test_a_file_this_version_does_not_know_is_offered(tmp_path: Path) -> None:
    future = MigrationFile("0099_future", tmp_path / "0099_future.sql")

    assert _pending_when_applied_up_to("0017_daily_start", future) == ["0099_future"]


async def test_the_newest_migration_can_be_seen_from_outside() -> None:
    """Else a database that has it would be offered it again every time."""
    from tracker.shared.constants.setup import MIGRATIONS_DIRECTORY

    newest = list_migration_files(MIGRATIONS_DIRECTORY)[-1].name

    assert KNOWN_MIGRATIONS.get(newest) is not None


# --- The composition root ------------------------------------------------------


async def test_missing_configuration_is_one_plain_problem_and_the_rest_skipped() -> None:
    def broken() -> Settings:
        message = "invalid configuration: SUPABASE_URL (Field required)"
        raise ConfigurationError(message)

    report = await run_doctor(broken)
    lines = render(report)

    assert report.results[0].status is CheckStatus.PROBLEM
    assert "SUPABASE_URL (missing)" in lines[0]
    assert all(result.status is CheckStatus.SKIPPED for result in report.results[1:])
    assert "1 problem(s) found" in lines[-2]


async def test_render_of_a_healthy_report() -> None:
    report = await DoctorService([OwnerCheck(FakeAdmin(owners=["a"]))]).run()

    assert render(report) == (
        "ok       Dashboard owner: recorded",
        "Everything Threadline needs is working.",
    )
