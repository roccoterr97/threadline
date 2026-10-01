"""Choosing mailboxes: configuration, collection over IMAP, and what the run records.

A Gmail (or any IMAP) mailbox must be judged exactly like an Outlook one: the
same noise rules, the same people, the same directions. These tests run the
mail collector on the fake IMAP server from :mod:`tests.imap_world` and compare
it with the Graph path of :mod:`tests.test_collectors`.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import SecretStr

from tests.conftest import JOB_SEARCH_RULES, TEST_ENCRYPTION_KEY, FakeSupabaseClient, as_client
from tests.imap_world import (
    APP_PASSWORD,
    GMAIL_ACCOUNT,
    FakeImapServer,
    StoredMessage,
    mail,
    session_on,
    writes_sent,
)
from tests.test_collectors import collect_email, rows_of
from tracker.domain.enums import Channel, RunStep
from tracker.domain.mail import MailMessage
from tracker.infrastructure.imap.connection import ImapConnection, StoreAccess
from tracker.infrastructure.imap.reader import ImapMailbox
from tracker.infrastructure.secret_store import SecretStore, imap_password_name
from tracker.repositories import Repositories, build_repositories
from tracker.services.collection.calendar_collector import CalendarCollector
from tracker.services.collection.email_collector import EmailCollector
from tracker.services.collection.mailbox import MailboxReader, MailboxSource
from tracker.services.collection.mailboxes import configured_mailboxes, imap_account
from tracker.services.runs.run_recorder import unconfigured_steps
from tracker.services.summary.problem_messages import explain
from tracker.shared import config
from tracker.shared.clock import FixedClock
from tracker.shared.config import Settings
from tracker.shared.constants.mailbox import ImapProvider, MailSource
from tracker.shared.errors import ConfigurationError, MailboxPasswordError

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

    async def list_messages_since(self, since: datetime) -> list[MailMessage]:
        self._diary.append(f"{self._name} started")
        await asyncio.sleep(0)
        self._diary.append(f"{self._name} finished")
        return []

    async def list_thread(self, conversation_id: str) -> list[MailMessage]:
        return []

    async def fetch_body(self, message_id: str) -> str:
        return ""


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
    recipe = (config.REPOSITORY_ROOT / ".claude" / "commands" / "daily-run.md").read_text()

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
