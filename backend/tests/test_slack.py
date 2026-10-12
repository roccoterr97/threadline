"""Slack as a source: direct messages from one or several workspaces, against a fake Slack."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import respx
from pydantic import SecretStr

from tests.conftest import JOB_SEARCH_RULES, FakeSupabaseClient
from tracker.domain.enums import Channel, Direction, RunStep
from tracker.domain.slack_markup import mentioned_users, plain_text
from tracker.repositories import Repositories
from tracker.services.collection.models import CollectionReport
from tracker.services.collection.slack_collector import SlackCollector
from tracker.services.doctor.checks import SlackCheck
from tracker.services.doctor.models import CheckStatus
from tracker.services.runs.run_recorder import unconfigured_steps
from tracker.services.summary.problem_messages import explain
from tracker.shared import config
from tracker.shared.clock import FixedClock
from tracker.shared.config import Settings, split_slack_tokens
from tracker.shared.constants.slack import (
    SLACK_APP_MANIFEST,
    SLACK_NEW_APP_LINK,
    SLACK_USER_SCOPES,
)
from tracker.shared.errors import (
    SlackApprovalNeededError,
    SlackRateLimitedError,
    SlackTokenRefusedError,
)

ACME_TOKEN = "xoxp-acme-made-up"
BETA_TOKEN = "xoxp-beta-made-up"
OWNER_ID = "U0OWNER"
HANNA = {
    "id": "U0HANNA",
    "real_name": "Hanna Keller",
    "profile": {"real_name": "Hanna Keller", "email": "Hanna.Keller@Northwind.example"},
}
#: Two days before the test clock, inside the first run's thirty-day window.
RECENT = "1789538400.000100"


def message(ts: str, user: str, text: str, **extra: Any) -> dict[str, Any]:
    """One made-up message as Slack's history returns it."""
    return {"type": "message", "ts": ts, "user": user, "text": text, **extra}


def im(channel: str, user: str, **extra: Any) -> dict[str, Any]:
    """One made-up direct message as ``users.conversations`` lists it."""
    return {"id": channel, "is_im": True, "user": user, **extra}


@dataclass
class FakeWorkspace:
    """One workspace as Slack would answer for it."""

    token: str
    team: str
    team_id: str
    conversations: list[dict[str, Any]] = field(default_factory=list)
    history: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    replies: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    members: dict[str, list[str]] = field(default_factory=dict)
    users: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: An error every call answers with, such as ``token_revoked``.
    error: str | None = None
    #: Rows per page, so a long listing has several pages.
    page_size: int = 2


