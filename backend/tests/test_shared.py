"""The clock never reads the wall clock in tests, and logs never carry secrets."""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from tracker.shared.clock import FixedClock, SystemClock, zone_label
from tracker.shared.errors import (
    ConfigurationError,
    DatabaseUnavailableError,
    TrackerError,
)
from tracker.shared.logging import redact_sensitive_fields


def test_fixed_clock_reports_the_instant_it_was_given() -> None:
    clock = FixedClock(datetime(2026, 9, 18, 7, 0, tzinfo=UTC))

    assert clock.now() == datetime(2026, 9, 18, 7, 0, tzinfo=UTC)
    assert clock.today() == date(2026, 9, 18)


def test_fixed_clock_refuses_a_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        FixedClock(datetime(2026, 9, 18, 7, 0))  # noqa: DTZ001


def test_system_clock_is_timezone_aware() -> None:
    assert SystemClock().now().tzinfo is not None


#: 23:30 UTC on 18 September: already the 19th in Tokyo, still the 18th in Los Angeles.
LATE_EVENING_UTC = datetime(2026, 9, 18, 23, 30, tzinfo=UTC)


def test_today_is_tomorrow_in_tokyo_at_half_past_eleven_utc() -> None:
    clock = FixedClock(LATE_EVENING_UTC, ZoneInfo("Asia/Tokyo"))

    assert clock.today() == date(2026, 9, 19)
    assert clock.now() == LATE_EVENING_UTC


def test_today_is_still_today_in_los_angeles_at_half_past_eleven_utc() -> None:
    clock = FixedClock(LATE_EVENING_UTC, ZoneInfo("America/Los_Angeles"))

    assert clock.today() == date(2026, 9, 18)


def test_a_clock_without_a_zone_reads_dates_in_utc() -> None:
    assert FixedClock(LATE_EVENING_UTC).today() == date(2026, 9, 18)
    assert SystemClock().zone is UTC


def test_system_clock_reports_its_zone() -> None:
    zone = ZoneInfo("Europe/Rome")

    assert SystemClock(zone).zone is zone


def test_zones_are_labelled_by_their_configured_name() -> None:
    assert zone_label(ZoneInfo("Europe/Rome")) == "Europe/Rome"
    assert zone_label(UTC) == "UTC"


def test_errors_share_one_hierarchy_with_stable_codes() -> None:
    assert issubclass(ConfigurationError, TrackerError)
    assert issubclass(DatabaseUnavailableError, TrackerError)
    assert ConfigurationError("broken").code == "configuration_invalid"
    assert DatabaseUnavailableError("down").message == "down"


def test_forbidden_fields_are_redacted() -> None:
    event = {"event": "collected", "token": "abc", "body": "hello", "items_new": 3}

    redacted = redact_sensitive_fields(None, "info", event)

    assert redacted["token"] == "[redacted]"
    assert redacted["body"] == "[redacted]"
    assert redacted["items_new"] == 3


def test_message_content_and_credentials_are_never_written_out() -> None:
    """Judged by behaviour, not by a list: callers invent field names.

    Matching is by substring, so a name nobody thought to list — an
    ``authorization`` header, a ``token_encryption_key`` — is still covered.
    """
    event = {
        "event": "collected",
        "body": "hello",
        "subject": "Coffee?",
        "access_token": "abc",
        "service_role_key": "abc",
        "authorization": "Bearer abc",
        "api_key": "abc",
        "token_encryption_key": "abc",
        "items_new": 3,
    }

    redacted = redact_sensitive_fields(None, "info", event)

    assert redacted["items_new"] == 3
    assert redacted["event"] == "collected"
    for field in event:
        if field in {"event", "items_new"}:
            continue
        assert redacted[field] == "[redacted]", f"{field} was written out"


def test_a_secret_one_level_down_is_redacted_too() -> None:
    """A caller can pass a dictionary of headers or a list of records."""
    event = {
        "event": "request",
        "headers": {"Authorization": "Bearer abc", "Accept": "application/json"},
        "records": [{"id": 1, "refresh_token": "abc"}],
    }

    redacted = redact_sensitive_fields(None, "info", event)

    headers = redacted["headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == "[redacted]"
    assert headers["Accept"] == "application/json"
    records = redacted["records"]
    assert isinstance(records, list)
    assert records[0]["refresh_token"] == "[redacted]"
    assert records[0]["id"] == 1
