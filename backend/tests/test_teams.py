"""Microsoft Teams chats: the separate sign-in, the chat reader and the collector.

Every payload is made up; only the shape follows Microsoft's documented
answers. Graph is faked with respx, so nothing here reaches the network.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import respx
from pydantic import SecretStr
from typer.testing import CliRunner

from tests.assessment_world import make_person
from tests.conftest import JOB_SEARCH_RULES, TEST_ENCRYPTION_KEY, FakeSupabaseClient, as_client
from tracker.cli.main import build_cli
from tracker.domain.enums import Channel, Direction, RunStep
from tracker.domain.models import PersonIdentity
from tracker.infrastructure.microsoft.auth import (
    TEAMS_SIGN_IN,
    TOKEN_URL,
    MicrosoftAuthenticator,
    login_urls,
)
from tracker.infrastructure.microsoft.teams import TeamsChats
from tracker.infrastructure.secret_store import (
    MICROSOFT_REFRESH_TOKEN,
    MICROSOFT_TEAMS_REFRESH_TOKEN,
    SecretStore,
)
from tracker.repositories import Repositories, build_repositories
from tracker.services.collection.teams_collector import TeamsCollector
from tracker.services.doctor.checks import TeamsCheck
from tracker.services.doctor.models import CheckStatus
from tracker.services.runs.run_recorder import unconfigured_steps
from tracker.services.summary.problem_messages import explain
from tracker.shared.clock import FixedClock
from tracker.shared.config import Settings
from tracker.shared.constants.collection import (
    MICROSOFT_TEAMS_SCOPE,
    MICROSOFT_TEAMS_TENANT,
)
from tracker.shared.errors import (
    AdminApprovalRequiredError,
    SourceAuthError,
    SourceUnavailableError,
    WorkAccountRequiredError,
)

TEAMS_DEVICE_CODE_URL, TEAMS_TOKEN_URL = login_urls(MICROSOFT_TEAMS_TENANT)
GRAPH_HOST = "graph.microsoft.com"
ME_PATH = "/v1.0/me"
CHATS_PATH = "/v1.0/me/chats"
OWNER_ID = "owner-0001"
HANNA_ID = "hanna-0002"
HANNA = "hanna.keller@northwind.example"
CHAT_ID = "19:hanna-and-sam@unq.gbl.spaces"


def messages_path(chat_id: str = CHAT_ID) -> str:
    """Where one chat's messages are listed."""
    return f"/v1.0/chats/{chat_id}/messages"


@pytest.fixture
def secret_store(fake_client: FakeSupabaseClient, clock: FixedClock) -> SecretStore:
    """A secret store on the in-memory database."""
    repositories = build_repositories(as_client(fake_client))
    return SecretStore(repositories.app_secrets, SecretStr(TEST_ENCRYPTION_KEY), clock)


@pytest.fixture
def teams_settings(settings: Settings) -> Settings:
    """The made-up configuration with Teams switched on."""
    return settings.model_copy(update={"teams_enabled": True})


def mock_teams_renewal(refresh_token: str = "new-teams-key") -> respx.Route:
    """Answer a Teams renewal with a fresh pair of keys."""
    return respx.post(TEAMS_TOKEN_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "made-up-teams-access-key",
                "refresh_token": refresh_token,
                "expires_in": 3599,
            },
        )
    )


def member(user_id: str, name: str, email: str | None) -> dict[str, Any]:
    """One chat member as Graph lists it."""
    return {
        "@odata.type": "#microsoft.graph.aadUserConversationMember",
        "userId": user_id,
        "displayName": name,
        "email": email,
    }


def chat(
    chat_id: str = CHAT_ID,
    *,
    chat_type: str = "oneOnOne",
    topic: str | None = None,
    members: list[dict[str, Any]] | None = None,
    last_message: str | None = "2026-09-17T10:00:00Z",
) -> dict[str, Any]:
    """One chat as Graph lists it, with its members and its last message."""
    return {
        "id": chat_id,
        "chatType": chat_type,
        "topic": topic,
        "members": members
        if members is not None
        else [
            member(OWNER_ID, "Sam Rivera", "sam@work.example"),
            member(HANNA_ID, "Hanna Keller", HANNA),
        ],
        "lastMessagePreview": None if last_message is None else {"createdDateTime": last_message},
    }


