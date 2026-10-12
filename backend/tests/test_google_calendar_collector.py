"""Google Calendar as a source: the same meetings as Outlook's, read from a secret address."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from pydantic import SecretStr

from tests.conftest import JOB_SEARCH_RULES, FakeSupabaseClient
from tests.ical_world import (
    GOOGLE_ADDRESS,
    HANNA,
    ORGANISER_NOTES,
    OWNER,
    FakeDownload,
    calendar_file,
    vevent,
)
from tracker.domain.enums import Channel, Direction
from tracker.repositories import Repositories
from tracker.services.collection.google_calendar_collector import GoogleCalendarCollector
from tracker.services.collection.models import CollectionReport
from tracker.shared.clock import FixedClock
from tracker.shared.config import Settings
from tracker.shared.errors import SourceAuthError

GMAIL = "sam.rivera@gmail.example"


@pytest.fixture
def google_settings(settings: Settings) -> Settings:
    """The usual settings with a Google calendar's secret address saved."""
    return settings.model_copy(update={"google_calendar_url": SecretStr(GOOGLE_ADDRESS)})


def collect(
    repositories: Repositories,
    settings: Settings,
    clock: FixedClock,
    *events: str,
    name: str = OWNER,
) -> CollectionReport:
    """Collect a made-up Google calendar holding the events."""
    download = FakeDownload(calendar_file(*events, name=name))
    collector = GoogleCalendarCollector(
        repositories, settings, clock, JOB_SEARCH_RULES, download=download
    )
    return collector.collect()


def rows(client: FakeSupabaseClient, table: str) -> list[dict[str, Any]]:
    """Read one table of the in-memory database."""
    return client.tables.get(table, [])


def test_without_an_address_nothing_is_read_and_nothing_fails(
    repositories: Repositories, settings: Settings, clock: FixedClock
) -> None:
    download = FakeDownload()

    report = GoogleCalendarCollector(
        repositories, settings, clock, JOB_SEARCH_RULES, download=download
    ).collect()

    assert report.not_configured is True
    assert report.channel is Channel.CALENDAR
    assert download.calls == []


def test_a_meeting_is_filed_under_the_person_by_their_e_mail_address(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    google_settings: Settings,
    clock: FixedClock,
) -> None:
    report = collect(repositories, google_settings, clock, vevent("intro@google.com"))

    (thread,) = rows(fake_client, "conversations")
    (identity,) = rows(fake_client, "person_identities")
    (message,) = rows(fake_client, "messages")
    assert report.conversations_new == 1
    assert thread["channel"] == Channel.CALENDAR.value
    assert thread["source_conversation_id"] == "intro@google.com"
    assert str(thread["meeting_at"]).startswith("2026-09-24T09:00")
    assert identity["identifier"] == HANNA[0]
    assert message["direction"] == Direction.INBOUND.value
    assert "Thu 24 Sep 2026, 09:00–09:45 (UTC)" in message["body"]
    assert "Your answer: accepted" in message["body"]


def test_what_the_organiser_typed_is_never_stored(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    google_settings: Settings,
    clock: FixedClock,
) -> None:
    collect(repositories, google_settings, clock, vevent("intro@google.com"))

    stored = repr(fake_client.tables)
    assert ORGANISER_NOTES not in stored
    assert "Meeting room 4" not in stored


def test_an_event_with_only_the_owner_is_never_stored(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    google_settings: Settings,
    clock: FixedClock,
) -> None:
    gym = vevent("gym@google.com", summary="Gym", organizer=None, attendees=())
    flight = vevent("flight@google.com", summary="Flight", organizer=(OWNER, "Sam"))

    collect(repositories, google_settings, clock, gym, flight)

    assert rows(fake_client, "conversations") == []
    assert rows(fake_client, "people") == []


