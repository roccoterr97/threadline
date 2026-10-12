"""Telegram: the rules, the collector behind a fake reader, and the Telethon adapter.

No test reaches Telegram. The collector is given a fake reader through its
port; the adapter is given a fake Telethon client that answers, or raises
Telethon's own errors, the way Telegram would.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest
from pydantic import SecretStr
from telethon import TelegramClient, errors, types
from typer.testing import CliRunner

from tests.conftest import JOB_SEARCH_RULES, FakeSupabaseClient
from tests.test_collectors import conversation_named, messages_of, rows_of
from tracker.cli.main import build_cli
from tracker.domain.enums import Channel, Direction, Relevance, RunStep, RunTrigger
from tracker.domain.models import Person, PersonIdentity
from tracker.domain.telegram import (
    ChatKind,
    MediaKind,
    TelegramAccount,
    TelegramApp,
    TelegramChat,
    TelegramMessage,
    display_name,
    is_person_chat,
    message_body,
)
from tracker.infrastructure.telegram.connection import build_client
from tracker.infrastructure.telegram.reader import TelethonReader, open_telegram
from tracker.repositories import Repositories
from tracker.services.collection.all_sources import (
    AllSourcesCollector,
    Source,
    record_outcomes,
)
from tracker.services.collection.models import NOT_CONFIGURED_LINE
from tracker.services.collection.telegram_collector import TelegramCollector, telegram_account
from tracker.services.collection.telegram_reader import TelegramReader
from tracker.services.doctor.checks import TelegramCheck
from tracker.services.doctor.models import CheckStatus
from tracker.services.doctor.service import DoctorService
from tracker.services.runs.run_recorder import RunRecorder, unconfigured_steps
from tracker.services.summary.problem_messages import explain
from tracker.shared import config
from tracker.shared.clock import FixedClock
from tracker.shared.config import Settings
from tracker.shared.constants.telegram import (
    TELEGRAM_MAX_MESSAGES_PER_CHAT,
    TELEGRAM_SERVICE_USER_ID,
)
from tracker.shared.errors import (
    ConfigurationError,
    SourceAuthError,
    SourceUnavailableError,
    TelegramFloodWaitError,
)

NOW = datetime(2026, 9, 18, 7, 0, tzinfo=UTC)
RECENT = NOW - timedelta(days=2)
LONG_AGO = NOW - timedelta(days=90)
SESSION = "1BVtsOK4made-up-telegram-session"
# Made up, and joined from parts so the secret scan does not take it for a real key.
API_HASH = "".join(["0123", "4567", "89ab", "cdef"]) * 2

ANA = TelegramChat(chat_id=1001, kind=ChatKind.PERSON, first_name="Ana", last_name="Lopes")


# --- The rules ------------------------------------------------------------------


@pytest.mark.parametrize(
    "chat",
    [
        TelegramChat(chat_id=1, kind=ChatKind.GROUP),
        TelegramChat(chat_id=2, kind=ChatKind.CHANNEL),
        TelegramChat(chat_id=3, kind=ChatKind.PERSON, first_name="Helper", is_bot=True),
        TelegramChat(chat_id=4, kind=ChatKind.PERSON, first_name="Me", is_self=True),
        TelegramChat(chat_id=5, kind=ChatKind.PERSON, is_deleted=True),
        TelegramChat(chat_id=6, kind=ChatKind.PERSON, first_name="Support", is_support=True),
        TelegramChat(chat_id=TELEGRAM_SERVICE_USER_ID, kind=ChatKind.PERSON, first_name="Telegram"),
    ],
)
def test_only_a_private_chat_with_a_real_person_is_a_conversation(chat: TelegramChat) -> None:
    assert not is_person_chat(chat)
    assert is_person_chat(ANA)


def test_a_person_is_named_by_their_name_else_their_username() -> None:
    assert display_name(ANA) == "Ana Lopes"
    assert display_name(TelegramChat(1, ChatKind.PERSON, username="ana_l")) == "@ana_l"
    assert display_name(TelegramChat(1, ChatKind.PERSON)) == ""


@pytest.mark.parametrize(
    ("message", "body"),
    [
        (TelegramMessage(1, NOW, outgoing=False, text="Hello"), "Hello"),
        (TelegramMessage(1, NOW, outgoing=False, media=MediaKind.PHOTO), "[photo]"),
        (
            TelegramMessage(1, NOW, outgoing=False, text="the deck", media=MediaKind.FILE),
            "[file] the deck",
        ),
        (TelegramMessage(1, NOW, outgoing=True, media=MediaKind.VOICE), "[voice message]"),
    ],
)
def test_a_message_keeps_its_text_and_marks_what_it_carried(
    message: TelegramMessage, body: str
) -> None:
    assert message_body(message) == body


# --- The collector, behind a fake reader ----------------------------------------


@dataclass
class FakeReader:
    """Telegram's chats and messages, as the port hands them over."""

    chats: list[TelegramChat] = field(default_factory=list)
    messages: dict[int, list[TelegramMessage]] = field(default_factory=dict)
    failure: Exception | None = None
    asked_since: list[datetime] = field(default_factory=list)
    histories_read: list[int] = field(default_factory=list)
    limits: list[int] = field(default_factory=list)
    opened: list[TelegramAccount] = field(default_factory=list)

    async def account_name(self) -> str:
        return "Sam Rivera"

    async def chats_since(self, since: datetime) -> Sequence[TelegramChat]:
        self.asked_since.append(since)
        if self.failure is not None:
            raise self.failure
        return [chat for chat in self.chats if (chat.last_message_at or since) >= since]

    async def recent_messages(self, chat: TelegramChat, limit: int) -> Sequence[TelegramMessage]:
        self.histories_read.append(chat.chat_id)
        self.limits.append(limit)
        return self.messages.get(chat.chat_id, [])[:limit]

    @asynccontextmanager
    async def open(self, account: TelegramAccount) -> AsyncIterator[TelegramReader]:
        self.opened.append(account)
        yield self


