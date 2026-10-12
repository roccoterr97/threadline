"""The morning summary offers LinkedIn now and then while it is not connected."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.conftest import as_client
from tests.summary_world import TODAYS_RUN, sample_client
from tracker.domain.linkedin_offer import linkedin_offer_due
from tracker.repositories import build_repositories
from tracker.schemas.summary import SummaryEmail
from tracker.services.summary.builder import SummaryBuilder
from tracker.shared.clock import FixedClock
from tracker.shared.config import Settings
from tracker.shared.constants.summary import LINKEDIN_GUIDE_URL

#: The sample data's first daily run started at 05:00 UTC on this day.
_FIRST_RUN_DAY = date(2026, 9, 17)
_OFFER = "Add your LinkedIn messages: about 5 minutes, profiles in the EEA or Switzerland only."


def _morning(day: date) -> FixedClock:
    """Seven in the morning, UTC, on one day."""
    return FixedClock(datetime(day.year, day.month, day.day, 7, 0, tzinfo=UTC))


def _build(settings: Settings, clock: FixedClock) -> SummaryEmail:
    """Build the summary of the sample data's latest run at one moment."""
    repositories = build_repositories(as_client(sample_client()))
    return SummaryBuilder(repositories, settings, clock).build(TODAYS_RUN)


# --- The policy -------------------------------------------------------------------


@pytest.mark.parametrize("days", [0, 7, 14, 21])
def test_the_offer_comes_on_the_first_day_and_once_a_week_after(days: int) -> None:
    assert linkedin_offer_due(_FIRST_RUN_DAY, _FIRST_RUN_DAY + timedelta(days=days))


@pytest.mark.parametrize("days", [1, 2, 6, 8, 13, 20, 22, 27])
def test_the_offer_never_comes_two_days_running(days: int) -> None:
    assert not linkedin_offer_due(_FIRST_RUN_DAY, _FIRST_RUN_DAY + timedelta(days=days))


@pytest.mark.parametrize("days", [28, 35, 365, -1])
def test_the_offer_stops_after_four_weeks_and_never_comes_before_the_first_run(
    days: int,
) -> None:
    assert not linkedin_offer_due(_FIRST_RUN_DAY, _FIRST_RUN_DAY + timedelta(days=days))


# --- In the summary ---------------------------------------------------------------


def test_the_first_mornings_summary_offers_linkedin_when_it_is_not_connected(
    settings_without_linkedin_key: Settings,
) -> None:
    email = _build(settings_without_linkedin_key, _morning(_FIRST_RUN_DAY))

    assert email.content.linkedin_offer
    assert f"{_OFFER} Run 'uv run tracker setup linkedin' on your computer." in email.text_body
    assert f"How: {LINKEDIN_GUIDE_URL}" in email.text_body
    assert _OFFER in email.html_body
    assert f"href='{LINKEDIN_GUIDE_URL}'" in email.html_body


def test_the_next_mornings_summary_does_not_offer_it_again(
    settings_without_linkedin_key: Settings,
) -> None:
    email = _build(settings_without_linkedin_key, _morning(_FIRST_RUN_DAY + timedelta(days=1)))

    assert not email.content.linkedin_offer
    assert _OFFER not in email.text_body
    assert _OFFER not in email.html_body


def test_a_week_later_the_summary_offers_it_once_more(
    settings_without_linkedin_key: Settings,
) -> None:
    email = _build(settings_without_linkedin_key, _morning(_FIRST_RUN_DAY + timedelta(days=7)))

    assert email.content.linkedin_offer


def test_an_owner_with_linkedin_connected_is_never_offered_it(settings: Settings) -> None:
    assert not _build(settings, _morning(_FIRST_RUN_DAY)).content.linkedin_offer


def test_the_days_are_counted_on_the_owners_calendar(
    settings_without_linkedin_key: Settings,
) -> None:
    # 23:30 UTC on the 23rd is already the 24th in Tokyo: a week after the first run there.
    tokyo = FixedClock(datetime(2026, 9, 23, 23, 30, tzinfo=UTC), ZoneInfo("Asia/Tokyo"))
    utc = FixedClock(datetime(2026, 9, 23, 23, 30, tzinfo=UTC), UTC)

    assert _build(settings_without_linkedin_key, tokyo).content.linkedin_offer
    assert not _build(settings_without_linkedin_key, utc).content.linkedin_offer
