"""The collection window, the writer's decisions, and the plain people list."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tests.conftest import FakeSupabaseClient
from tests.test_collectors import collect_email, collect_linkedin
from tracker.domain.enums import (
    Channel,
    Direction,
    Relevance,
    RelevanceDecidedBy,
    RunStatus,
    RunTrigger,
)
from tracker.domain.models import RunLog
from tracker.repositories import Repositories
from tracker.services.collection.models import RawConversation, RawMessage
from tracker.services.collection.window import last_successful_run_at, window_start
from tracker.services.collection.writer import ConversationWriter
from tracker.services.identity.directory import PeopleDirectory
from tracker.shared.clock import FixedClock
from tracker.shared.config import Settings
from tracker.shared.constants.collection import INITIAL_WINDOW_DAYS, OVERLAP_DAYS

NOW = datetime(2026, 9, 18, 7, 0, tzinfo=UTC)


def test_a_first_run_looks_back_thirty_days(clock: FixedClock) -> None:
    assert window_start(clock) == NOW - timedelta(days=INITIAL_WINDOW_DAYS)


def test_a_later_run_starts_from_the_last_one_with_an_overlap(clock: FixedClock) -> None:
    yesterday = NOW - timedelta(days=1)

    assert window_start(clock, last_run_at=yesterday) == yesterday - timedelta(days=OVERLAP_DAYS)


def test_an_explicit_start_beats_everything(clock: FixedClock) -> None:
    asked = datetime(2026, 1, 1, tzinfo=UTC)

    assert window_start(clock, last_run_at=NOW, since=asked) == asked


def test_a_long_gap_is_caught_up_in_full(clock: FixedClock) -> None:
    long_ago = NOW - timedelta(days=90)

    assert window_start(clock, last_run_at=long_ago) == long_ago - timedelta(days=OVERLAP_DAYS)


def test_only_a_successful_run_moves_the_window(
    repositories: Repositories,
    clock: FixedClock,
) -> None:
    repositories.run_logs.bulk_upsert(
        [
            RunLog(
                started_at=NOW - timedelta(days=3),
                status=RunStatus.SUCCESS,
                trigger=RunTrigger.CLOUD,
            ),
            RunLog(
                started_at=NOW - timedelta(days=1),
                status=RunStatus.FAILED,
                trigger=RunTrigger.CLOUD,
            ),
        ]
    )

    assert last_successful_run_at(repositories) == NOW - timedelta(days=3)
    assert window_start(clock, last_run_at=last_successful_run_at(repositories)) == NOW - timedelta(
        days=3 + OVERLAP_DAYS
    )


def test_with_no_successful_run_the_next_one_is_a_first_run(repositories: Repositories) -> None:
    assert last_successful_run_at(repositories) is None


def noise_thread() -> RawConversation:
    """A thread the prefilter judged machine traffic."""
    return RawConversation(
        channel=Channel.EMAIL,
        source_conversation_id="t-news",
        subject="This week in hiring",
        relevance=Relevance.NOISE,
        messages=(
            RawMessage(
                source_message_id="m-1",
                sent_at=NOW,
                direction=Direction.INBOUND,
                sender_identifier="newsletter@weekly.example",
                body="Made-up newsletter text.",
            ),
        ),
    )


def test_the_writer_keeps_no_text_for_a_thread_judged_noise(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
) -> None:
    ConversationWriter(repositories).write(Channel.EMAIL, [noise_thread()], {})

    conversation = fake_client.tables["conversations"][0]
    assert conversation["subject"] is None
    assert conversation["relevance_decided_by"] == RelevanceDecidedBy.RULE.value
    assert fake_client.tables["messages"][0]["body"] is None


def test_the_writer_records_the_four_dates_of_a_thread(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
) -> None:
    thread = RawConversation(
        channel=Channel.EMAIL,
        source_conversation_id="t-human",
        subject="Coffee next week?",
        relevance=Relevance.UNSURE,
        messages=(
            RawMessage(
                source_message_id="m-1",
                sent_at=datetime(2026, 9, 10, 9, 30, tzinfo=UTC),
                direction=Direction.INBOUND,
                sender_identifier="elodie.martin@acme.example",
                body="Hello",
            ),
            RawMessage(
                source_message_id="m-2",
                sent_at=datetime(2026, 9, 10, 10, 0, tzinfo=UTC),
                direction=Direction.OUTBOUND,
                sender_identifier="sam.rivera@mailbox.example",
                body="Hello back",
            ),
        ),
    )

    ConversationWriter(repositories).write(Channel.EMAIL, [thread], {})

    stored = fake_client.tables["conversations"][0]
    assert stored["first_message_at"].startswith("2026-09-10T09:30")
    assert stored["last_message_at"].startswith("2026-09-10T10:00")
    assert stored["last_inbound_at"].startswith("2026-09-10T09:30")
    assert stored["last_outbound_at"].startswith("2026-09-10T10:00")


def test_a_decision_the_assessment_already_made_is_not_overwritten(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
) -> None:
    writer = ConversationWriter(repositories)
    writer.write(Channel.EMAIL, [noise_thread()], {})
    stored = fake_client.tables["conversations"][0]
    stored["relevance"] = Relevance.RELEVANT.value
    stored["relevance_decided_by"] = RelevanceDecidedBy.AI.value

    writer.write(Channel.EMAIL, [noise_thread()], {})

    assert fake_client.tables["conversations"][0]["relevance"] == Relevance.RELEVANT.value
    assert (
        fake_client.tables["conversations"][0]["relevance_decided_by"]
        == RelevanceDecidedBy.AI.value
    )


def test_the_people_list_shows_channels_counts_and_last_contact(
    repositories: Repositories,
    settings: Settings,
    clock: FixedClock,
) -> None:
    collect_linkedin(repositories, settings, clock)
    collect_email(repositories, settings, clock)

    entries = PeopleDirectory(repositories).list_people()

    by_name = {entry.full_name: entry for entry in entries}
    elodie = by_name["Élodie Martin"]
    assert set(elodie.channels) == {Channel.EMAIL, Channel.LINKEDIN}
    assert elodie.message_count == 4
    assert elodie.last_contact_at == datetime(2026, 9, 12, 9, 0, tzinfo=UTC)
    assert by_name["Bruno Founder"].channels == (Channel.LINKEDIN,)