@pytest.fixture
def telegram_settings(valid_environment: None, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Configuration with Telegram set up."""
    monkeypatch.setenv("TELEGRAM_API_ID", "1234567")
    monkeypatch.setenv("TELEGRAM_API_HASH", API_HASH)
    monkeypatch.setenv("TELEGRAM_SESSION", SESSION)
    config.reset_settings_cache()
    return config.get_settings()


def chat(chat_id: int, first_name: str, last: datetime = RECENT, **flags: Any) -> TelegramChat:
    return TelegramChat(
        chat_id=chat_id,
        kind=flags.pop("kind", ChatKind.PERSON),
        first_name=first_name,
        last_message_at=last,
        **flags,
    )


def conversation_with_ana() -> FakeReader:
    """Ana wrote, the owner answered with a photo, both inside the window."""
    return FakeReader(
        chats=[chat(1001, "Ana", last_name="Lopes")],
        messages={
            1001: [
                TelegramMessage(
                    11, RECENT, outgoing=True, text="here it is", media=MediaKind.PHOTO
                ),
                TelegramMessage(10, RECENT - timedelta(hours=1), outgoing=False, text="Send it?"),
            ]
        },
    )


def collect(
    repositories: Repositories, settings: Settings, reader: FakeReader, **options: Any
) -> Any:
    collector = TelegramCollector(
        repositories, settings, FixedClock(NOW), JOB_SEARCH_RULES, reader.open
    )
    return collector.collect(**options)


def test_a_private_chat_becomes_one_thread_with_its_direction_and_text(
    repositories: Repositories, fake_client: FakeSupabaseClient, telegram_settings: Settings
) -> None:
    report = collect(repositories, telegram_settings, conversation_with_ana())

    assert report.conversations_found == 1
    assert report.people_new == 1
    thread = conversation_named(fake_client, "1001")
    assert thread["channel"] == Channel.TELEGRAM.value
    assert thread["relevance"] == Relevance.UNSURE.value
    stored = {row["source_message_id"]: row for row in messages_of(fake_client, "1001")}
    assert stored["10"]["direction"] == Direction.INBOUND.value
    assert stored["10"]["body"] == "Send it?"
    assert stored["10"]["sender_identifier"] == "1001"
    assert stored["11"]["direction"] == Direction.OUTBOUND.value
    assert stored["11"]["body"] == "[photo] here it is"
    identity = rows_of(fake_client, "person_identities")[0]
    assert (identity["channel"], identity["identifier"]) == ("telegram", "1001")
    assert rows_of(fake_client, "people")[0]["full_name"] == "Ana Lopes"


def test_bots_groups_channels_notices_and_saved_messages_are_never_read(
    repositories: Repositories, fake_client: FakeSupabaseClient, telegram_settings: Settings
) -> None:
    reader = FakeReader(
        chats=[
            chat(1, "Helper", is_bot=True),
            chat(2, "", kind=ChatKind.GROUP),
            chat(3, "", kind=ChatKind.CHANNEL),
            chat(TELEGRAM_SERVICE_USER_ID, "Telegram"),
            chat(4, "Me", is_self=True),
        ],
        messages={n: [TelegramMessage(1, RECENT, outgoing=False, text="x")] for n in range(5)},
    )

    report = collect(repositories, telegram_settings, reader)

    assert reader.histories_read == []
    assert report.conversations_found == 0
    assert rows_of(fake_client, "conversations") == []
    assert rows_of(fake_client, "people") == []


def test_a_chat_with_nothing_in_the_window_stores_nothing(
    repositories: Repositories, fake_client: FakeSupabaseClient, telegram_settings: Settings
) -> None:
    reader = FakeReader(
        chats=[chat(1001, "Ana", last=LONG_AGO)],
        messages={1001: [TelegramMessage(1, LONG_AGO, outgoing=False, text="old")]},
    )

    report = collect(repositories, telegram_settings, reader)

    assert report.conversations_found == 0
    assert rows_of(fake_client, "messages") == []


def test_the_first_read_looks_back_thirty_days_and_reads_a_bounded_history(
    repositories: Repositories, telegram_settings: Settings
) -> None:
    reader = conversation_with_ana()

    collect(repositories, telegram_settings, reader)

    assert reader.asked_since == [NOW - timedelta(days=30)]
    assert reader.limits == [TELEGRAM_MAX_MESSAGES_PER_CHAT]


def test_an_explicit_start_beats_the_usual_window(
    repositories: Repositories, telegram_settings: Settings
) -> None:
    reader = conversation_with_ana()
    since = NOW - timedelta(days=3)

    collect(repositories, telegram_settings, reader, since=since)

    assert reader.asked_since == [since]


def test_a_second_run_changes_nothing(
    repositories: Repositories, fake_client: FakeSupabaseClient, telegram_settings: Settings
) -> None:
    collect(repositories, telegram_settings, conversation_with_ana())
    again = collect(repositories, telegram_settings, conversation_with_ana())

    assert again.conversations_new == 0
    assert again.messages_new == 0
    assert again.people_new == 0
    assert len(rows_of(fake_client, "messages")) == 2


def test_a_known_person_with_the_same_unique_name_is_joined_by_the_usual_rule(
    repositories: Repositories, fake_client: FakeSupabaseClient, telegram_settings: Settings
) -> None:
    person = Person(full_name="Ana Lopes")
    repositories.people.bulk_upsert([person])
    repositories.person_identities.bulk_upsert(
        [
            PersonIdentity(
                person_id=person.id,
                channel=Channel.EMAIL,
                identifier="ana@acme.example",
                display_name="Ana Lopes",
            )
        ]
    )

    report = collect(repositories, telegram_settings, conversation_with_ana())

    assert report.people_new == 0
    assert conversation_named(fake_client, "1001")["person_id"] == str(person.id)


def test_without_a_saved_login_telegram_is_skipped_before_any_request(
    repositories: Repositories, fake_client: FakeSupabaseClient, settings: Settings
) -> None:
    reader = conversation_with_ana()

    report = collect(repositories, settings, reader)

    assert report.as_lines() == ("channel: telegram", NOT_CONFIGURED_LINE)
    assert reader.opened == []
    assert fake_client.executed == []
    assert telegram_account(settings) is None
    assert RunStep.COLLECT_TELEGRAM in unconfigured_steps(settings)


def test_with_a_saved_login_telegram_is_a_step_of_the_run(telegram_settings: Settings) -> None:
    account = telegram_account(telegram_settings)

    assert account is not None
    assert account.app.api_id == 1234567
    assert account.session.get_secret_value() == SESSION
    assert RunStep.COLLECT_TELEGRAM not in unconfigured_steps(telegram_settings)


def test_the_saved_login_never_appears_in_the_settings_text(telegram_settings: Settings) -> None:
    assert SESSION not in repr(telegram_settings)
    assert API_HASH not in repr(telegram_settings)


def test_a_long_pause_is_recorded_as_the_telegram_step_and_the_others_carry_on(
    repositories: Repositories, fake_client: FakeSupabaseClient, telegram_settings: Settings
) -> None:
    reader = FakeReader(failure=TelegramFloodWaitError("Telegram asked for a pause"))
    collector = TelegramCollector(
        repositories, telegram_settings, FixedClock(NOW), JOB_SEARCH_RULES, reader.open
    )
    run = RunRecorder(repositories, FixedClock(NOW)).start(RunTrigger.MANUAL)

    outcomes = AllSourcesCollector(
        [[Source(Channel.TELEGRAM, RunStep.COLLECT_TELEGRAM, collector.read)]]
    ).collect()
    record_outcomes(RunRecorder(repositories, FixedClock(NOW)), run.id, outcomes)

    (step,) = rows_of(fake_client, "run_step_logs")
    assert step["step"] == "collect_telegram"
    assert step["status"] == "failed"
    assert step["error_code"] == "telegram_flood_wait"


def test_a_revoked_login_ends_the_collection_with_the_sign_in_code(
    repositories: Repositories, telegram_settings: Settings
) -> None:
    reader = FakeReader(failure=SourceAuthError("Telegram no longer accepts the login"))

    with pytest.raises(SourceAuthError):
        collect(repositories, telegram_settings, reader)


# --- The Telethon adapter, with a fake client -----------------------------------


@dataclass
class FakeTelethon:
    """The few Telethon client calls Threadline makes, answering like Telegram."""

    dialogs: list[Any] = field(default_factory=list)
    history: list[Any] = field(default_factory=list)
    authorised: bool = True
    raise_on_connect: Exception | None = None
    raise_on_read: Exception | None = None
    connected: bool = False
    disconnects: int = 0
    calls: list[str] = field(default_factory=list)

    async def connect(self) -> None:
        self.calls.append("connect")
        if self.raise_on_connect is not None:
            raise self.raise_on_connect
        self.connected = True

    async def is_user_authorized(self) -> bool:
        return self.authorised

    async def disconnect(self) -> None:
        self.disconnects += 1

    async def get_me(self) -> Any:
        self.calls.append("get_me")
        return types.User(id=42, first_name="Sam", last_name="Rivera")

    async def iter_dialogs(self, limit: int) -> AsyncIterator[Any]:
        self.calls.append(f"iter_dialogs:{limit}")
        if self.raise_on_read is not None:
            raise self.raise_on_read
        for dialog in self.dialogs:
            yield dialog

    async def iter_messages(self, peer: Any, limit: int) -> AsyncIterator[Any]:
        self.calls.append(f"iter_messages:{limit}")
        if self.raise_on_read is not None:
            raise self.raise_on_read
        for message in self.history[:limit]:
            yield message


def dialog(entity: Any, when: datetime | None, *, pinned: bool = False) -> SimpleNamespace:
    return SimpleNamespace(entity=entity, date=when, pinned=pinned)


def raw_message(
    message_id: int, *, out: bool = False, text: str = "", media: Any = None, **kinds: Any
) -> SimpleNamespace:
    """A Telethon message: text, media, and the property naming what the media is."""
    return SimpleNamespace(
        id=message_id, date=RECENT, out=out, message=text, media=media, action=None, **kinds
    )


def account() -> TelegramAccount:
    return TelegramAccount(TelegramApp(1234567, SecretStr(API_HASH)), SecretStr(SESSION))


async def read_with(fake: FakeTelethon) -> list[TelegramChat]:
    async with open_telegram(account(), lambda _account: cast(TelegramClient, fake)) as reader:
        return list(await reader.chats_since(NOW - timedelta(days=30)))


@pytest.mark.asyncio
async def test_the_chat_list_stops_at_the_first_old_chat_but_not_at_an_old_pinned_one() -> None:
    fake = FakeTelethon(
        dialogs=[
            dialog(types.User(id=1, first_name="Old pinned"), LONG_AGO, pinned=True),
            dialog(types.User(id=2, first_name="Ana", bot=False), RECENT),
            dialog(
                types.Channel(
                    id=3, title="News", photo=types.ChatPhotoEmpty(), date=None, megagroup=False
                ),
                RECENT,
            ),
            dialog(types.User(id=4, first_name="Too old"), LONG_AGO),
            dialog(types.User(id=5, first_name="Never reached"), RECENT),
        ]
    )

    chats = await read_with(fake)

    assert [(item.chat_id, item.kind) for item in chats] == [
        (2, ChatKind.PERSON),
        (3, ChatKind.CHANNEL),
    ]
    assert fake.disconnects == 1


@pytest.mark.asyncio
async def test_a_user_is_described_with_every_flag_the_rules_need() -> None:
    entity = types.User(
        id=9, first_name="Bob", last_name="Ng", username="bob", bot=True, is_self=False
    )

    (described,) = await read_with(FakeTelethon(dialogs=[dialog(entity, RECENT)]))

    assert described == TelegramChat(
        chat_id=9,
        kind=ChatKind.PERSON,
        first_name="Bob",
        last_name="Ng",
        username="bob",
        is_bot=True,
        last_message_at=RECENT,
    )


@pytest.mark.asyncio
async def test_media_becomes_a_mark_and_a_link_preview_stays_plain_text() -> None:
    fake = FakeTelethon(
        history=[
            raw_message(1, text="caption", media=object(), photo=object()),
            raw_message(2, media=object(), voice=object(), document=object()),
            raw_message(
                3,
                text="see https://x.example",
                media=types.MessageMediaWebPage(webpage=types.WebPageEmpty(id=1)),
            ),
            raw_message(4, media=object()),
            raw_message(5),
            SimpleNamespace(
                id=6, date=RECENT, out=True, action=types.MessageActionPhoneCall(call_id=1)
            ),
            SimpleNamespace(
                id=7, date=RECENT, out=False, action=types.MessageActionContactSignUp()
            ),
        ]
    )
    reader = TelethonReader(cast(TelegramClient, fake))

    found = await reader.recent_messages(ANA, 50)

    assert [(item.message_id, item.text, item.media) for item in found] == [
        (1, "caption", MediaKind.PHOTO),
        (2, "", MediaKind.VOICE),
        (3, "see https://x.example", None),
        (4, "", MediaKind.OTHER),
        (6, "", MediaKind.CALL),
    ]
    assert fake.calls == ["iter_messages:50"]


@pytest.mark.parametrize(
    ("raised", "expected", "code"),
    [
        (
            errors.FloodWaitError(request=None, capture=3600),
            TelegramFloodWaitError,
            "telegram_flood_wait",
        ),
        (errors.AuthKeyUnregisteredError(request=None), SourceAuthError, "source_auth_failed"),
        (errors.SessionRevokedError(request=None), SourceAuthError, "source_auth_failed"),
        (errors.AuthKeyDuplicatedError(request=None), SourceAuthError, "source_auth_failed"),
        (
            errors.ServerError(request=None, message="INTERNAL"),
            SourceUnavailableError,
            "source_unavailable",
        ),
        (ConnectionError("network down"), SourceUnavailableError, "source_unavailable"),
    ],
)
@pytest.mark.asyncio
async def test_what_telegram_raises_becomes_a_plain_failure_with_a_stable_code(
    raised: Exception, expected: type[Exception], code: str
) -> None:
    fake = FakeTelethon(raise_on_read=raised)

    with pytest.raises(expected) as caught:
        await read_with(fake)

    assert getattr(caught.value, "code", None) == code
    assert caught.value.__cause__ is None
    assert fake.disconnects == 1


@pytest.mark.asyncio
async def test_a_revoked_login_tells_the_owner_to_log_in_again() -> None:
    fake = FakeTelethon(authorised=False)

    with pytest.raises(SourceAuthError) as caught:
        await read_with(fake)

    assert "uv run tracker setup telegram" in caught.value.message
    assert fake.calls == ["connect"]
    assert fake.disconnects == 1


@pytest.mark.asyncio
async def test_telegram_out_of_reach_is_an_outage() -> None:
    fake = FakeTelethon(raise_on_connect=OSError("unreachable"))

    with pytest.raises(SourceUnavailableError):
        await read_with(fake)

    assert fake.disconnects == 1


@pytest.mark.asyncio
async def test_the_account_name_proves_the_login() -> None:
    reader = TelethonReader(cast(TelegramClient, FakeTelethon()))

    assert await reader.account_name() == "Sam Rivera"


def test_a_saved_login_telethon_cannot_read_is_refused_without_repeating_it() -> None:
    with pytest.raises(ConfigurationError) as caught:
        build_client(TelegramApp(1234567, SecretStr(API_HASH)), "not-a-session")

    assert "not-a-session" not in caught.value.message
    assert "uv run tracker setup telegram" in caught.value.message


def test_a_client_is_made_with_updates_off_and_named_threadline() -> None:
    client = build_client(TelegramApp(1234567, SecretStr(API_HASH)), "")

    assert client.api_id == 1234567
    assert client.flood_sleep_threshold == 60


# --- What the owner reads: the summary, the doctor and the command line ---------


@pytest.mark.parametrize(
    ("code", "words"),
    [
        ("source_auth_failed", "uv run tracker setup telegram"),
        ("source_unavailable", "Telegram did not answer"),
        ("telegram_flood_wait", "Telegram asked Threadline to pause"),
        ("something_new", "Your Telegram chats could not be read"),
    ],
)
def test_a_failed_telegram_step_is_explained_in_plain_words(code: str, words: str) -> None:
    problem = explain(RunStep.COLLECT_TELEGRAM, code)

    assert words in f"{problem.what_happened} {problem.what_to_do}"
    assert code not in f"{problem.what_happened} {problem.what_to_do}"


@pytest.mark.asyncio
async def test_the_doctor_checks_the_saved_login_only_when_there_is_one() -> None:
    async def accepted() -> str:
        return "Sam Rivera"

    async def revoked() -> str:
        message = "Telegram no longer accepts Threadline's login"
        raise SourceAuthError(message)

    skipped = await TelegramCheck(None).run()
    healthy = await TelegramCheck(accepted).run()
    report = await DoctorService([TelegramCheck(revoked)]).run()

    assert skipped.status is CheckStatus.SKIPPED
    assert healthy.status is CheckStatus.OK
    assert "Sam Rivera" in healthy.detail
    assert report.results[0].status is CheckStatus.PROBLEM
    assert report.results[0].fix == "run 'uv run tracker setup telegram'"


def test_collect_telegram_without_a_login_says_not_configured(
    monkeypatch: pytest.MonkeyPatch, repositories: Repositories, settings: Settings
) -> None:
    monkeypatch.setattr("tracker.cli.commands.collect._wiring", lambda: (settings, repositories))
    monkeypatch.setattr("tracker.cli.commands.collect._rules", lambda _repos: JOB_SEARCH_RULES)

    result = CliRunner().invoke(build_cli(), ["collect", "telegram"])

    assert result.exit_code == 0
    assert result.output.splitlines()[-2:] == ["channel: telegram", NOT_CONFIGURED_LINE]
