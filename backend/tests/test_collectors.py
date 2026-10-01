"""The two collectors, end to end, against an in-memory database.

No network: every source answer is mocked with ``respx`` and every payload is
made up. What is checked here is the behaviour the owner was promised — noise
keeps no text, whole threads are kept, and a second run changes nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import respx
from pydantic import SecretStr

from tests.conftest import JOB_SEARCH_RULES, TEST_ENCRYPTION_KEY, FakeSupabaseClient
from tests.test_linkedin import page
from tests.test_microsoft import (
    MESSAGES_URL,
    InFlight,
    body_answer,
    graph_message,
    mock_folders,
    mock_renewal,
)
from tracker.domain.enums import Channel, Direction, Relevance, RunStatus, RunStep, RunTrigger
from tracker.domain.models import Conversation, Message, RunLog, RunStepLog
from tracker.infrastructure.secret_store import MICROSOFT_REFRESH_TOKEN, SecretStore
from tracker.repositories import Repositories
from tracker.services.collection.email_collector import EmailCollector
from tracker.services.collection.linkedin_collector import LinkedInCollector
from tracker.services.collection.models import NOT_CONFIGURED_LINE
from tracker.shared.clock import FixedClock
from tracker.shared.config import Settings, get_settings, reset_settings_cache
from tracker.shared.constants.collection import (
    GRAPH_CONCURRENT_REQUESTS,
    GROUP_SUBJECT_PREFIX,
    LINKEDIN_SNAPSHOT_URL,
    MICROSOFT_GRAPH_URL,
)
from tracker.shared.errors import SourceUnavailableError

OWNER_PROFILE = "https://www.linkedin.com/in/sam"
ELODIE = "https://www.linkedin.com/in/elodie-martin"
ADA = "https://www.linkedin.com/in/ada-recruiter"
BRUNO = "https://www.linkedin.com/in/bruno-founder"


def linkedin_row(
    conversation_id: str,
    *,
    sender: str,
    sender_name: str,
    date: str,
    content: str,
    folder: str = "INBOX",
    title: str = "",
    recipients: str = OWNER_PROFILE,
    recipient_names: str = "Sam Rivera",
) -> dict[str, str]:
    """Build one made-up snapshot row."""
    return {
        "CONVERSATION ID": conversation_id,
        "CONVERSATION TITLE": title or sender_name,
        "FROM": sender_name,
        "SENDER PROFILE URL": sender,
        "TO": recipient_names,
        "RECIPIENT PROFILE URLS": recipients,
        "DATE": date,
        "SUBJECT": "",
        "CONTENT": content,
        "FOLDER": folder,
        "ATTACHMENTS": "",
    }


ARCHIVE: list[dict[str, str]] = [
    linkedin_row(
        "2-advert",
        sender=ADA,
        sender_name="Ada Recruiter",
        date="2026-09-08 10:00:00 UTC",
        content="Sponsored: join our talent pool today.",
        folder="SPONSORED_INMAIL",
    ),
    linkedin_row(
        "2-advert-answered",
        sender=BRUNO,
        sender_name="Bruno Founder",
        date="2026-09-09 10:00:00 UTC",
        content="Sponsored: we are hiring engineers.",
        folder="SPONSORED_INMAIL",
    ),
    linkedin_row(
        "2-advert-answered",
        sender=OWNER_PROFILE,
        sender_name="Sam Rivera",
        date="2026-09-09 11:00:00 UTC",
        content="Interested — what is the role?",
        folder="SPONSORED_INMAIL",
        recipients=BRUNO,
        recipient_names="Bruno Founder",
    ),
    linkedin_row(
        "2-chat",
        sender=ELODIE,
        sender_name="Élodie Martin",
        date="2026-05-02 08:00:00 UTC",
        content="We met at the conference last spring.",
    ),
    linkedin_row(
        "2-chat",
        sender=OWNER_PROFILE,
        sender_name="Sam Rivera",
        date="2026-09-12 09:00:00 UTC",
        content="Following up on our chat.",
        recipients=ELODIE,
        recipient_names="Élodie Martin",
    ),
    linkedin_row(
        "2-forgotten",
        sender=ELODIE,
        sender_name="Élodie Martin",
        date="2025-11-01 08:00:00 UTC",
        content="An old thread nobody touched this month.",
    ),
]


def mock_archive(rows: list[dict[str, str]]) -> None:
    """Answer page zero with the rows, and 404 for the page after it."""

    def handle(request: httpx.Request) -> httpx.Response:
        if int(request.url.params["start"]) == 0:
            return httpx.Response(200, json=page(rows))
        return httpx.Response(404, json={"message": "no more data"})

    respx.get(LINKEDIN_SNAPSHOT_URL).mock(side_effect=handle)


def collect_linkedin(
    repositories: Repositories,
    settings: Settings,
    clock: FixedClock,
    rows: list[dict[str, str]] = ARCHIVE,
) -> Any:
    """Run the LinkedIn collector against a made-up archive."""
    with respx.mock:
        mock_archive(rows)
        return LinkedInCollector(repositories, settings, clock, JOB_SEARCH_RULES).collect()


def rows_of(client: FakeSupabaseClient, table: str) -> list[dict[str, Any]]:
    """Read one table of the in-memory database."""
    return client.tables.get(table, [])


def conversation_named(client: FakeSupabaseClient, source_id: str) -> dict[str, Any]:
    """Find one stored conversation by its source identifier."""
    return next(
        row
        for row in rows_of(client, "conversations")
        if row["source_conversation_id"] == source_id
    )


def messages_of(client: FakeSupabaseClient, source_id: str) -> list[dict[str, Any]]:
    """List the stored messages of one conversation."""
    conversation_id = conversation_named(client, source_id)["id"]
    return [row for row in rows_of(client, "messages") if row["conversation_id"] == conversation_id]


def test_an_advert_without_a_reply_is_stored_as_noise_with_no_text(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    collect_linkedin(repositories, settings, clock)

    conversation = conversation_named(fake_client, "2-advert")
    assert conversation["relevance"] == Relevance.NOISE.value
    assert conversation["subject"] is None
    assert conversation["person_id"] is None
    assert [message["body"] for message in messages_of(fake_client, "2-advert")] == [None]


def test_an_advert_the_owner_answered_keeps_its_text(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    collect_linkedin(repositories, settings, clock)

    conversation = conversation_named(fake_client, "2-advert-answered")
    stored = messages_of(fake_client, "2-advert-answered")
    bodies = sorted(str(message["body"]) for message in stored)
    assert conversation["relevance"] == Relevance.UNSURE.value
    assert conversation["person_id"] is not None
    assert bodies == ["Interested — what is the role?", "Sponsored: we are hiring engineers."]


def test_a_touched_thread_is_kept_whole_and_an_untouched_one_is_left_alone(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    report = collect_linkedin(repositories, settings, clock)

    stored = {row["source_conversation_id"] for row in rows_of(fake_client, "conversations")}
    assert stored == {"2-advert", "2-advert-answered", "2-chat"}
    assert len(messages_of(fake_client, "2-chat")) == 2
    assert report.conversations_found == 3
    assert report.conversations_noise == 1


def test_a_linkedin_message_delivered_days_late_is_still_collected(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    """LinkedIn's copy runs days behind; a message older than the last run still counts."""
    repositories.run_logs.bulk_upsert(
        [
            RunLog(
                started_at=datetime(2026, 9, 17, 7, 0, tzinfo=UTC),
                status=RunStatus.SUCCESS,
                trigger=RunTrigger.CLOUD,
            )
        ]
    )
    late = linkedin_row(
        "2-late",
        sender=BRUNO,
        sender_name="Bruno Founder",
        date="2026-09-08 10:00:00 UTC",
        content="Are you free for a call next week?",
    )

    collect_linkedin(repositories, settings, clock, rows=[late])

    assert {row["source_conversation_id"] for row in rows_of(fake_client, "conversations")} == {
        "2-late"
    }