def message(
    message_id: str,
    *,
    sent: str = "2026-09-17T10:00:00Z",
    sender: str | None = HANNA_ID,
    name: str = "Hanna Keller",
    content: str = "Are you free on Thursday?",
    content_type: str = "text",
    message_type: str = "message",
    deleted: str | None = None,
    application: bool = False,
) -> dict[str, Any]:
    """One chat message as Graph lists it."""
    sender_block: dict[str, Any] | None = None
    if application:
        sender_block = {"application": {"id": "bot-1", "displayName": "Polls"}, "user": None}
    elif sender is not None:
        sender_block = {"user": {"id": sender, "displayName": name}, "application": None}
    return {
        "id": message_id,
        "messageType": message_type,
        "createdDateTime": sent,
        "deletedDateTime": deleted,
        "from": sender_block,
        "body": {"contentType": content_type, "content": content},
    }


def mock_graph(
    chats: list[dict[str, Any]],
    pages_by_chat: dict[str, list[dict[str, Any]]],
) -> dict[str, respx.Route]:
    """Answer who signed in, the chat listing and each chat's messages."""
    routes = {
        "me": respx.get(host=GRAPH_HOST, path=ME_PATH).mock(
            return_value=httpx.Response(
                200, json={"id": OWNER_ID, "displayName": "Sam Rivera", "mail": "Sam@Work.example"}
            )
        ),
        "chats": respx.get(host=GRAPH_HOST, path=CHATS_PATH).mock(
            return_value=httpx.Response(200, json={"value": chats})
        ),
    }
    for chat_id, items in pages_by_chat.items():
        routes[chat_id] = respx.get(host=GRAPH_HOST, path=messages_path(chat_id)).mock(
            return_value=httpx.Response(200, json={"value": items})
        )
    return routes


def store_teams_key(repositories: Repositories, clock: FixedClock) -> None:
    """Save a Teams sign-in key, as the set-up does."""
    SecretStore(repositories.app_secrets, SecretStr(TEST_ENCRYPTION_KEY), clock).put_secret(
        MICROSOFT_TEAMS_REFRESH_TOKEN, "old-teams-key"
    )


def rows(client: FakeSupabaseClient, table: str) -> list[dict[str, Any]]:
    """Read one table of the in-memory database."""
    return client.tables.get(table, [])


# --- The separate sign-in -------------------------------------------------------


@pytest.mark.asyncio
async def test_the_teams_sign_in_asks_work_accounts_for_chat_read_only(
    secret_store: SecretStore, clock: FixedClock, teams_settings: Settings
) -> None:
    with respx.mock:
        device = respx.post(TEAMS_DEVICE_CODE_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "user_code": "ABCD-EFGH",
                    "verification_uri": "https://microsoft.com/devicelogin",
                    "device_code": "device-1",
                    "interval": 0,
                },
            )
        )
        token = mock_teams_renewal("first-teams-key")
        authenticator = MicrosoftAuthenticator.for_teams(secret_store, clock, teams_settings)
        async with authenticator:
            prompt = await authenticator.request_device_code()
            await authenticator.wait_for_sign_in(prompt)

    assert "/organizations/" in TEAMS_DEVICE_CODE_URL
    form = httpx.QueryParams(device.calls.last.request.content.decode())
    assert form["scope"] == MICROSOFT_TEAMS_SCOPE
    assert token.called
    assert secret_store.get_secret(MICROSOFT_TEAMS_REFRESH_TOKEN) == "first-teams-key"
    assert secret_store.get_secret(MICROSOFT_REFRESH_TOKEN) is None