def test_the_google_account_behind_the_calendar_is_never_taken_for_a_person(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    google_settings: Settings,
    clock: FixedClock,
) -> None:
    """The Google account is not among the owner's mailboxes, but the address names it."""
    meeting = vevent(
        "coffee@google.com",
        organizer=(GMAIL, "Sam Rivera"),
        attendees=((GMAIL, "Sam Rivera", "ACCEPTED"), (HANNA[0], HANNA[1], "NEEDS-ACTION")),
    )

    collect(repositories, google_settings, clock, meeting, name="Sam's calendar")

    assert {row["identifier"] for row in rows(fake_client, "person_identities")} == {HANNA[0]}
    (message,) = rows(fake_client, "messages")
    assert message["direction"] == Direction.OUTBOUND.value
    assert "Your answer: you organised it" in message["body"]


def test_an_interview_the_owner_typed_is_filed_under_its_company(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    google_settings: Settings,
    clock: FixedClock,
) -> None:
    """Google may list the owner as the only guest of their own entry; it is still theirs."""
    entry = vevent(
        "acme@google.com",
        summary="Video interview - Sam and Acme",
        organizer=(OWNER, "Sam"),
        attendees=((OWNER, "Sam", "ACCEPTED"),),
    )

    collect(repositories, google_settings, clock, entry)

    (person,) = rows(fake_client, "people")
    assert person["full_name"] == "Acme"
    assert {row["identifier"] for row in rows(fake_client, "person_identities")} == {
        "own-calendar#acme"
    }


def test_a_moved_meeting_adds_a_message_and_a_second_run_changes_nothing(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    google_settings: Settings,
    clock: FixedClock,
) -> None:
    collect(repositories, google_settings, clock, vevent("intro@google.com"))
    cancelled = vevent("intro@google.com", status="CANCELLED", last_modified="20260916T100000Z")

    collect(repositories, google_settings, clock, cancelled)
    collect(repositories, google_settings, clock, cancelled)

    (thread,) = rows(fake_client, "conversations")
    bodies = [row["body"] for row in rows(fake_client, "messages")]
    assert len(bodies) == 2
    assert any("This meeting was cancelled." in body for body in bodies)
    assert thread["meeting_at"] is None


def test_each_occurrence_of_a_weekly_meeting_is_its_own_meeting(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    google_settings: Settings,
    clock: FixedClock,
) -> None:
    weekly = vevent(
        "weekly@google.com",
        start="DTSTART;TZID=Europe/Rome:20260915T100000",
        end="DTEND;TZID=Europe/Rome:20260915T103000",
        extra=("RRULE:FREQ=WEEKLY;COUNT=3",),
    )

    report = collect(repositories, google_settings, clock, weekly)

    assert report.conversations_found == 3
    assert len(rows(fake_client, "people")) == 1
    assert len({row["person_id"] for row in rows(fake_client, "conversations")}) == 1


def test_times_are_shown_in_the_owners_zone_and_a_whole_day_by_its_dates(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    google_settings: Settings,
) -> None:
    rome = FixedClock(datetime(2026, 9, 18, 7, 0, tzinfo=UTC), ZoneInfo("Europe/Rome"))
    offsite = vevent(
        "offsite@google.com",
        summary="Offsite",
        start="DTSTART;VALUE=DATE:20260925",
        end="DTEND;VALUE=DATE:20260927",
    )

    collect(repositories, google_settings, rome, vevent("intro@google.com"), offsite)

    bodies = {row["body"] for row in rows(fake_client, "messages")}
    assert any("Thu 24 Sep 2026, 11:00–11:45 (Europe/Rome)" in body for body in bodies)
    assert any("When: Fri 25 Sep 2026–Sat 26 Sep 2026 (all day)" in body for body in bodies)


def test_a_refused_address_is_raised_for_the_run_to_record(
    repositories: Repositories, google_settings: Settings, clock: FixedClock
) -> None:
    collector = GoogleCalendarCollector(
        repositories,
        google_settings,
        clock,
        JOB_SEARCH_RULES,
        download=FakeDownload(failure="refused"),
    )

    with pytest.raises(SourceAuthError):
        collector.collect()
