"""Choosing mailboxes: configuration, collection over IMAP, and what the run records.

A Gmail (or any IMAP) mailbox must be judged exactly like an Outlook one: the
same noise rules, the same people, the same directions. These tests run the
mail collector on the fake IMAP server from :mod:`tests.imap_world` and compare
it with the Graph path of :mod:`tests.test_collectors`.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import SecretStr
from typer.testing import CliRunner

from tests.conftest import JOB_SEARCH_RULES, TEST_ENCRYPTION_KEY, FakeSupabaseClient, as_client
from tests.imap_world import (
    APP_PASSWORD,
    GMAIL_ACCOUNT,
    FakeImapServer,
    StoredMessage,
    body_fetches,
    mail,
    session_on,
    writes_sent,
)
from tests.test_collectors import collect_email, rows_of
from tests.test_summary_send import FakeSmtp
from tracker.cli.main import build_cli
from tracker.domain.enums import Channel, RunStatus, RunStep, RunTrigger
from tracker.domain.mail import MailMessage
from tracker.domain.models import RunLog, RunStepLog
from tracker.infrastructure.imap.connection import ImapConnection, StoreAccess
from tracker.infrastructure.imap.reader import ImapMailbox
from tracker.infrastructure.secret_store import SecretStore, imap_password_name
from tracker.infrastructure.smtp import SmtpAccount
from tracker.repositories import Repositories, build_repositories
from tracker.services.collection.all_sources import AllSourcesCollector, Source, record_outcomes
from tracker.services.collection.calendar_collector import CalendarCollector
from tracker.services.collection.email_collector import EmailCollector
from tracker.services.collection.mailbox import MailboxReader, MailboxSource
from tracker.services.collection.mailboxes import configured_mailboxes, imap_account
from tracker.services.collection.window import last_collected_at
from tracker.services.runs.run_recorder import (
    RunRecorder,
    StepOutcome,
    StepResult,
    unconfigured_steps,
)
from tracker.services.summary.problem_messages import explain
from tracker.shared import config
from tracker.shared.clock import FixedClock
from tracker.shared.config import Settings
from tracker.shared.constants.mailbox import ImapProvider, MailSource
from tracker.shared.errors import (
    ConfigurationError,
    MailboxPasswordError,
    MailboxWindowCappedError,
)

OWNER = "sam.rivera@mailbox.example"
SENT = "Sent Messages"


def moment(day: int, hour: int, minute: int = 0) -> datetime:
    """A made-up moment in September 2026."""
    return datetime(2026, 9, day, hour, minute, tzinfo=UTC)


def outlook_twin() -> FakeImapServer:
    """The Graph test mailbox of ``test_collectors``, as an IMAP server holds it."""
    inbox = [
        StoredMessage(
            1,
            mail(
                sender="Startup Weekly <newsletter@weekly.example>",
                to=OWNER,
                subject="This week in hiring",
                sent=moment(8, 6),
                message_id="<news@weekly.example>",
                unsubscribe=True,
            ),
            moment(8, 6),
        ),
        StoredMessage(
            2,
            mail(
                sender="Élodie Martin <elodie.martin@acme.example>",
                to=OWNER,
                subject="Coffee next week?",
                sent=moment(10, 9, 30),
                message_id="<h1@acme.example>",
            ),
            moment(10, 9, 30),
        ),
    ]
    sent = [
        StoredMessage(
            1,
            mail(
                sender=f"Sam Rivera <{OWNER}>",
                to="Élodie Martin <elodie.martin@acme.example>",
                subject="RE: Coffee next week?",
                sent=moment(10, 10),
                message_id="<r1@mailbox.example>",
                references="<h1@acme.example>",
                in_reply_to="<h1@acme.example>",
            ),
            moment(10, 10),
        ),
    ]
    return FakeImapServer(
        folders={"INBOX": inbox, SENT: sent},
        attributes={SENT: "\\HasNoChildren \\Sent"},
        gmail=False,
    )


def imap_source(server: FakeImapServer) -> MailboxSource:
    """The fake server as a mailbox the collector can open."""
    return MailboxSource(MailSource.IMAP, lambda: ImapMailbox(session_on(server)))


def stored_threads(client: FakeSupabaseClient) -> list[tuple[Any, ...]]:
    """What the database holds, without the source's own identifiers."""
    threads = []
    for conversation in rows_of(client, "conversations"):
        messages = [
            row
            for row in rows_of(client, "messages")
            if row["conversation_id"] == conversation["id"]
        ]
        threads.append(
            (
                conversation["relevance"],
                conversation["subject"],
                tuple(sorted(str(row["direction"]) for row in messages)),
                tuple(sorted(str(row["body"]) for row in messages)),
            )
        )
    return sorted(threads, key=str)