@pytest.mark.asyncio
async def test_renewing_teams_never_touches_the_outlook_key(
    secret_store: SecretStore, clock: FixedClock, teams_settings: Settings
) -> None:
    secret_store.put_secret(MICROSOFT_REFRESH_TOKEN, "outlook-key")
    secret_store.put_secret(MICROSOFT_TEAMS_REFRESH_TOKEN, "old-teams-key")

    with respx.mock:
        outlook = respx.post(TOKEN_URL)
        teams = mock_teams_renewal()
        authenticator = MicrosoftAuthenticator.for_teams(secret_store, clock, teams_settings)
        async with authenticator:
            assert await authenticator.access_token() == "made-up-teams-access-key"

    assert not outlook.called
    assert "Chat.Read" in teams.calls.last.request.content.decode()
    assert secret_store.get_secret(MICROSOFT_TEAMS_REFRESH_TOKEN) == "new-teams-key"
    assert secret_store.get_secret(MICROSOFT_REFRESH_TOKEN) == "outlook-key"


@pytest.mark.asyncio
async def test_without_a_teams_sign_in_the_owner_is_told_the_teams_command(
    secret_store: SecretStore, clock: FixedClock, teams_settings: Settings
) -> None:
    secret_store.put_secret(MICROSOFT_REFRESH_TOKEN, "outlook-key")

    async with MicrosoftAuthenticator.for_teams(secret_store, clock, teams_settings) as auth:
        with pytest.raises(SourceAuthError, match="tracker setup teams"):
            await auth.access_token()


def refusal(code: int, error: str = "invalid_grant") -> httpx.Response:
    """A refusal as Microsoft's sign-in endpoint words it."""
    return httpx.Response(
        400,
        json={
            "error": error,
            "error_description": f"AADSTS{code}: made-up description.",
            "error_codes": [code],
        },
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [65001, 90094, 53003])
async def test_an_organisation_that_blocks_the_application_is_named(
    secret_store: SecretStore, clock: FixedClock, teams_settings: Settings, code: int
) -> None:
    secret_store.put_secret(MICROSOFT_TEAMS_REFRESH_TOKEN, "old-teams-key")

    with respx.mock:
        respx.post(TEAMS_TOKEN_URL).mock(return_value=refusal(code))
        async with MicrosoftAuthenticator.for_teams(secret_store, clock, teams_settings) as auth:
            with pytest.raises(AdminApprovalRequiredError, match="IT admin has to allow"):
                await auth.access_token()


@pytest.mark.asyncio
async def test_a_personal_account_is_told_teams_needs_a_work_account(
    secret_store: SecretStore, clock: FixedClock, teams_settings: Settings
) -> None:
    prompt_payload = {
        "user_code": "C",
        "verification_uri": "https://microsoft.com/devicelogin",
        "device_code": "d",
        "interval": 0,
    }
    with respx.mock:
        respx.post(TEAMS_DEVICE_CODE_URL).mock(
            return_value=httpx.Response(200, json=prompt_payload)
        )
        respx.post(TEAMS_TOKEN_URL).mock(return_value=refusal(500200, "invalid_request"))
        async with MicrosoftAuthenticator.for_teams(secret_store, clock, teams_settings) as auth:
            prompt = await auth.request_device_code()
            with pytest.raises(WorkAccountRequiredError, match="work or school account"):
                await auth.wait_for_sign_in(prompt)


@pytest.mark.asyncio
async def test_a_revoked_teams_key_asks_for_a_new_sign_in(
    secret_store: SecretStore, clock: FixedClock, teams_settings: Settings
) -> None:
    secret_store.put_secret(MICROSOFT_TEAMS_REFRESH_TOKEN, "revoked-key")

    with respx.mock:
        respx.post(TEAMS_TOKEN_URL).mock(return_value=refusal(70008))
        async with MicrosoftAuthenticator.for_teams(secret_store, clock, teams_settings) as auth:
            with pytest.raises(SourceAuthError, match="sign in again") as raised:
                await auth.access_token()

    assert type(raised.value) is SourceAuthError