def test_direction_follows_the_owners_own_profile(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    collect_linkedin(repositories, settings, clock)

    directions = {
        str(message["sender_identifier"]): message["direction"]
        for message in messages_of(fake_client, "2-chat")
    }
    assert directions == {
        "linkedin.com/in/sam": "outbound",
        "linkedin.com/in/elodie-martin": "inbound",
    }


def test_a_second_run_changes_nothing(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    collect_linkedin(repositories, settings, clock)
    before = {
        table: [dict(row) for row in rows_of(fake_client, table)]
        for table in ("conversations", "messages", "people", "person_identities")
    }

    second = collect_linkedin(repositories, settings, clock)

    after = {
        table: [dict(row) for row in rows_of(fake_client, table)]
        for table in ("conversations", "messages", "people", "person_identities")
    }
    assert after == before
    assert second.conversations_new == 0
    assert second.messages_new == 0
    assert second.people_new == 0


def test_a_group_thread_is_marked_in_its_subject(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    rows = [
        linkedin_row(
            "2-group",
            sender=ELODIE,
            sender_name="Élodie Martin",
            date="2026-09-11 08:00:00 UTC",
            content="Introducing you two.",
            title="Introductions",
            recipients=f"{OWNER_PROFILE}, {BRUNO}",
            recipient_names="Sam Rivera, Bruno Founder",
        )
    ]

    collect_linkedin(repositories, settings, clock, rows)

    subject = conversation_named(fake_client, "2-group")["subject"]
    assert subject == f"{GROUP_SUBJECT_PREFIX} Introductions"


def test_a_missing_linkedin_key_skips_linkedin_before_any_request(
    repositories: Repositories,
    settings_without_linkedin_key: Settings,
    clock: FixedClock,
    fake_client: FakeSupabaseClient,
) -> None:
    collector = LinkedInCollector(
        repositories, settings_without_linkedin_key, clock, JOB_SEARCH_RULES
    )

    report = collector.collect()

    assert report.not_configured is True
    assert report.as_lines() == ("channel: linkedin", NOT_CONFIGURED_LINE)
    assert fake_client.executed == []


def test_a_missing_linkedin_profile_skips_linkedin_too(
    repositories: Repositories,
    valid_environment: None,
    monkeypatch: pytest.MonkeyPatch,
    clock: FixedClock,
) -> None:
    monkeypatch.delenv("OWNER_LINKEDIN_PROFILE_URL")
    monkeypatch.setenv("LINKEDIN_ACCESS_TOKEN", "made-up-linkedin-key")
    reset_settings_cache()

    report = LinkedInCollector(repositories, get_settings(), clock, JOB_SEARCH_RULES).collect()

    assert report.not_configured is True


# --- mailbox ---------------------------------------------------------------

MAILBOX: list[dict[str, Any]] = [
    graph_message(
        "m-news",
        conversation_id="t-news",
        address="newsletter@weekly.example",
        name="Startup Weekly",
        subject="This week in hiring",
        sent="2026-09-08T06:00:00Z",
        unsubscribe=True,
    ),
    graph_message(
        "m-human-1",
        conversation_id="t-human",
        address="elodie.martin@acme.example",
        name="Élodie Martin",
        subject="Coffee next week?",
        sent="2026-09-10T09:30:00Z",
    ),
    graph_message(
        "m-human-2",
        conversation_id="t-human",
        address="sam.rivera@mailbox.example",
        name="Sam Rivera",
        subject="RE: Coffee next week?",
        sent="2026-09-10T10:00:00Z",
    ),
]


def mock_mailbox(messages: list[dict[str, Any]]) -> tuple[respx.Route, respx.Route]:
    """Answer the metadata pass, the thread pass and the body pass.

    Returns:
        The listing route and the body route, so a test can read their calls.
    """
    mock_renewal()
    mock_folders()

    def handle(request: httpx.Request) -> httpx.Response:
        wanted = request.url.params.get("$filter", "")
        if "conversationId" in wanted:
            thread = wanted.split("'")[1]
            return httpx.Response(
                200,
                json={"value": [m for m in messages if m["conversationId"] == thread]},
            )
        return httpx.Response(200, json={"value": messages})

    listing = respx.get(MESSAGES_URL).mock(side_effect=handle)
    bodies = respx.get(url__startswith=f"{MESSAGES_URL}/").mock(
        side_effect=lambda request: httpx.Response(
            200,
            json={
                "id": request.url.path.rsplit("/", maxsplit=1)[-1],
                "body": {"contentType": "text", "content": "Made-up body text."},
            },
        )
    )
    return listing, bodies


def collect_email(
    repositories: Repositories,
    settings: Settings,
    clock: FixedClock,
    messages: list[dict[str, Any]] = MAILBOX,
) -> Any:
    """Run the mailbox collector against a made-up mailbox."""
    SecretStore(repositories.app_secrets, SecretStr(TEST_ENCRYPTION_KEY), clock).put_secret(
        MICROSOFT_REFRESH_TOKEN, "old-long-lived-key"
    )
    with respx.mock:
        mock_mailbox(messages)
        return EmailCollector(repositories, settings, clock, JOB_SEARCH_RULES).collect()


def test_a_newsletter_is_stored_with_no_subject_and_no_body(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    collect_email(repositories, settings, clock)

    conversation = conversation_named(fake_client, "t-news")
    assert conversation["relevance"] == Relevance.NOISE.value
    assert conversation["subject"] is None
    assert conversation["person_id"] is None
    assert [message["body"] for message in messages_of(fake_client, "t-news")] == [None]


def test_a_newsletter_never_becomes_a_person(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    collect_email(repositories, settings, clock)

    names = {str(row["full_name"]) for row in rows_of(fake_client, "people")}
    assert names == {"Élodie Martin"}


def test_a_thread_the_owner_replied_to_keeps_its_text_and_its_direction(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    collect_email(repositories, settings, clock)

    conversation = conversation_named(fake_client, "t-human")
    messages = messages_of(fake_client, "t-human")
    assert conversation["relevance"] == Relevance.UNSURE.value
    assert conversation["subject"] == "Coffee next week?"
    assert all(message["body"] == "Made-up body text." for message in messages)
    assert sorted(str(message["direction"]) for message in messages) == ["inbound", "outbound"]


def test_no_body_is_ever_fetched_for_a_noise_thread(
    repositories: Repositories,
    settings: Settings,
    clock: FixedClock,
) -> None:
    SecretStore(repositories.app_secrets, SecretStr(TEST_ENCRYPTION_KEY), clock).put_secret(
        MICROSOFT_REFRESH_TOKEN, "old-long-lived-key"
    )

    with respx.mock:
        _, bodies = mock_mailbox(MAILBOX)
        EmailCollector(repositories, settings, clock, JOB_SEARCH_RULES).collect()
        fetched = {call.request.url.path.rsplit("/", maxsplit=1)[-1] for call in bodies.calls}

    assert fetched == {"m-human-1", "m-human-2"}


BUSY_SENDERS = (
    "Ada Lovelace",
    "Bruno Rossi",
    "Chiara Blanc",
    "Dario Conti",
    "Emma Dubois",
    "Fabio Neri",
)

#: Six real conversations, each one message in and the owner's reply.
BUSY_MAILBOX: list[dict[str, Any]] = [
    message
    for number, sender in enumerate(BUSY_SENDERS)
    for message in (
        graph_message(
            f"m-{number}-in",
            conversation_id=f"t-{number}",
            address=f"{sender.split()[0].lower()}@company{number}.example",
            name=sender,
            subject=f"Role {number}",
            sent="2026-09-10T09:30:00Z",
        ),
        graph_message(
            f"m-{number}-out",
            conversation_id=f"t-{number}",
            address="sam.rivera@mailbox.example",
            name="Sam Rivera",
            subject=f"RE: Role {number}",
            sent="2026-09-10T10:00:00Z",
        ),
    )
]


def test_kept_threads_are_read_side_by_side_and_each_message_keeps_its_own_text(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    SecretStore(repositories.app_secrets, SecretStr(TEST_ENCRYPTION_KEY), clock).put_secret(
        MICROSOFT_REFRESH_TOKEN, "old-long-lived-key"
    )
    in_flight = InFlight(body_answer)

    with respx.mock:
        _, bodies = mock_mailbox(BUSY_MAILBOX)
        bodies.mock(side_effect=in_flight)
        report = EmailCollector(repositories, settings, clock, JOB_SEARCH_RULES).collect()

    assert 1 < in_flight.peak <= GRAPH_CONCURRENT_REQUESTS
    assert report.conversations_found == len(BUSY_SENDERS)
    stored = [str(row["source_conversation_id"]) for row in rows_of(fake_client, "conversations")]
    assert stored == [f"t-{number}" for number in range(len(BUSY_SENDERS))]
    for source_id in stored:
        for message in messages_of(fake_client, source_id):
            assert message["body"] == f"body of {message['source_message_id']}"


def test_a_message_that_cannot_be_read_ends_the_run_cleanly_and_stores_nothing(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    SecretStore(repositories.app_secrets, SecretStr(TEST_ENCRYPTION_KEY), clock).put_secret(
        MICROSOFT_REFRESH_TOKEN, "old-long-lived-key"
    )

    def refuse_one(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/m-3-in"):
            return httpx.Response(403, json={})
        return body_answer(request)

    with respx.mock:
        _, bodies = mock_mailbox(BUSY_MAILBOX)
        bodies.mock(side_effect=InFlight(refuse_one))
        with pytest.raises(SourceUnavailableError, match="403"):
            EmailCollector(repositories, settings, clock, JOB_SEARCH_RULES).collect()

    assert rows_of(fake_client, "conversations") == []
    assert rows_of(fake_client, "messages") == []


def test_a_second_mailbox_run_changes_nothing(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    collect_email(repositories, settings, clock)
    before = {
        table: [dict(row) for row in rows_of(fake_client, table)]
        for table in ("conversations", "messages", "people", "person_identities")
    }

    second = collect_email(repositories, settings, clock)

    after = {
        table: [dict(row) for row in rows_of(fake_client, table)]
        for table in ("conversations", "messages", "people", "person_identities")
    }
    assert after == before
    assert (second.conversations_new, second.messages_new, second.people_new) == (0, 0, 0)


def test_an_employer_domain_becomes_an_organisation_and_a_free_one_does_not(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    messages = [
        *MAILBOX,
        graph_message(
            "m-friend",
            conversation_id="t-friend",
            address="marco.rossi@gmail.com",
            name="Marco Rossi",
            subject="Beers?",
            sent="2026-09-11T18:00:00Z",
        ),
    ]

    collect_email(repositories, settings, clock, messages)

    domains = {str(row["email_domain"]) for row in rows_of(fake_client, "organisations")}
    assert domains == {"acme.example"}


def test_the_mailbox_is_never_asked_for_a_message_outside_the_window(
    repositories: Repositories,
    settings: Settings,
    clock: FixedClock,
) -> None:
    SecretStore(repositories.app_secrets, SecretStr(TEST_ENCRYPTION_KEY), clock).put_secret(
        MICROSOFT_REFRESH_TOKEN, "old-long-lived-key"
    )

    with respx.mock:
        listing, _ = mock_mailbox(MAILBOX)
        EmailCollector(repositories, settings, clock, JOB_SEARCH_RULES).collect()
        asked = listing.calls[0].request.url.params["$filter"]

    assert asked == "receivedDateTime ge 2026-08-19T07:00:00Z"


def test_a_run_partial_for_another_source_still_moves_the_mailbox_window(
    repositories: Repositories,
    settings: Settings,
    clock: FixedClock,
) -> None:
    SecretStore(repositories.app_secrets, SecretStr(TEST_ENCRYPTION_KEY), clock).put_secret(
        MICROSOFT_REFRESH_TOKEN, "old-long-lived-key"
    )
    run = RunLog(
        started_at=datetime(2026, 9, 17, 7, 0, tzinfo=UTC),
        status=RunStatus.PARTIAL,
        trigger=RunTrigger.GITHUB,
    )
    repositories.run_logs.bulk_upsert([run])
    repositories.run_step_logs.bulk_upsert(
        [
            RunStepLog(run_id=run.id, step=RunStep.COLLECT_LINKEDIN, status=RunStatus.FAILED),
            RunStepLog(run_id=run.id, step=RunStep.COLLECT_EMAIL, status=RunStatus.SUCCESS),
        ]
    )

    with respx.mock:
        listing, _ = mock_mailbox(MAILBOX)
        EmailCollector(repositories, settings, clock, JOB_SEARCH_RULES).collect()
        asked = listing.calls[0].request.url.params["$filter"]

    assert asked == "receivedDateTime ge 2026-09-15T07:00:00Z"


def test_the_graph_reader_is_only_ever_asked_to_read(
    repositories: Repositories,
    settings: Settings,
    clock: FixedClock,
) -> None:
    SecretStore(repositories.app_secrets, SecretStr(TEST_ENCRYPTION_KEY), clock).put_secret(
        MICROSOFT_REFRESH_TOKEN, "old-long-lived-key"
    )

    with respx.mock:
        mock_mailbox(MAILBOX)
        EmailCollector(repositories, settings, clock, JOB_SEARCH_RULES).collect()
        methods = {
            call.request.method
            for route in respx.routes
            for call in route.calls
            if str(call.request.url).startswith(MICROSOFT_GRAPH_URL)
        }

    assert methods == {"GET"}


def test_a_thread_already_kept_is_read_in_full_before_being_called_noise(
    repositories: Repositories,
    settings: Settings,
    clock: FixedClock,
) -> None:
    """The window may hold only part of a thread.

    A recruiter thread the owner replied to in August, where the only message
    inside the window is a machine-sent one, must not be flipped to noise:
    that would drop its subject and erase every stored body, which no later run
    can restore.
    """
    inside_window = graph_message(
        "m-ats",
        conversation_id="t-recruiter",
        address="no-reply@ats.example",
        name="Careers Bot",
        subject="Your application",
        sent="2026-09-10T09:00:00Z",
        unsubscribe=True,
    )
    older_owner_reply = graph_message(
        "m-owner",
        conversation_id="t-recruiter",
        address="sam.rivera@mailbox.example",
        name="Sam Rivera",
        subject="RE: Your application",
        sent="2026-07-02T09:00:00Z",
    )
    SecretStore(repositories.app_secrets, SecretStr(TEST_ENCRYPTION_KEY), clock).put_secret(
        MICROSOFT_REFRESH_TOKEN, "old-long-lived-key"
    )

    def handle(request: httpx.Request) -> httpx.Response:
        wanted = request.url.params.get("$filter", "")
        if "conversationId" in wanted:
            # The thread pass sees everything, including the older reply.
            return httpx.Response(200, json={"value": [inside_window, older_owner_reply]})
        # The metadata pass only ever sees the window.
        return httpx.Response(200, json={"value": [inside_window]})

    # The state a previous run left behind: the thread is kept, with its text.
    kept = Conversation(
        channel=Channel.EMAIL,
        source_conversation_id="t-recruiter",
        subject="Your application",
        relevance=Relevance.UNSURE,
    )
    repositories.conversations.bulk_upsert([kept])
    repositories.messages.bulk_upsert(
        [
            Message(
                conversation_id=kept.id,
                source_message_id="m-owner",
                direction=Direction.OUTBOUND,
                sent_at=datetime(2026, 7, 2, 9, tzinfo=UTC),
                body="I am very interested, here is my availability.",
            )
        ]
    )

    with respx.mock:
        mock_renewal()
        mock_folders()
        respx.get(MESSAGES_URL).mock(side_effect=handle)
        respx.get(url__startswith=f"{MESSAGES_URL}/").mock(
            side_effect=lambda request: httpx.Response(
                200,
                json={
                    "id": request.url.path.rsplit("/", maxsplit=1)[-1],
                    "body": {"contentType": "text", "content": "Made-up body text."},
                },
            )
        )
        # A later run whose window holds only the machine-sent message.
        EmailCollector(repositories, settings, clock, JOB_SEARCH_RULES).collect()

    again = repositories.conversations.find_by_source(Channel.EMAIL, "t-recruiter")
    assert again is not None
    assert again.relevance is not Relevance.NOISE, "a kept thread must not be flipped to noise"
    bodies = [m.body for m in repositories.messages.list_for_conversations([again.id])]
    assert any(bodies), "the stored message text must survive"


# --- shared senders ----------------------------------------------------------

ASHBY = "no-reply@ashbyhq.com"

SHARED_SENDERS: list[dict[str, Any]] = [
    graph_message(
        "m-northwind",
        conversation_id="t-northwind",
        address=ASHBY,
        name="Northwind AI Hiring Team",
        subject="Northwind AI Interview Confirmation",
        sent="2026-09-10T08:00:00Z",
        unsubscribe=True,
    ),
    graph_message(
        "m-bluebird",
        conversation_id="t-bluebird",
        address=ASHBY,
        name="Bluebird Hiring Team",
        subject="Welcome to Bluebird's recruitment process!",
        sent="2026-09-11T08:00:00Z",
        unsubscribe=True,
    ),
    graph_message(
        "m-invite",
        conversation_id="t-invite",
        address="c_0000example@group.calendar.google.com",
        name="Interviews",
        subject="Invitation: Operations Associate - Intro Call",
        sent="2026-09-12T08:00:00Z",
        reply_to=(("hanna.keller@northwind.example", "Hanna Keller"),),
    ),
]


def test_two_companies_behind_one_hiring_system_become_two_people(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    collect_email(repositories, settings, clock, SHARED_SENDERS)

    northwind = conversation_named(fake_client, "t-northwind")
    bluebird = conversation_named(fake_client, "t-bluebird")
    assert northwind["person_id"] != bluebird["person_id"]
    assert northwind["relevance"] == Relevance.UNSURE.value
    identifiers = {str(row["identifier"]) for row in rows_of(fake_client, "person_identities")}
    assert ASHBY not in identifiers


def test_a_hiring_system_company_becomes_an_organisation_but_the_system_does_not(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    collect_email(repositories, settings, clock, SHARED_SENDERS)

    names = {str(row["name"]) for row in rows_of(fake_client, "organisations")}
    assert {"Northwind AI", "Bluebird"} <= names
    assert not any("ashby" in name.lower() for name in names)


def test_a_calendar_invitation_is_filed_under_the_person_who_sent_it(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    collect_email(repositories, settings, clock, SHARED_SENDERS)

    invite = conversation_named(fake_client, "t-invite")
    people = {row["id"]: row["full_name"] for row in rows_of(fake_client, "people")}
    assert people[invite["person_id"]] == "Hanna Keller"


def test_an_accepted_invitation_moved_to_deleted_items_is_still_read(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    """Outlook tidies an invitation into Deleted Items the moment it is accepted."""
    messages = [
        graph_message(
            "m-accepted",
            conversation_id="t-accepted",
            address="c_0001example@group.calendar.google.com",
            name="Orbita Interview Calendar",
            subject="Invitation: Sam <> Orbita",
            sent="2026-09-12T08:00:00Z",
            folder="folder-deleteditems",
            reply_to=(("lena.h@orbita.example", "Lena Hoffman-Adler"),),
            odata_type="#microsoft.graph.eventMessageRequest",
        ),
        graph_message(
            "m-binned",
            conversation_id="t-binned",
            address="anna@acme.example",
            name="Anna Lee",
            subject="An ordinary deleted e-mail",
            sent="2026-09-12T09:00:00Z",
            folder="folder-deleteditems",
        ),
    ]

    collect_email(repositories, settings, clock, messages)

    sources = {str(row["source_conversation_id"]) for row in rows_of(fake_client, "conversations")}
    assert sources == {"t-accepted"}
    people = {str(row["full_name"]) for row in rows_of(fake_client, "people")}
    assert people == {"Lena Hoffman-Adler"}


# --- a hiring system writing under the company's own domain (Acme) ---------

ACME_MAILBOX: list[dict[str, Any]] = [
    graph_message(
        "m-applied",
        conversation_id="t-applied",
        address="notification@acmecareers.example",
        name="Acme",
        subject="Thank you for applying to Acme",
        sent="2026-09-10T08:00:00Z",
        unsubscribe=True,
    ),
    graph_message(
        "m-video-1",
        conversation_id="t-video",
        address="notifications@acmecareers.example",
        name="notifications",
        subject="Video interview - Sam Rivera and Acme",
        sent="2026-09-11T08:00:00Z",
        unsubscribe=True,
    ),
    graph_message(
        "m-video-2",
        conversation_id="t-video",
        address="notifications@acmecareers.example",
        name="notifications",
        subject="Video interview - Sam Rivera and Acme",
        sent="2026-09-11T08:05:00Z",
        unsubscribe=True,
    ),
]


def test_a_companys_own_hiring_mail_is_kept_under_one_company_record(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    collect_email(repositories, settings, clock, ACME_MAILBOX)

    applied = conversation_named(fake_client, "t-applied")
    video = conversation_named(fake_client, "t-video")
    assert applied["relevance"] == video["relevance"] == Relevance.UNSURE.value
    assert video["subject"] == "Video interview - Sam Rivera and Acme"
    assert all(message["body"] for message in messages_of(fake_client, "t-video"))
    (person,) = rows_of(fake_client, "people")
    assert applied["person_id"] == video["person_id"] == person["id"]
    assert person["full_name"] == "Acme Hiring Team"
    (identity,) = rows_of(fake_client, "person_identities")
    assert identity["identifier"] == "no-reply@acmecareers.example#acme"
    assert {str(row["name"]) for row in rows_of(fake_client, "organisations")} == {"Acme"}


# --- The summary prefix is one setting (Plan 18) ------------------------------


def _summary_mail(subject: str) -> list[dict[str, Any]]:
    return [
        graph_message(
            "m-summary",
            conversation_id="t-summary",
            address="desk@sender.example",
            name="Morning desk",
            subject=subject,
            sent="2026-09-17T05:00:00Z",
        )
    ]


def test_the_mailbox_ignores_a_summary_sent_with_the_configured_prefix(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    branded = settings.model_copy(update={"summary_subject_prefix": "[Weekly Desk]"})

    collect_email(repositories, branded, clock, _summary_mail("[Weekly Desk] 2 to chase"))

    assert conversation_named(fake_client, "t-summary")["relevance"] == Relevance.NOISE.value


def test_the_old_prefix_no_longer_hides_mail_once_the_setting_changes(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    branded = settings.model_copy(update={"summary_subject_prefix": "[Weekly Desk]"})

    collect_email(repositories, branded, clock, _summary_mail("[Threadline] 2 to chase"))

    assert conversation_named(fake_client, "t-summary")["relevance"] != Relevance.NOISE.value