def people(client: FakeSupabaseClient) -> set[str]:
    """Everybody the collector created."""
    return {str(row["full_name"]) for row in rows_of(client, "people")}


# --- Configuration ------------------------------------------------------------


def test_outlook_stays_the_mailbox_when_nothing_is_said(settings: Settings) -> None:
    assert settings.mail_sources == (MailSource.OUTLOOK,)
    assert settings.outlook_enabled
    assert not settings.imap_enabled


def test_gmail_alone_is_a_complete_set_up(
    valid_environment: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MAIL_SOURCES", "imap")
    monkeypatch.setenv("IMAP_PROVIDER", " Gmail ")
    monkeypatch.setenv("IMAP_USERNAME", "sam@gmail.example")

    settings = config.get_settings()

    assert not settings.outlook_enabled
    assert settings.imap_server == ("imap.gmail.com", 993)
    assert imap_account(settings).company == "Google"


def test_a_custom_server_is_used_as_written(
    valid_environment: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MAIL_SOURCES", "outlook, imap")
    monkeypatch.setenv("IMAP_HOST", "Mail.Example.org")
    monkeypatch.setenv("IMAP_PORT", "10993")
    monkeypatch.setenv("IMAP_USERNAME", "sam@example.org")

    settings = config.get_settings()

    assert settings.mail_sources == (MailSource.OUTLOOK, MailSource.IMAP)
    assert settings.imap_server == ("mail.example.org", 10993)


@pytest.mark.parametrize(
    ("variables", "named"),
    [
        ({"MAIL_SOURCES": " , "}, "MAIL_SOURCES"),
        ({"MAIL_SOURCES": "outlook,pigeon"}, "MAIL_SOURCES"),
        ({"MAIL_SOURCES": "imap", "IMAP_PROVIDER": "gmail"}, "IMAP_USERNAME"),
        ({"MAIL_SOURCES": "imap", "IMAP_USERNAME": "sam@example.org"}, "IMAP_HOST"),
        ({"IMAP_HOST": "https://mail.example.org"}, "IMAP_HOST"),
        ({"IMAP_PORT": "70000"}, "IMAP_PORT"),
        ({"IMAP_PROVIDER": "hotmail"}, "IMAP_PROVIDER"),
    ],
)
def test_a_mailbox_setting_that_cannot_work_is_refused(
    valid_environment: None,
    monkeypatch: pytest.MonkeyPatch,
    variables: dict[str, str],
    named: str,
) -> None:
    for name, value in variables.items():
        monkeypatch.setenv(name, value)

    with pytest.raises(ConfigurationError, match=named):
        config.get_settings()


def test_only_the_configured_mailboxes_are_opened(
    repositories: Repositories, settings: Settings, clock: FixedClock
) -> None:
    both = settings.model_copy(
        update={
            "mail_sources": (MailSource.OUTLOOK, MailSource.IMAP),
            "imap_provider": ImapProvider.GMAIL,
            "imap_username": "sam@gmail.example",
        }
    )

    kinds = [source.kind for source in configured_mailboxes(repositories, both, clock)]

    assert kinds == [MailSource.OUTLOOK, MailSource.IMAP]


# --- Collecting ---------------------------------------------------------------


def test_the_noise_rules_judge_an_imap_mailbox_exactly_like_outlook(
    settings: Settings, clock: FixedClock
) -> None:
    graph_client, imap_client = FakeSupabaseClient(), FakeSupabaseClient()
    graph_repositories = build_repositories(as_client(graph_client))
    imap_repositories = build_repositories(as_client(imap_client))

    collect_email(graph_repositories, settings, clock)
    EmailCollector(
        imap_repositories, settings, clock, JOB_SEARCH_RULES, [imap_source(outlook_twin())]
    ).collect()

    assert stored_threads(imap_client) == stored_threads(graph_client)
    assert people(imap_client) == people(graph_client) == {"Élodie Martin"}


def test_a_newsletter_read_over_imap_keeps_no_subject_and_no_body(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    server = outlook_twin()

    EmailCollector(repositories, settings, clock, JOB_SEARCH_RULES, [imap_source(server)]).collect()

    noise = [row for row in rows_of(fake_client, "conversations") if row["relevance"] == "noise"]
    assert [row["subject"] for row in noise] == [None]
    body_fetches = [
        entry
        for entry in server.log
        if entry[:2] == ("UID", "FETCH") and "HEADER.FIELDS" not in entry[3]
    ]
    assert len(body_fetches) == 2  # the two messages of the kept thread, never the newsletter


def test_a_kept_threads_bodies_are_read_with_one_command_per_folder(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    server = outlook_twin()
    elodie = "Élodie Martin <elodie.martin@acme.example>"
    chain = "<h1@acme.example> <r1@mailbox.example>"
    server.folders["INBOX"].append(
        StoredMessage(
            3,
            mail(
                sender=elodie,
                to=OWNER,
                subject="RE: Coffee next week?",
                body="Tuesday at ten?",
                sent=moment(11, 9),
                message_id="<h2@acme.example>",
                references=chain,
                in_reply_to="<r1@mailbox.example>",
            ),
            moment(11, 9),
        )
    )
    server.folders[SENT].append(
        StoredMessage(
            2,
            mail(
                sender=f"Sam Rivera <{OWNER}>",
                to=elodie,
                subject="RE: Coffee next week?",
                body="Tuesday at ten it is.",
                sent=moment(11, 10),
                message_id="<r2@mailbox.example>",
                references=f"{chain} <h2@acme.example>",
                in_reply_to="<h2@acme.example>",
            ),
            moment(11, 10),
        )
    )

    EmailCollector(repositories, settings, clock, JOB_SEARCH_RULES, [imap_source(server)]).collect()

    assert sorted(body_fetches(server)) == ["1,2", "2,3"]
    kept = sorted(
        (str(row["sent_at"]), row["direction"], row["body"])
        for row in rows_of(fake_client, "messages")
        if row["body"] is not None
    )
    assert [(direction, body) for _sent_at, direction, body in kept] == [
        ("inbound", "Made-up body text."),
        ("outbound", "Made-up body text."),
        ("inbound", "Tuesday at ten?"),
        ("outbound", "Tuesday at ten it is."),
    ]
    assert writes_sent(server) == []


def test_a_reply_filed_in_sent_is_outbound_even_from_an_unlisted_address(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    server = outlook_twin()
    server.folders[SENT][0].raw = server.folders[SENT][0].raw.replace(
        OWNER.encode(), b"sam.alias@elsewhere.example", 1
    )

    EmailCollector(repositories, settings, clock, JOB_SEARCH_RULES, [imap_source(server)]).collect()

    directions = sorted(str(row["direction"]) for row in rows_of(fake_client, "messages"))
    assert directions == ["inbound", "inbound", "outbound"]
    assert people(fake_client) == {"Élodie Martin"}


def test_one_mailbox_failing_does_not_lose_the_other(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    @asynccontextmanager
    async def refused() -> AsyncIterator[MailboxReader]:
        message = "Google refused the app password"
        raise MailboxPasswordError(message)
        yield  # pragma: no cover - makes this a generator

    sources = [imap_source(outlook_twin()), MailboxSource(MailSource.IMAP, refused)]

    with pytest.raises(MailboxPasswordError):
        EmailCollector(repositories, settings, clock, JOB_SEARCH_RULES, sources).collect()

    assert len(rows_of(fake_client, "conversations")) == 2


class _SlowEmptyMailbox:
    """An empty mailbox that notes when its reading starts and ends."""

    def __init__(self, name: str, diary: list[str]) -> None:
        self._name = name
        self._diary = diary
        self.window_capped = False

    async def list_messages_since(self, since: datetime) -> list[MailMessage]:
        self._diary.append(f"{self._name} started")
        await asyncio.sleep(0)
        self._diary.append(f"{self._name} finished")
        return []

    async def list_thread(self, conversation_id: str) -> list[MailMessage]:
        return []

    async def fetch_body(self, message_id: str) -> str:
        return ""

    async def fetch_bodies(self, message_ids: Sequence[str]) -> list[str]:
        return ["" for _ in message_ids]


# --- A mailbox read only in part ----------------------------------------------


@pytest.fixture
def small_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """A cap of one message a folder, so the test mailbox overflows it."""
    monkeypatch.setattr("tracker.infrastructure.imap.reader.IMAP_MAX_MESSAGES_PER_FOLDER", 1)


@pytest.mark.usefixtures("small_cap")
def test_a_mailbox_read_in_part_stores_what_it_read_and_says_so(
    repositories: Repositories,
    settings: Settings,
    clock: FixedClock,
    fake_client: FakeSupabaseClient,
) -> None:
    collector = EmailCollector(
        repositories, settings, clock, JOB_SEARCH_RULES, [imap_source(outlook_twin())]
    )

    with pytest.raises(MailboxWindowCappedError):
        collector.collect()

    assert rows_of(fake_client, "conversations")


@pytest.mark.usefixtures("small_cap")
def test_a_mailbox_that_failed_outranks_one_read_in_part(
    repositories: Repositories, settings: Settings, clock: FixedClock
) -> None:
    @asynccontextmanager
    async def refused() -> AsyncIterator[MailboxReader]:
        message = "Google refused the app password"
        raise MailboxPasswordError(message)
        yield  # pragma: no cover - makes this a generator

    sources = [imap_source(outlook_twin()), MailboxSource(MailSource.IMAP, refused)]

    with pytest.raises(MailboxPasswordError):
        EmailCollector(repositories, settings, clock, JOB_SEARCH_RULES, sources).collect()


@pytest.mark.usefixtures("small_cap")
def test_a_mailbox_read_in_part_is_recorded_as_a_failed_step_the_owner_reads(
    repositories: Repositories, settings: Settings, clock: FixedClock
) -> None:
    source = imap_source(outlook_twin())
    collector = EmailCollector(repositories, settings, clock, JOB_SEARCH_RULES, [source])
    recorder = RunRecorder(repositories, clock)
    run = recorder.start(RunTrigger.GITHUB)
    email = Source(Channel.EMAIL, RunStep.COLLECT_EMAIL, collector.read)
    outcome = AllSourcesCollector([[email]]).collect()

    record_outcomes(recorder, run.id, outcome)

    step = recorder.find_step(run.id, RunStep.COLLECT_EMAIL)
    assert step is not None
    assert (step.status, step.error_code) == (RunStatus.FAILED, "mailbox_window_capped")
    assert (step.items_found, step.items_new) == (1, 1)
    problem = explain(RunStep.COLLECT_EMAIL, step.error_code)
    assert "newest 10,000 messages" in problem.what_happened
    assert "mailbox_window_capped" not in problem.what_happened + problem.what_to_do


@pytest.fixture
def only_a_capped_mailbox(
    monkeypatch: pytest.MonkeyPatch,
    small_cap: None,  # noqa: ARG001 - a fixture used for its effect
    repositories: Repositories,
    settings: Settings,
    clock: FixedClock,
) -> None:
    """Point ``tracker collect all`` at one IMAP mailbox that overflows the cap, alone."""
    collector = EmailCollector(
        repositories, settings, clock, JOB_SEARCH_RULES, [imap_source(outlook_twin())]
    )
    only_the_mailbox = ((Source(Channel.EMAIL, RunStep.COLLECT_EMAIL, collector.read),),)
    monkeypatch.setattr("tracker.cli.commands.collect._wiring", lambda: (settings, repositories))
    monkeypatch.setattr("tracker.cli.commands.collect._rules", lambda _repos: JOB_SEARCH_RULES)
    monkeypatch.setattr("tracker.cli.commands.collect.SystemClock", lambda _zone: clock)
    monkeypatch.setattr("tracker.cli.commands.collect._sources", lambda *_: only_the_mailbox)


@pytest.mark.usefixtures("only_a_capped_mailbox")
def test_a_mailbox_read_in_part_alone_still_counts_as_collected_so_the_run_assesses_it(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    clock: FixedClock,
) -> None:
    """The common Gmail-only set-up: what was stored must be tidied and assessed the same run."""
    recorder = RunRecorder(repositories, clock)
    run = recorder.start(RunTrigger.GITHUB)

    result = CliRunner().invoke(build_cli(), ["collect", "all", "--record"])

    assert result.exit_code == 0
    lines = result.output.splitlines()
    counts = lines.index("conversations found: 1 (new: 1, noise: 0)")
    assert lines[counts - 1] == "channel: email"
    assert lines[counts + 4] == "read in part · code=mailbox_window_capped"
    assert "sources collected: 1" in lines
    assert lines[-1] == "steps recorded"
    assert rows_of(fake_client, "conversations")
    recorder.record_step(run.id, StepOutcome(RunStep.ASSESS, StepResult.SUCCESS))
    assert recorder.finish(run.id).status is RunStatus.PARTIAL


@pytest.mark.usefixtures("only_a_capped_mailbox")
def test_by_hand_a_mailbox_read_in_part_prints_its_counts_and_ends_as_a_failure(
    fake_client: FakeSupabaseClient,
) -> None:
    result = CliRunner().invoke(build_cli(), ["collect", "all"])

    assert result.exit_code != 0
    assert "read in part · code=mailbox_window_capped" in result.output.splitlines()
    assert rows_of(fake_client, "conversations")
    assert rows_of(fake_client, "run_step_logs") == []


def test_the_next_window_starts_from_a_read_that_hit_the_cap(
    repositories: Repositories,
) -> None:
    """The reader takes the newest mail, so staying further back would never reach the rest."""
    earlier = RunLog(
        started_at=datetime(2026, 9, 10, 7, 0, tzinfo=UTC),
        status=RunStatus.SUCCESS,
        trigger=RunTrigger.GITHUB,
    )
    capped = RunLog(
        started_at=datetime(2026, 9, 17, 7, 0, tzinfo=UTC),
        status=RunStatus.PARTIAL,
        trigger=RunTrigger.GITHUB,
    )
    repositories.run_logs.bulk_upsert([earlier, capped])
    repositories.run_step_logs.bulk_upsert(
        [
            RunStepLog(run_id=earlier.id, step=RunStep.COLLECT_EMAIL, status=RunStatus.SUCCESS),
            RunStepLog(
                run_id=capped.id,
                step=RunStep.COLLECT_EMAIL,
                status=RunStatus.FAILED,
                error_code="mailbox_window_capped",
            ),
        ]
    )

    assert last_collected_at(repositories, RunStep.COLLECT_EMAIL) == capped.started_at


def test_a_mailbox_that_failed_outright_does_not_move_the_window(
    repositories: Repositories,
) -> None:
    earlier = RunLog(
        started_at=datetime(2026, 9, 10, 7, 0, tzinfo=UTC),
        status=RunStatus.SUCCESS,
        trigger=RunTrigger.GITHUB,
    )
    failed = RunLog(
        started_at=datetime(2026, 9, 17, 7, 0, tzinfo=UTC),
        status=RunStatus.FAILED,
        trigger=RunTrigger.GITHUB,
    )
    repositories.run_logs.bulk_upsert([earlier, failed])
    repositories.run_step_logs.bulk_upsert(
        [
            RunStepLog(run_id=earlier.id, step=RunStep.COLLECT_EMAIL, status=RunStatus.SUCCESS),
            RunStepLog(
                run_id=failed.id,
                step=RunStep.COLLECT_EMAIL,
                status=RunStatus.FAILED,
                error_code="source_unavailable",
            ),
        ]
    )

    assert last_collected_at(repositories, RunStep.COLLECT_EMAIL) == earlier.started_at


def test_two_mailboxes_are_read_at_the_same_time(
    repositories: Repositories,
    settings: Settings,
    clock: FixedClock,
) -> None:
    diary: list[str] = []

    def source(name: str) -> MailboxSource:
        @asynccontextmanager
        async def opened() -> AsyncIterator[MailboxReader]:
            yield _SlowEmptyMailbox(name, diary)

        return MailboxSource(MailSource.IMAP, opened)

    sources = [source("first"), source("second")]

    EmailCollector(repositories, settings, clock, JOB_SEARCH_RULES, sources).collect()

    assert diary == ["first started", "second started", "first finished", "second finished"]


def test_a_missing_app_password_is_a_password_problem(
    repositories: Repositories, settings: Settings, clock: FixedClock
) -> None:
    gmail_only = settings.model_copy(
        update={
            "mail_sources": (MailSource.IMAP,),
            "imap_provider": ImapProvider.GMAIL,
            "imap_username": "sam@gmail.example",
        }
    )

    with pytest.raises(MailboxPasswordError, match="no app password is saved for your Gmail"):
        EmailCollector(repositories, gmail_only, clock, JOB_SEARCH_RULES).collect()


def test_the_app_password_is_stored_encrypted_under_the_mailbox_name(
    repositories: Repositories, fake_client: FakeSupabaseClient, clock: FixedClock
) -> None:
    store = SecretStore(repositories.app_secrets, SecretStr(TEST_ENCRYPTION_KEY), clock)

    store.put_secret(imap_password_name(" Sam@Gmail.Example "), "abcdefghijklmnop")

    [row] = rows_of(fake_client, "app_secrets")
    assert row["name"] == "imap_app_password:sam@gmail.example"
    assert "abcdefghijklmnop" not in str(row["encrypted_value"])


def test_without_outlook_the_calendar_is_not_configured(
    repositories: Repositories, settings: Settings, clock: FixedClock
) -> None:
    gmail_only = settings.model_copy(update={"mail_sources": (MailSource.IMAP,)})

    report = CalendarCollector(repositories, gmail_only, clock, JOB_SEARCH_RULES).collect()

    assert report.channel is Channel.CALENDAR
    assert report.not_configured


# --- The run ------------------------------------------------------------------


def test_every_mailbox_is_recorded_under_the_one_email_step(settings: Settings) -> None:
    gmail_only = settings.model_copy(update={"mail_sources": (MailSource.IMAP,)})

    assert RunStep.COLLECT_EMAIL not in unconfigured_steps(gmail_only)
    assert RunStep.COLLECT_CALENDAR in unconfigured_steps(gmail_only)
    assert RunStep.COLLECT_CALENDAR not in unconfigured_steps(settings)


def test_a_refused_app_password_is_explained_with_the_providers_name() -> None:
    problem = explain(RunStep.COLLECT_EMAIL, "mailbox_password_refused", ImapProvider.GMAIL)

    assert problem.what_happened == (
        "Your Gmail could not be read this morning: Google refused the app password."
    )
    assert "tracker setup mailbox" in problem.what_to_do
    assert "Renew a mailbox app password" in problem.what_to_do


def test_a_refused_microsoft_sign_in_keeps_its_own_words() -> None:
    problem = explain(RunStep.COLLECT_EMAIL, "source_auth_failed", ImapProvider.GMAIL)

    assert "Microsoft refused" in problem.what_happened


def test_the_daily_recipe_records_every_mailbox_under_a_real_step() -> None:
    recipe_file = config.REPOSITORY_ROOT / ".claude" / "commands" / "daily-run.md"
    recipe = recipe_file.read_text(encoding="utf-8")

    steps = set(re.findall(r"--step (\w+)", recipe))

    assert steps <= {step.value for step in RunStep}
    # The collection records its own steps, every mailbox under the e-mail one
    # (see test_all_sources.py); the recipe only has to run that one command.
    assert "uv run tracker collect all --record" in recipe
    assert "collect imap" not in recipe
    assert MailboxPasswordError.code in recipe


def test_the_set_up_checks_a_password_live_and_keeps_it_encrypted(
    fake_client: FakeSupabaseClient, clock: FixedClock
) -> None:
    server = outlook_twin()
    connection = ImapConnection(lambda _url, _key: as_client(fake_client), clock, server.connect)
    access = StoreAccess(
        "https://sample-project.supabase.co", SecretStr("key"), SecretStr(TEST_ENCRYPTION_KEY)
    )

    survey = asyncio.run(connection.check(GMAIL_ACCOUNT, SecretStr(APP_PASSWORD), moment(1, 0)))
    asyncio.run(connection.save_password(access, GMAIL_ACCOUNT.username, SecretStr(APP_PASSWORD)))

    assert (survey.inbox_messages, survey.sent_folder) == (2, SENT)
    assert asyncio.run(connection.has_password(access, GMAIL_ACCOUNT.username))
    assert writes_sent(server) == []


def test_the_set_up_signs_in_to_the_sending_server_without_sending(
    fake_client: FakeSupabaseClient, clock: FixedClock
) -> None:
    smtp = FakeSmtp()
    connection = ImapConnection(
        lambda _url, _key: as_client(fake_client),
        clock,
        smtp_connector=lambda *_: smtp,
    )
    account = SmtpAccount("smtp.mail.example", 587, "sam", "Mail", "Mail Inc.")

    asyncio.run(connection.check_sending(account, SecretStr(APP_PASSWORD)))

    assert smtp.calls == ["starttls", "login sam", "quit"]
    assert smtp.sent == []
