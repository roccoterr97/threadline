"""Dates, thresholds and the owner's corrections are decided in Python."""

from __future__ import annotations

from calendar import Day
from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from tracker.domain.assessment_policy import (
    ContactTiming,
    OwnerCalendar,
    OwnerCorrections,
    VerdictValues,
    add_working_days,
    decide,
    follow_up_date,
    has_gone_quiet,
    needs_review,
)
from tracker.domain.enums import ContactStatus, Relevance, Signal, WaitingOn
from tracker.shared.errors import ValidationFailedError

NOW = datetime(2026, 9, 18, 7, 0, tzinfo=UTC)
TODAY = NOW.date()
SAT_SUN = frozenset({Day.SATURDAY, Day.SUNDAY})
UTC_CALENDAR = OwnerCalendar(zone=UTC, weekend=SAT_SUN)


def _values(**changes: object) -> VerdictValues:
    """A confident verdict, changed field by field per test."""
    base = {
        "relevance": Relevance.RELEVANT,
        "person_type": "startup",
        "status": ContactStatus.IN_CONVERSATION,
        "waiting_on": WaitingOn.THEM,
        "signal": Signal.POSITIVE,
        "confidence": Decimal("0.9"),
    }
    base.update(changes)
    return VerdictValues(**base)  # pyright: ignore[reportArgumentType]


def test_gone_quiet_triggers_on_day_ten() -> None:
    timing = ContactTiming(
        last_inbound_at=datetime(2026, 9, 7, 7, 0, tzinfo=UTC),
        last_outbound_at=datetime(2026, 9, 8, 7, 0, tzinfo=UTC),
    )

    assert has_gone_quiet(timing, NOW)


def test_gone_quiet_does_not_trigger_on_day_nine() -> None:
    timing = ContactTiming(
        last_inbound_at=datetime(2026, 9, 7, 7, 0, tzinfo=UTC),
        last_outbound_at=datetime(2026, 9, 9, 7, 0, tzinfo=UTC),
    )

    assert not has_gone_quiet(timing, NOW)


def test_a_first_message_nobody_ever_answered_has_not_gone_quiet() -> None:
    """It never started, so it is still "contacted, no reply yet".

    Calling it gone quiet hides the difference between being ignored from the
    start and a conversation that was running and stopped.
    """
    timing = ContactTiming(last_outbound_at=datetime(2026, 9, 1, 7, 0, tzinfo=UTC))

    assert not has_gone_quiet(timing, NOW)


def test_gone_quiet_needs_the_owner_to_have_written_last() -> None:
    timing = ContactTiming(
        last_outbound_at=datetime(2026, 9, 1, 7, 0, tzinfo=UTC),
        last_inbound_at=datetime(2026, 9, 2, 7, 0, tzinfo=UTC),
    )

    assert not has_gone_quiet(timing, NOW)


def test_the_status_becomes_gone_quiet_whatever_the_assistant_said() -> None:
    timing = ContactTiming(
        last_message_at=datetime(2026, 9, 8, 7, 0, tzinfo=UTC),
        last_inbound_at=datetime(2026, 9, 7, 7, 0, tzinfo=UTC),
        last_outbound_at=datetime(2026, 9, 8, 7, 0, tzinfo=UTC),
    )

    state = decide(_values(), timing, OwnerCorrections(), NOW, UTC_CALENDAR)

    assert state.status is ContactStatus.GONE_QUIET
    assert state.waiting_on is WaitingOn.THEM


def test_a_closed_conversation_is_not_reopened_by_silence() -> None:
    timing = ContactTiming(last_outbound_at=datetime(2026, 9, 1, 7, 0, tzinfo=UTC))

    state = decide(
        _values(status=ContactStatus.CLOSED), timing, OwnerCorrections(), NOW, UTC_CALENDAR
    )

    assert state.status is ContactStatus.CLOSED


def test_the_follow_up_date_skips_the_weekend() -> None:
    # Thursday 17 September 2026 plus five working days is Thursday the 24th,
    # not Tuesday the 22nd.
    assert add_working_days(date(2026, 9, 17), 5, SAT_SUN) == date(2026, 9, 24)


def test_adding_no_working_days_changes_nothing() -> None:
    assert add_working_days(date(2026, 9, 19), 0, SAT_SUN) == date(2026, 9, 19)


def test_waiting_on_them_is_chased_five_working_days_after_the_last_contact() -> None:
    timing = ContactTiming(last_message_at=datetime(2026, 9, 17, 9, 0, tzinfo=UTC))

    assert follow_up_date(WaitingOn.THEM, timing, NOW, UTC_CALENDAR) == date(2026, 9, 24)


def test_waiting_on_me_is_due_today() -> None:
    assert follow_up_date(WaitingOn.ME, ContactTiming(), NOW, UTC_CALENDAR) == TODAY


def test_waiting_on_nobody_has_no_date() -> None:
    assert follow_up_date(WaitingOn.NOBODY, ContactTiming(), NOW, UTC_CALENDAR) is None


def test_a_missing_due_date_is_filled_in() -> None:
    timing = ContactTiming(last_message_at=datetime(2026, 9, 17, 9, 0, tzinfo=UTC))

    state = decide(_values(), timing, OwnerCorrections(), NOW, UTC_CALENDAR)

    assert state.due_date == date(2026, 9, 24)


def test_a_due_date_the_assistant_gave_is_kept() -> None:
    state = decide(
        _values(due_date=date(2026, 9, 21)), ContactTiming(), OwnerCorrections(), NOW, UTC_CALENDAR
    )

    assert state.due_date == date(2026, 9, 21)