@pytest.mark.asyncio
async def test_the_outlook_sign_in_keeps_its_plain_refusal(
    secret_store: SecretStore, clock: FixedClock
) -> None:
    secret_store.put_secret(MICROSOFT_REFRESH_TOKEN, "outlook-key")

    with respx.mock:
        respx.post(TOKEN_URL).mock(return_value=refusal(65001))
        async with MicrosoftAuthenticator(secret_store, clock) as authenticator:
            with pytest.raises(SourceAuthError) as raised:
                await authenticator.access_token()

    assert raised.value.code == SourceAuthError.code


def test_the_teams_sign_in_keeps_its_own_key_and_permissions() -> None:
    assert TEAMS_SIGN_IN.secret_name == MICROSOFT_TEAMS_REFRESH_TOKEN
    assert TEAMS_SIGN_IN.scope == MICROSOFT_TEAMS_SCOPE
    assert "Chat.Read" in MICROSOFT_TEAMS_SCOPE
    assert "offline_access" in MICROSOFT_TEAMS_SCOPE
    assert MICROSOFT_TEAMS_TENANT == "organizations"


# --- The chat reader ------------------------------------------------------------


class _Tokens:
    """Hands out a made-up key without any sign-in."""

    async def access_token(self) -> str:
        return "made-up-teams-access-key"


@pytest.mark.asyncio
async def test_only_what_people_wrote_is_read_and_html_becomes_text(clock: FixedClock) -> None:
    items = [
        message(
            "m-html", content="<p>See you <b>Thursday</b></p><p>Hanna</p>", content_type="html"
        ),
        message("m-system", message_type="systemEventMessage", sender=None),
        message("m-deleted", deleted="2026-09-17T11:00:00Z"),
        message("m-bot", application=True),
        message("m-text", content="Plain words"),
    ]
    with respx.mock:
        mock_graph([chat()], {CHAT_ID: items})
        async with TeamsChats(_Tokens()) as teams:
            found = await teams.messages_since(CHAT_ID, clock.now().replace(month=8))

    assert [item.message_id for item in found] == ["m-html", "m-text"]
    assert found[0].text == "See you Thursday\n\nHanna"
    assert found[1].text == "Plain words"


@pytest.mark.asyncio
async def test_messages_are_paged_newest_first_and_stop_at_the_window(clock: FixedClock) -> None:
    start = clock.now().replace(day=1)  # 2026-09-01
    next_link = f"https://{GRAPH_HOST}{messages_path()}?$skiptoken=page-2"
    pages = {
        None: {
            "value": [message("m-3", sent="2026-09-15T09:00:00Z")],
            "@odata.nextLink": next_link,
        },
        "page-2": {
            "value": [
                message("m-2", sent="2026-09-02T09:00:00Z"),
                message("m-1", sent="2026-08-20T09:00:00Z"),
            ],
            "@odata.nextLink": f"https://{GRAPH_HOST}{messages_path()}?$skiptoken=page-3",
        },
    }

    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=pages[request.url.params.get("$skiptoken")])

    with respx.mock:
        route = respx.get(host=GRAPH_HOST, path=messages_path()).mock(side_effect=answer)
        async with TeamsChats(_Tokens()) as teams:
            found = await teams.messages_since(CHAT_ID, start)

    assert [item.message_id for item in found] == ["m-3", "m-2"]
    assert route.call_count == 2
    first = route.calls[0].request.url.params
    assert first["$orderby"] == "createdDateTime desc"
    assert "getAllMessages" not in str(route.calls[0].request.url)


