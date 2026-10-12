"""Reading a calendar file: repeating meetings, time zones, whole days, cancellations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.ical_world import HANNA, OWNER, calendar_file, vevent
from tracker.domain.calendar import CalendarEvent, MeetingResponse
from tracker.infrastructure.ical.parser import CalendarFile, read_calendar_file
from tracker.shared.errors import ValidationFailedError

NOW = datetime(2026, 9, 18, 7, 0, tzinfo=UTC)
ROME = ZoneInfo("Europe/Rome")


def read(
    content: bytes, *, owner: tuple[str, ...] = (OWNER,), zone: ZoneInfo = ROME
) -> CalendarFile:
    """Read a calendar file for the usual window: 30 days back, 60 ahead."""
    return read_calendar_file(
        content,
        start=NOW - timedelta(days=30),
        end=NOW + timedelta(days=60),
        owner_addresses=owner,
        zone=zone,
    )


def only(content: bytes, *, zone: ZoneInfo = ROME) -> CalendarEvent:
    """Read a calendar file that holds exactly one event in the window."""
    (event,) = read(content, zone=zone).events
    return event


def test_an_invitation_keeps_its_title_times_people_and_the_owners_answer() -> None:
    event = only(calendar_file(vevent("intro@google.com")))

    assert event.ical_uid == "intro@google.com"
    assert event.subject == "Operations Associate - Intro Call"
    assert event.start == datetime(2026, 9, 24, 9, 0, tzinfo=UTC)
    assert event.end == datetime(2026, 9, 24, 9, 45, tzinfo=UTC)
    assert event.organizer == HANNA
    assert event.attendees == ((OWNER, OWNER),)
    assert event.is_organizer is False
    assert event.response is MeetingResponse.ACCEPTED
    assert event.is_cancelled is False
    assert event.is_all_day is False
    assert event.changed_at == datetime(2026, 9, 15, 10, 0, tzinfo=UTC)
    assert event.revision == "2026-09-15T10:00:00+00:00"


@pytest.mark.parametrize(
    ("partstat", "answer"),
    [
        ("TENTATIVE", MeetingResponse.TENTATIVE),
        ("DECLINED", MeetingResponse.DECLINED),
        ("NEEDS-ACTION", MeetingResponse.NOT_ANSWERED),
    ],
)
def test_the_owners_answer_is_read_from_their_own_line(
    partstat: str, answer: MeetingResponse
) -> None:
    people = ((HANNA[0], HANNA[1], "ACCEPTED"), (OWNER, "Sam", partstat))

    event = only(calendar_file(vevent("intro@google.com", attendees=people)))

    assert event.response is answer


def test_a_meeting_the_owner_organised_is_theirs() -> None:
    event = only(
        calendar_file(
            vevent(
                "coffee@google.com",
                organizer=(OWNER, "Sam"),
                attendees=((HANNA[0], HANNA[1], "NEEDS-ACTION"),),
            )
        )
    )

    assert event.is_organizer is True
    assert event.response is MeetingResponse.ORGANIZER


def test_an_entry_with_no_organiser_is_the_owners_own() -> None:
    event = only(calendar_file(vevent("gym@google.com", organizer=None, attendees=())))

    assert event.is_organizer is True
    assert event.organizer == ("", "")
    assert event.attendees == ()


def test_the_owner_is_known_by_the_address_the_calendar_is_named_after() -> None:
    """A Google account that is not one of the listed mailboxes is still the owner's."""
    gmail = "sam.rivera@gmail.example"
    content = calendar_file(
        vevent("coffee@google.com", organizer=(gmail, "Sam")), name=gmail.upper()
    )

    found = read(content)

    assert found.owner_addresses == {gmail}
    assert found.events[0].is_organizer is True


def test_a_calendar_named_in_words_names_no_owner() -> None:
    assert read(calendar_file(name="Work")).owner_addresses == frozenset()


def test_a_time_with_a_zone_is_read_in_that_zone() -> None:
    event = only(
        calendar_file(
            vevent(
                "rome@google.com",
                start="DTSTART;TZID=Europe/Rome:20260924T110000",
                end="DTEND;TZID=Europe/Rome:20260924T114500",
            )
        )
    )

    assert event.start.astimezone(UTC) == datetime(2026, 9, 24, 9, 0, tzinfo=UTC)
    assert event.end.astimezone(UTC) == datetime(2026, 9, 24, 9, 45, tzinfo=UTC)


def test_a_time_without_a_zone_is_the_calendars_own_zone() -> None:
    """Google names the calendar's zone in X-WR-TIMEZONE; a floating time is in it."""
    event = only(
        calendar_file(
            vevent(
                "floating@google.com", start="DTSTART:20260924T110000", end="DTEND:20260924T120000"
            )
        )
    )

    assert event.start.astimezone(UTC) == datetime(2026, 9, 24, 9, 0, tzinfo=UTC)


def test_a_whole_day_entry_starts_at_the_owners_midnight() -> None:
    event = only(
        calendar_file(
            vevent(
                "offsite@google.com",
                start="DTSTART;VALUE=DATE:20260925",
                end="DTEND;VALUE=DATE:20260927",
            )
        ),
        zone=ZoneInfo("America/New_York"),
    )

    assert event.is_all_day is True
    assert event.start == datetime(2026, 9, 25, tzinfo=ZoneInfo("America/New_York"))
    assert event.end == datetime(2026, 9, 27, tzinfo=ZoneInfo("America/New_York"))