def test_low_confidence_goes_to_review() -> None:
    assert needs_review(_values(confidence=Decimal("0.59")))
    assert not needs_review(_values(confidence=Decimal("0.6")))


def test_an_unsure_verdict_goes_to_review_however_confident() -> None:
    assert needs_review(_values(relevance=Relevance.UNSURE, confidence=Decimal("1")))


def test_an_override_on_status_survives_a_contrary_verdict() -> None:
    corrections = OwnerCorrections(status=ContactStatus.IN_PROCESS)

    values = _values(status=ContactStatus.CLOSED, summary="New note")

    state = decide(values, ContactTiming(), corrections, NOW, UTC_CALENDAR)

    assert state.status is ContactStatus.IN_PROCESS
    assert state.summary == "New note"
    assert state.signal is Signal.POSITIVE


def test_an_override_beats_even_the_gone_quiet_rule() -> None:
    timing = ContactTiming(last_outbound_at=datetime(2026, 9, 1, 7, 0, tzinfo=UTC))
    corrections = OwnerCorrections(status=ContactStatus.MEETING_PLANNED)

    state = decide(_values(), timing, corrections, NOW, UTC_CALENDAR)

    assert state.status is ContactStatus.MEETING_PLANNED


def test_a_noise_verdict_needs_no_dates() -> None:
    state = decide(
        _values(relevance=Relevance.NOISE), ContactTiming(), OwnerCorrections(), NOW, UTC_CALENDAR
    )

    assert state.is_noise
    assert state.due_date is None


def test_waiting_for_the_result_of_an_interview_is_not_gone_quiet() -> None:
    """Silence is what a hiring process looks like while it runs.

    The owner had the interview and is waiting to hear; ten quiet days do not
    turn that into a conversation that died.
    """
    timing = ContactTiming(
        last_message_at=datetime(2026, 9, 8, 7, 0, tzinfo=UTC),
        last_inbound_at=datetime(2026, 9, 7, 7, 0, tzinfo=UTC),
        last_outbound_at=datetime(2026, 9, 8, 7, 0, tzinfo=UTC),
    )

    state = decide(
        _values(status=ContactStatus.IN_PROCESS),
        timing,
        OwnerCorrections(),
        NOW,
        UTC_CALENDAR,
    )

    assert state.status is ContactStatus.IN_PROCESS


def test_an_agreed_meeting_is_not_gone_quiet_either() -> None:
    timing = ContactTiming(
        last_message_at=datetime(2026, 9, 8, 7, 0, tzinfo=UTC),
        last_inbound_at=datetime(2026, 9, 7, 7, 0, tzinfo=UTC),
        last_outbound_at=datetime(2026, 9, 8, 7, 0, tzinfo=UTC),
    )

    state = decide(
        _values(status=ContactStatus.MEETING_PLANNED), timing, OwnerCorrections(), NOW, UTC_CALENDAR
    )

    assert state.status is ContactStatus.MEETING_PLANNED


# --- The owner's calendar (Plan 18) -------------------------------------------

LATE_EVENING_UTC = datetime(2026, 9, 18, 23, 30, tzinfo=UTC)


def test_waiting_on_me_is_due_on_the_owners_today_in_tokyo() -> None:
    tokyo = OwnerCalendar(zone=ZoneInfo("Asia/Tokyo"), weekend=SAT_SUN)

    due = follow_up_date(WaitingOn.ME, ContactTiming(), LATE_EVENING_UTC, tokyo)

    assert due == date(2026, 9, 19)


def test_waiting_on_me_is_due_on_the_owners_today_in_los_angeles() -> None:
    los_angeles = OwnerCalendar(zone=ZoneInfo("America/Los_Angeles"), weekend=SAT_SUN)

    due = follow_up_date(WaitingOn.ME, ContactTiming(), LATE_EVENING_UTC, los_angeles)

    assert due == date(2026, 9, 18)


def test_the_last_contact_day_is_read_in_the_owners_zone() -> None:
    # 23:30 UTC on Thursday 17 September is already Friday the 18th in Tokyo,
    # so five working days later is Friday the 25th rather than Thursday the 24th.
    timing = ContactTiming(last_message_at=datetime(2026, 9, 17, 23, 30, tzinfo=UTC))
    tokyo = OwnerCalendar(zone=ZoneInfo("Asia/Tokyo"), weekend=SAT_SUN)

    assert follow_up_date(WaitingOn.THEM, timing, NOW, tokyo) == date(2026, 9, 25)


def test_a_friday_saturday_weekend_is_skipped_instead() -> None:
    # Thursday 17 September plus five working days, skipping Friday and
    # Saturday, is Thursday the 24th reached via Sun, Mon, Tue, Wed, Thu.
    fri_sat = frozenset({Day.FRIDAY, Day.SATURDAY})

    assert add_working_days(date(2026, 9, 17), 5, fri_sat) == date(2026, 9, 24)
    assert add_working_days(date(2026, 9, 17), 1, fri_sat) == date(2026, 9, 20)


def test_an_owner_with_no_weekend_counts_every_day() -> None:
    assert add_working_days(date(2026, 9, 17), 5, frozenset()) == date(2026, 9, 22)


def test_a_week_with_no_working_day_is_refused() -> None:
    with pytest.raises(ValidationFailedError):
        OwnerCalendar(zone=UTC, weekend=frozenset(Day))