@pytest.mark.asyncio
async def test_a_slow_down_answer_is_waited_out_as_microsoft_asks(
    clock: FixedClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    waits: list[float] = []

    async def record(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr("tracker.shared.http.SOURCE_RETRY_AFTER_CAP_SECONDS", 60.0)
    monkeypatch.setattr("tracker.shared.http.asyncio", SimpleNamespace(sleep=record))
    answers = iter(
        [
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(200, json={"value": [message("m-1")]}),
        ]
    )
    with respx.mock:
        respx.get(host=GRAPH_HOST, path=messages_path()).mock(side_effect=lambda _: next(answers))
        async with TeamsChats(_Tokens()) as teams:
            found = await teams.messages_since(CHAT_ID, clock.now().replace(month=8))

    assert waits == [7.0]
    assert [item.message_id for item in found] == ["m-1"]


@pytest.mark.asyncio
async def test_meeting_chats_and_chats_nobody_wrote_in_are_left_out() -> None:
    chats = [
        chat("19:meeting@thread.v2", chat_type="meeting"),
        chat("19:empty@thread.v2", last_message=None),
        chat(),
    ]
    with respx.mock:
        mock_graph(chats, {})
        async with TeamsChats(_Tokens()) as teams:
            listed = await teams.list_chats()

    assert [(item.chat_id, item.has_messages) for item in listed] == [
        ("19:empty@thread.v2", False),
        (CHAT_ID, True),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_a_refused_teams_read_asks_for_a_new_sign_in(status: int) -> None:
    with respx.mock:
        respx.get(host=GRAPH_HOST, path=CHATS_PATH).mock(return_value=httpx.Response(status))
        async with TeamsChats(_Tokens()) as teams:
            with pytest.raises(SourceAuthError, match="tracker setup teams"):
                await teams.list_chats()


@pytest.mark.asyncio
async def test_a_teams_outage_is_reported_as_unavailable() -> None:
    with respx.mock:
        respx.get(host=GRAPH_HOST, path=CHATS_PATH).mock(return_value=httpx.Response(500))
        async with TeamsChats(_Tokens()) as teams:
            with pytest.raises(SourceUnavailableError):
                await teams.list_chats()


# --- The collector --------------------------------------------------------------


def collect(
    repositories: Repositories,
    settings: Settings,
    clock: FixedClock,
    chats: list[dict[str, Any]],
    pages_by_chat: dict[str, list[dict[str, Any]]],
) -> dict[str, respx.Route]:
    """Run the Teams collector against made-up chats."""
    store_teams_key(repositories, clock)
    with respx.mock:
        mock_teams_renewal()
        routes = mock_graph(chats, pages_by_chat)
        TeamsCollector(repositories, settings, clock, JOB_SEARCH_RULES).collect()
    return routes


def test_a_chat_is_filed_under_the_person_by_their_e_mail_address(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    teams_settings: Settings,
    clock: FixedClock,
) -> None:
    items = [
        message("m-2", sent="2026-09-17T10:05:00Z", sender=OWNER_ID, name="Sam", content="Yes!"),
        message("m-1", sent="2026-09-17T10:00:00Z"),
    ]

    collect(repositories, teams_settings, clock, [chat()], {CHAT_ID: items})

    (thread,) = rows(fake_client, "conversations")
    (identity,) = rows(fake_client, "person_identities")
    stored = sorted(rows(fake_client, "messages"), key=lambda row: row["source_message_id"])
    assert thread["channel"] == Channel.TEAMS.value
    assert thread["source_conversation_id"] == CHAT_ID
    assert identity["channel"] == Channel.EMAIL.value
    assert identity["identifier"] == HANNA
    assert [row["direction"] for row in stored] == [
        Direction.INBOUND.value,
        Direction.OUTBOUND.value,
    ]
    assert stored[0]["sender_identifier"] == HANNA
    assert stored[1]["sender_identifier"] == "sam@work.example"
    assert stored[0]["body"] == "Are you free on Thursday?"


def test_a_teams_chat_joins_the_e_mail_record_of_the_same_person(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    teams_settings: Settings,
    clock: FixedClock,
) -> None:
    hanna = make_person("Hanna Keller")
    repositories.people.bulk_upsert([hanna])
    repositories.person_identities.bulk_upsert(
        [PersonIdentity(person_id=hanna.id, channel=Channel.EMAIL, identifier=HANNA)]
    )

    collect(repositories, teams_settings, clock, [chat()], {CHAT_ID: [message("m-1")]})

    (thread,) = rows(fake_client, "conversations")
    assert thread["person_id"] == str(hanna.id)
    assert len(rows(fake_client, "people")) == 1


def test_somebody_without_an_address_is_filed_under_their_teams_identifier(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    teams_settings: Settings,
    clock: FixedClock,
) -> None:
    guest = [member(OWNER_ID, "Sam", "sam@work.example"), member("guest-9", "Lou Guest", None)]
    items = [message("m-1", sender="guest-9", name="Lou Guest")]

    collect(repositories, teams_settings, clock, [chat(members=guest)], {CHAT_ID: items})

    (identity,) = rows(fake_client, "person_identities")
    (stored,) = rows(fake_client, "messages")
    assert identity["channel"] == Channel.TEAMS.value
    assert identity["identifier"] == "guest-9"
    assert stored["sender_identifier"] == "guest-9"


def test_a_group_chat_is_marked_and_a_chat_quiet_since_the_window_is_not_read(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    teams_settings: Settings,
    clock: FixedClock,
) -> None:
    group = chat(
        "19:group@thread.v2",
        chat_type="group",
        topic="Northwind hiring",
        members=[
            member(OWNER_ID, "Sam", "sam@work.example"),
            member(HANNA_ID, "Hanna Keller", HANNA),
            member("lee-3", "Lee Park", "lee.park@northwind.example"),
        ],
    )
    quiet = chat("19:quiet@thread.v2", last_message="2026-06-01T09:00:00Z")

    routes = collect(
        repositories,
        teams_settings,
        clock,
        [group, quiet],
        {"19:group@thread.v2": [message("m-1")], "19:quiet@thread.v2": [message("m-old")]},
    )

    (thread,) = rows(fake_client, "conversations")
    assert thread["subject"] == "[group] Northwind hiring"
    assert len(rows(fake_client, "person_identities")) == 2
    assert not routes["19:quiet@thread.v2"].called


def test_without_teams_set_up_nothing_is_read(
    repositories: Repositories, settings: Settings, clock: FixedClock
) -> None:
    with respx.mock:
        report = TeamsCollector(repositories, settings, clock, JOB_SEARCH_RULES).collect()

    assert report.not_configured
    assert report.channel is Channel.TEAMS


def test_the_teams_step_counts_only_when_teams_is_set_up(
    settings: Settings, teams_settings: Settings
) -> None:
    assert RunStep.COLLECT_TEAMS in unconfigured_steps(settings)
    assert RunStep.COLLECT_TEAMS not in unconfigured_steps(teams_settings)


# --- What the owner is told -----------------------------------------------------


@pytest.mark.parametrize(
    ("code", "words"),
    [
        (AdminApprovalRequiredError.code, "IT admin has to allow this"),
        (WorkAccountRequiredError.code, "uv run tracker setup teams"),
        (SourceAuthError.code, "uv run tracker setup teams"),
        (SourceUnavailableError.code, "the next run tries again"),
    ],
)
def test_every_teams_problem_reads_as_plain_words(code: str, words: str) -> None:
    problem = explain(RunStep.COLLECT_TEAMS, code)

    assert "Teams" in problem.what_happened
    assert words in problem.what_to_do
    assert code not in problem.what_happened + problem.what_to_do


@pytest.mark.asyncio
async def test_the_doctor_skips_teams_until_it_is_connected() -> None:
    assert (await TeamsCheck(None).run()).status is CheckStatus.SKIPPED


@pytest.mark.asyncio
async def test_the_doctor_names_who_is_signed_in_to_teams() -> None:
    async def address() -> str:
        return "sam@work.example"

    result = await TeamsCheck(address).run()

    assert result.status is CheckStatus.OK
    assert "sam@work.example" in result.detail


def test_teams_can_be_collected_on_its_own() -> None:
    result = CliRunner().invoke(build_cli(), ["collect", "teams", "--help"], color=False)

    assert result.exit_code == 0
    assert "work or school account" in result.output