def test_a_cancelled_meeting_says_so() -> None:
    event = only(calendar_file(vevent("intro@google.com", status="CANCELLED")))

    assert event.is_cancelled is True


def test_a_weekly_meeting_becomes_one_event_per_occurrence_in_the_window() -> None:
    weekly = vevent(
        "weekly@google.com",
        summary="Weekly sync",
        start="DTSTART;TZID=Europe/Rome:20260801T100000",
        end="DTEND;TZID=Europe/Rome:20260801T103000",
        extra=("RRULE:FREQ=WEEKLY;COUNT=20",),
    )

    events = read(calendar_file(weekly)).events

    starts = [event.start.astimezone(ROME) for event in events]
    # 1 Aug is before the window (19 Aug to 17 Nov); 12 Dec is past the count.
    assert starts[0] == datetime(2026, 8, 22, 10, 0, tzinfo=ROME)
    assert starts[-1] == datetime(2026, 11, 14, 10, 0, tzinfo=ROME)
    assert len(events) == 13
    assert len({event.ical_uid for event in events}) == 13
    assert all(event.ical_uid.startswith("weekly@google.com#") for event in events)


def test_a_weekly_meeting_keeps_ten_oclock_across_the_clock_change() -> None:
    weekly = vevent(
        "weekly@google.com",
        start="DTSTART;TZID=Europe/Rome:20260922T100000",
        end="DTEND;TZID=Europe/Rome:20260922T103000",
        extra=("RRULE:FREQ=WEEKLY;UNTIL=20261103T090000Z",),
    )

    events = read(calendar_file(weekly)).events

    assert {event.start.astimezone(ROME).hour for event in events} == {10}
    assert {event.start.astimezone(UTC).hour for event in events} == {8, 9}


def test_a_skipped_occurrence_is_left_out_and_a_moved_one_is_read_where_it_went() -> None:
    master = vevent(
        "weekly@google.com",
        summary="Weekly sync",
        start="DTSTART;TZID=Europe/Rome:20260901T100000",
        end="DTEND;TZID=Europe/Rome:20260901T103000",
        extra=(
            "RRULE:FREQ=WEEKLY;COUNT=4",
            "EXDATE;TZID=Europe/Rome:20260908T100000",
        ),
    )
    moved = vevent(
        "weekly@google.com",
        summary="Weekly sync (moved)",
        start="DTSTART;TZID=Europe/Rome:20260916T150000",
        end="DTEND;TZID=Europe/Rome:20260916T153000",
        last_modified="20260910T080000Z",
        extra=("RECURRENCE-ID;TZID=Europe/Rome:20260915T100000",),
    )

    events = read(calendar_file(master, moved)).events

    by_id = {event.ical_uid: event for event in events}
    assert sorted(by_id) == [
        "weekly@google.com#20260901T080000Z",
        "weekly@google.com#20260915T080000Z",
        "weekly@google.com#20260922T080000Z",
    ]
    shifted = by_id["weekly@google.com#20260915T080000Z"]
    assert shifted.subject == "Weekly sync (moved)"
    assert shifted.start.astimezone(ROME) == datetime(2026, 9, 16, 15, 0, tzinfo=ROME)
    assert shifted.revision == "2026-09-10T08:00:00+00:00"


def test_rooms_and_entries_without_an_address_are_not_people() -> None:
    meeting = vevent("intro@google.com", attendees=((OWNER, "Sam", "ACCEPTED"),)).replace(
        "END:VEVENT",
        "\r\n".join(
            [
                "ATTENDEE;CUTYPE=ROOM;PARTSTAT=ACCEPTED;CN=Room 4:mailto:room4@rooms.example",
                "ATTENDEE;CUTYPE=INDIVIDUAL;CN=Someone:urn:uuid:1234",
                "END:VEVENT",
            ]
        ),
    )

    event = only(calendar_file(meeting))

    assert event.attendees == ((OWNER, "Sam"),)


def test_an_entry_without_a_last_change_follows_its_time_and_status() -> None:
    plain = only(calendar_file(vevent("intro@google.com", last_modified=None)))
    cancelled = only(
        calendar_file(vevent("intro@google.com", last_modified=None, status="CANCELLED"))
    )

    assert plain.revision == "20260924T090000Z"
    assert cancelled.revision == "20260924T090000Z-cancelled"
    assert plain.changed_at == datetime(2026, 9, 14, 10, 0, tzinfo=UTC)


def test_events_outside_the_window_are_left_out() -> None:
    old = vevent("old@google.com", start="DTSTART:20250101T090000Z", end="DTEND:20250101T100000Z")

    assert read(calendar_file(old)).events == ()


def test_the_description_is_never_copied() -> None:
    event = only(calendar_file(vevent("intro@google.com")))

    assert "Dial-in" not in repr(event)
    assert "Meeting room 4" not in repr(event)


@pytest.mark.parametrize(
    "content",
    [
        b"<!DOCTYPE html><html><body>Sign in</body></html>",
        b"",
        b"BEGIN:VCALENDAR\r\nthis is not a calendar",
    ],
)
def test_anything_but_a_calendar_file_is_refused_plainly(content: bytes) -> None:
    with pytest.raises(ValidationFailedError, match="Secret address in iCal format"):
        read(content)


def test_a_byte_order_mark_before_the_calendar_is_fine() -> None:
    content = b"\xef\xbb\xbf" + calendar_file(vevent("intro@google.com"))

    assert len(read(content).events) == 1