@dataclass
class FakeSlack:
    """Slack's Web API for several workspaces, recording every call."""

    workspaces: list[FakeWorkspace]
    calls: list[tuple[str, dict[str, str]]] = field(default_factory=list)
    #: Answers given before the real ones, in turn, such as a 429.
    queued: list[httpx.Response] = field(default_factory=list)
    #: Conversations Slack refuses to read, as one closed since it was listed.
    closed: set[str] = field(default_factory=set)

    def answer(self, request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[-1]
        params = dict(request.url.params)
        self.calls.append((method, params))
        if self.queued:
            return self.queued.pop(0)
        if params.get("channel") in self.closed:
            return httpx.Response(200, json={"ok": False, "error": "channel_not_found"})
        token = request.headers["Authorization"].removeprefix("Bearer ")
        workspace = next(item for item in self.workspaces if item.token == token)
        if workspace.error is not None:
            return httpx.Response(200, json={"ok": False, "error": workspace.error})
        return httpx.Response(200, json={"ok": True, **_body(workspace, method, params)})


def _body(workspace: FakeWorkspace, method: str, params: dict[str, str]) -> dict[str, Any]:
    if method == "auth.test":
        return {"user_id": OWNER_ID, "team_id": workspace.team_id, "team": workspace.team}
    if method == "users.info":
        user = workspace.users.get(params["user"], {"id": params["user"], "name": "someone"})
        return {"user": user}
    if method == "users.conversations":
        return _page(workspace, workspace.conversations, "channels", params)
    if method == "conversations.history":
        return _page(workspace, workspace.history.get(params["channel"], []), "messages", params)
    if method == "conversations.replies":
        return _page(workspace, workspace.replies.get(params["ts"], []), "messages", params)
    if method == "conversations.members":
        return _page(workspace, workspace.members.get(params["channel"], []), "members", params)
    raise AssertionError(method)


def _page(
    workspace: FakeWorkspace, rows: list[Any], key: str, params: dict[str, str]
) -> dict[str, Any]:
    start = int(params.get("cursor") or 0)
    end = start + workspace.page_size
    more = end < len(rows)
    return {key: rows[start:end], "response_metadata": {"next_cursor": str(end) if more else ""}}


def acme(**changes: Any) -> FakeWorkspace:
    """A workspace with one direct message with Hanna: her message and the owner's reply."""
    workspace = FakeWorkspace(
        token=ACME_TOKEN,
        team="Acme",
        team_id="T0ACME",
        conversations=[im("D0HANNA", "U0HANNA")],
        history={
            "D0HANNA": [
                message("1789538460.000200", OWNER_ID, "Thanks <@U0HANNA>, Tuesday works"),
                message(
                    RECENT,
                    "U0HANNA",
                    "Can we talk? Deck: <https://deck.example/a|our deck> &amp; notes",
                ),
            ]
        },
        users={"U0HANNA": HANNA},
    )
    for name, value in changes.items():
        setattr(workspace, name, value)
    return workspace


@pytest.fixture
def slack_settings(valid_environment: None, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Configuration with the Acme workspace set up."""
    monkeypatch.setenv("SLACK_USER_TOKENS", ACME_TOKEN)
    config.reset_settings_cache()
    return config.get_settings()


def run(
    repositories: Repositories,
    settings: Settings,
    clock: FixedClock,
    slack: FakeSlack,
) -> CollectionReport:
    """Read and store, against the fake Slack, handing back the report with any problem."""
    collector = SlackCollector(repositories, settings, clock, JOB_SEARCH_RULES)
    with respx.mock:
        respx.route(host="slack.com").mock(side_effect=slack.answer)
        return asyncio.run(collector.read())()


def rows(client: FakeSupabaseClient, table: str) -> list[dict[str, Any]]:
    return client.tables.get(table, [])


def methods(slack: FakeSlack) -> list[str]:
    return [method for method, _ in slack.calls]


# --- Reading one workspace ------------------------------------------------------


def test_a_direct_message_is_one_thread_filed_under_the_persons_e_mail(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    slack_settings: Settings,
    clock: FixedClock,
) -> None:
    slack = FakeSlack([acme()])

    report = run(repositories, slack_settings, clock, slack)

    (thread,) = rows(fake_client, "conversations")
    (identity,) = rows(fake_client, "person_identities")
    messages = sorted(rows(fake_client, "messages"), key=lambda row: str(row["sent_at"]))
    assert report.problem is None
    assert (report.conversations_found, report.messages_found, report.people_new) == (1, 2, 1)
    assert thread["channel"] == Channel.SLACK.value
    assert thread["source_conversation_id"] == "D0HANNA"
    assert thread["subject"] == "Slack · Acme"
    assert (identity["channel"], identity["identifier"]) == (
        Channel.EMAIL.value,
        "hanna.keller@northwind.example",
    )
    assert [row["direction"] for row in messages] == [
        Direction.INBOUND.value,
        Direction.OUTBOUND.value,
    ]
    assert messages[0]["body"] == "Can we talk? Deck: our deck (https://deck.example/a) & notes"
    assert messages[1]["body"] == "Thanks @Hanna Keller, Tuesday works"


def test_the_window_is_asked_for_with_oldest(
    repositories: Repositories, slack_settings: Settings, clock: FixedClock
) -> None:
    slack = FakeSlack([acme()])

    run(repositories, slack_settings, clock, slack)

    (history,) = [params for method, params in slack.calls if method == "conversations.history"]
    oldest = datetime.fromtimestamp(float(history["oldest"]), tz=UTC)
    assert oldest == datetime(2026, 8, 19, 7, 0, tzinfo=UTC)


def test_a_slack_dm_joins_the_record_the_person_already_has_by_e_mail(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    slack_settings: Settings,
    clock: FixedClock,
) -> None:
    run(repositories, slack_settings, clock, FakeSlack([acme()]))
    run(repositories, slack_settings, clock, FakeSlack([acme()]))

    assert len(rows(fake_client, "people")) == 1
    assert len(rows(fake_client, "conversations")) == 1
    assert len(rows(fake_client, "messages")) == 2


def test_somebody_without_a_shared_address_is_known_by_their_slack_id(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    slack_settings: Settings,
    clock: FixedClock,
) -> None:
    private = {"id": "U0HANNA", "real_name": "Hanna Keller", "profile": {}}

    run(repositories, slack_settings, clock, FakeSlack([acme(users={"U0HANNA": private})]))

    (identity,) = rows(fake_client, "person_identities")
    assert (identity["channel"], identity["identifier"]) == (Channel.SLACK.value, "U0HANNA")
    assert rows(fake_client, "messages")[0]["sender_identifier"] in {"U0HANNA", OWNER_ID}


def test_bots_slackbot_apps_and_removed_accounts_are_never_a_conversation(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    slack_settings: Settings,
    clock: FixedClock,
) -> None:
    workspace = acme(
        conversations=[
            im("D0SLACKBOT", "USLACKBOT"),
            im("D0GONE", "U0GONE", is_user_deleted=True),
            im("D0BOT", "U0BOT"),
            im("D0HANNA", "U0HANNA"),
        ],
        history={
            "D0BOT": [message(RECENT, "U0BOT", "Your build passed")],
            "D0HANNA": [
                message(RECENT, "U0HANNA", "Hello"),
                message("1789538401.0", "U0HANNA", "Reminder", bot_id="B01"),
                message("1789538402.0", "U0HANNA", "joined", subtype="channel_join"),
            ],
        },
        users={"U0HANNA": HANNA, "U0BOT": {"id": "U0BOT", "name": "ci", "is_bot": True}},
    )
    slack = FakeSlack([workspace])

    report = run(repositories, slack_settings, clock, slack)

    (thread,) = rows(fake_client, "conversations")
    assert thread["source_conversation_id"] == "D0HANNA"
    assert [row["body"] for row in rows(fake_client, "messages")] == ["Hello"]
    assert report.people_new == 1
    read = [params.get("channel") for method, params in slack.calls if "history" in method]
    assert set(read) == {"D0BOT", "D0HANNA"}


def test_every_page_is_followed(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    slack_settings: Settings,
    clock: FixedClock,
) -> None:
    history = [message(f"17895384{index:02d}.0", "U0HANNA", f"note {index}") for index in range(5)]
    conversations = [im("D0HANNA", "U0HANNA"), *[im(f"D0X{n}", "USLACKBOT") for n in range(3)]]
    workspace = acme(conversations=conversations, history={"D0HANNA": history})
    slack = FakeSlack([workspace])

    run(repositories, slack_settings, clock, slack)

    assert len(rows(fake_client, "messages")) == 5
    assert methods(slack).count("conversations.history") == 3
    assert methods(slack).count("users.conversations") == 2


def test_a_group_dm_has_every_person_and_is_marked_as_a_group(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    slack_settings: Settings,
    clock: FixedClock,
) -> None:
    omar = {"id": "U0OMAR", "real_name": "Omar Ali", "profile": {"email": "omar@fund.example"}}
    workspace = acme(
        conversations=[{"id": "G0TRIO", "is_mpim": True}],
        history={"G0TRIO": [message(RECENT, "U0OMAR", "Intro: Hanna, meet Sam")]},
        members={"G0TRIO": [OWNER_ID, "U0HANNA", "U0OMAR"]},
        users={"U0HANNA": HANNA, "U0OMAR": omar},
    )

    run(repositories, slack_settings, clock, FakeSlack([workspace]))

    (thread,) = rows(fake_client, "conversations")
    assert thread["subject"] == "[group] Slack · Acme"
    identifiers = {row["identifier"] for row in rows(fake_client, "person_identities")}
    assert identifiers == {"hanna.keller@northwind.example", "omar@fund.example"}


def test_replies_in_a_thread_are_read_with_the_message_that_starts_it(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    slack_settings: Settings,
    clock: FixedClock,
) -> None:
    starter = message(RECENT, "U0HANNA", "Two questions", reply_count=1, thread_ts=RECENT)
    reply = message("1789538500.0", OWNER_ID, "Answers inside", thread_ts=RECENT)
    workspace = acme(history={"D0HANNA": [starter]}, replies={RECENT: [starter, reply]})

    run(repositories, slack_settings, clock, FakeSlack([workspace]))

    bodies = sorted(row["body"] for row in rows(fake_client, "messages"))
    assert bodies == ["Answers inside", "Two questions"]


def test_a_file_only_message_names_the_file() -> None:
    from tracker.infrastructure.slack.parser import message_from
    from tracker.services.collection.slack_threads import _body

    shared = message_from(message(RECENT, "U0HANNA", "", files=[{"name": "deck.pdf"}]))

    assert _body(shared, {}) == "[shared a file: deck.pdf]"


def test_slack_not_set_up_makes_no_request(
    repositories: Repositories, settings: Settings, clock: FixedClock
) -> None:
    slack = FakeSlack([acme()])

    report = run(repositories, settings, clock, slack)

    assert report.not_configured
    assert slack.calls == []


# --- When Slack refuses or asks to wait -------------------------------------------


def test_a_revoked_token_says_to_run_the_set_up_again_without_showing_it(
    repositories: Repositories, slack_settings: Settings, clock: FixedClock
) -> None:
    slack = FakeSlack([acme(error="token_revoked")])

    with pytest.raises(SlackTokenRefusedError) as raised:
        run(repositories, slack_settings, clock, slack)

    assert "uv run tracker setup slack" in raised.value.message
    assert ACME_TOKEN not in raised.value.message
    assert methods(slack) == ["auth.test"]


def test_a_workspace_waiting_for_admin_approval_says_so(
    repositories: Repositories, slack_settings: Settings, clock: FixedClock
) -> None:
    with pytest.raises(SlackApprovalNeededError) as raised:
        run(repositories, slack_settings, clock, FakeSlack([acme(error="team_access_not_granted")]))

    assert "admin must approve" in raised.value.message


def test_a_short_wait_is_sat_out_and_the_read_goes_on(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    slack_settings: Settings,
    clock: FixedClock,
) -> None:
    slow_down = httpx.Response(429, headers={"Retry-After": "2"})
    slack = FakeSlack([acme()], queued=[slow_down])

    report = run(repositories, slack_settings, clock, slack)

    assert report.problem is None
    assert len(rows(fake_client, "conversations")) == 1
    assert methods(slack)[:2] == ["auth.test", "auth.test"]


def test_a_long_wait_stops_cleanly_after_one_request(
    repositories: Repositories, slack_settings: Settings, clock: FixedClock
) -> None:
    slack = FakeSlack([acme()], queued=[httpx.Response(429, headers={"Retry-After": "3600"})])

    with pytest.raises(SlackRateLimitedError) as raised:
        run(repositories, slack_settings, clock, slack)

    assert "3600" in raised.value.message
    assert len(slack.calls) == 1


def test_a_conversation_slack_will_not_read_is_skipped_not_the_workspace(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    slack_settings: Settings,
    clock: FixedClock,
) -> None:
    workspace = acme(conversations=[im("D0CLOSED", "U0HANNA"), im("D0HANNA", "U0HANNA")])
    slack = FakeSlack([workspace], closed={"D0CLOSED"})

    report = run(repositories, slack_settings, clock, slack)

    assert report.problem is None
    assert [row["source_conversation_id"] for row in rows(fake_client, "conversations")] == [
        "D0HANNA"
    ]


# --- Several workspaces -----------------------------------------------------------


@pytest.fixture
def two_workspaces(valid_environment: None, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Configuration with the Acme and Beta workspaces set up."""
    monkeypatch.setenv("SLACK_USER_TOKENS", f"{ACME_TOKEN}, {BETA_TOKEN}")
    config.reset_settings_cache()
    return config.get_settings()


def beta(**changes: Any) -> FakeWorkspace:
    """A second workspace with one direct message with Omar."""
    omar = {"id": "U0OMAR", "real_name": "Omar Ali", "profile": {"email": "omar@fund.example"}}
    workspace = FakeWorkspace(
        token=BETA_TOKEN,
        team="Beta",
        team_id="T0BETA",
        conversations=[im("D0OMAR", "U0OMAR")],
        history={"D0OMAR": [message(RECENT, "U0OMAR", "Term sheet attached")]},
        users={"U0OMAR": omar},
    )
    for name, value in changes.items():
        setattr(workspace, name, value)
    return workspace


def test_two_workspaces_are_read_side_by_side(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    two_workspaces: Settings,
    clock: FixedClock,
) -> None:
    report = run(repositories, two_workspaces, clock, FakeSlack([acme(), beta()]))

    subjects = sorted(row["subject"] for row in rows(fake_client, "conversations"))
    assert subjects == ["Slack · Acme", "Slack · Beta"]
    assert report.conversations_found == 2
    assert report.problem is None


def test_one_refused_workspace_never_loses_the_other(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    two_workspaces: Settings,
    clock: FixedClock,
) -> None:
    report = run(
        repositories, two_workspaces, clock, FakeSlack([acme(error="invalid_auth"), beta()])
    )

    assert [row["subject"] for row in rows(fake_client, "conversations")] == ["Slack · Beta"]
    assert isinstance(report.problem, SlackTokenRefusedError)


def test_a_slack_connect_dm_seen_from_both_workspaces_is_one_thread(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    two_workspaces: Settings,
    clock: FixedClock,
) -> None:
    shared = beta(conversations=[im("D0HANNA", "U0HANNA")], users={"U0HANNA": HANNA})
    shared.history = acme().history

    run(repositories, two_workspaces, clock, FakeSlack([acme(), shared]))

    assert len(rows(fake_client, "conversations")) == 1


# --- The tokens, the run, the summary and the doctor -------------------------------


def test_the_tokens_setting_is_split_trimmed_and_kept_once() -> None:
    assert split_slack_tokens(SecretStr(" xoxp-a ,xoxp-b,,xoxp-a ")) == ("xoxp-a", "xoxp-b")
    assert split_slack_tokens(None) == ()


def test_once_slack_is_set_up_its_step_is_part_of_the_run(slack_settings: Settings) -> None:
    assert RunStep.COLLECT_SLACK not in unconfigured_steps(slack_settings)


def test_without_slack_its_step_is_not_part_of_the_run(settings: Settings) -> None:
    assert RunStep.COLLECT_SLACK in unconfigured_steps(settings)


@pytest.mark.parametrize(
    ("code", "words"),
    [
        (SlackTokenRefusedError.code, "uv run tracker setup slack"),
        (SlackApprovalNeededError.code, "admin"),
        (SlackRateLimitedError.code, "next run reads the rest"),
        ("source_unavailable", "Slack did not answer"),
        ("something_new", "Slack messages could not be read"),
    ],
)
def test_every_slack_failure_reads_as_plain_words(code: str, words: str) -> None:
    problem = explain(RunStep.COLLECT_SLACK, code)

    assert words in f"{problem.what_happened} {problem.what_to_do}"
    assert code not in f"{problem.what_happened} {problem.what_to_do}"


def test_the_doctor_names_the_workspaces_slack_accepted() -> None:
    async def names() -> tuple[str, ...]:
        return ("Acme", "Beta")

    accepted = asyncio.run(SlackCheck(names).run())
    absent = asyncio.run(SlackCheck(None).run())

    assert accepted.status is CheckStatus.OK
    assert accepted.detail == "Slack accepted the key for Acme, Beta"
    assert absent.status is CheckStatus.SKIPPED


def test_the_app_link_carries_the_read_only_manifest() -> None:
    assert SLACK_NEW_APP_LINK.startswith("https://api.slack.com/apps?new_app=1&manifest_json=")
    assert SLACK_APP_MANIFEST["oauth_config"] == {"scopes": {"user": list(SLACK_USER_SCOPES)}}
    assert set(SLACK_USER_SCOPES) == {
        "im:history",
        "im:read",
        "mpim:history",
        "mpim:read",
        "users:read",
        "users:read.email",
    }


# --- Slack's markup -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "plain"),
    [
        ("Hi <@U0HANNA>!", "Hi @Hanna Keller!"),
        ("Hi <@U0NOBODY>", "Hi @someone"),
        ("Hi <@U0NOBODY|hk>", "Hi @hk"),
        ("See <https://a.example/x|the plan>", "See the plan (https://a.example/x)"),
        ("See <https://a.example/x>", "See https://a.example/x"),
        ("Mail <mailto:hk@a.example|hk@a.example>", "Mail hk@a.example"),
        ("In <#C0GENERAL|general>", "In #general"),
        ("<!here> ready?", "@here ready?"),
        ("<!subteam^S0ENG|@engineering> look", "@engineering look"),
        ("<!date^1789538400^{date}|18 Sep 2026> works", "18 Sep 2026 works"),
        ("a &lt; b &amp;&amp; c &gt; d", "a < b && c > d"),
        ("&amp;lt;", "&lt;"),
    ],
)
def test_slack_markup_reads_as_plain_text(text: str, plain: str) -> None:
    assert plain_text(text, {"U0HANNA": "Hanna Keller"}, "someone") == plain


def test_mentions_are_listed_once_in_order() -> None:
    assert mentioned_users("<@U1> and <@U2|b> and <@U1>") == ("U1", "U2")


# --- The commands -----------------------------------------------------------------


def test_slack_has_its_own_collect_command() -> None:
    from typer.testing import CliRunner

    from tracker.cli.main import build_cli

    result = CliRunner().invoke(build_cli(), ["collect", "--help"])

    assert result.exit_code == 0
    assert "slack" in result.output


def test_the_daily_run_reads_slack_on_its_own_and_stores_it_last(
    repositories: Repositories, slack_settings: Settings, clock: FixedClock
) -> None:
    from tracker.cli.commands.collect import _sources

    lanes = _sources(repositories, slack_settings, clock, None, None)

    (slack,) = lanes[-1]
    assert (slack.channel, slack.step) == (Channel.SLACK, RunStep.COLLECT_SLACK)
