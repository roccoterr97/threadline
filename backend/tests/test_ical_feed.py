"""Downloading a calendar from its secret address, without ever repeating the address."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from pydantic import SecretStr

from tests.ical_world import GOOGLE_ADDRESS, OWNER, FakeDownload, calendar_file, vevent
from tracker.infrastructure.ical.feed import CalendarFeed, owner_in_address
from tracker.infrastructure.ical.parser import CalendarFile
from tracker.infrastructure.web_download import WebDownload
from tracker.shared.constants.calendar_feed import CALENDAR_FEED_MAX_BYTES
from tracker.shared.errors import (
    DownloadTooLargeError,
    SourceAuthError,
    SourceUnavailableError,
    TrackerError,
)

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 9, 18, 7, 0, tzinfo=UTC)
FASTMAIL_ADDRESS = "https://user.fm/c1-secret-calendar/calendar.ics"


async def read(download: FakeDownload | None, address: str = GOOGLE_ADDRESS) -> CalendarFile:
    """Read the usual window through a feed on the given download."""
    return await CalendarFeed(download).read(
        SecretStr(address),
        start=NOW - timedelta(days=30),
        end=NOW + timedelta(days=60),
        owner_addresses=(OWNER,),
        zone=UTC,
    )


async def test_the_calendar_is_downloaded_once_with_the_size_cap() -> None:
    download = FakeDownload()

    found = await read(download)

    assert download.calls == [(GOOGLE_ADDRESS, CALENDAR_FEED_MAX_BYTES)]
    assert [event.ical_uid for event in found.events] == ["intro@google.com"]


async def test_the_google_account_in_the_address_is_the_owners() -> None:
    gmail = "sam.rivera@gmail.example"
    download = FakeDownload(
        calendar_file(vevent("coffee@google.com", organizer=(gmail, "Sam")), name="Work")
    )

    found = await read(download)

    assert found.owner_addresses == {gmail}
    assert found.events[0].is_organizer is True


@pytest.mark.parametrize(
    "address",
    [
        FASTMAIL_ADDRESS,
        "https://calendar.google.com/calendar/ical/c_abc%40group.calendar.google.com/private-1/basic.ics",
        "https://calendar.google.com/calendar/ical/",
        "https://calendar.google.com/somewhere/else.ics",
    ],
)
async def test_other_addresses_name_no_owner(address: str) -> None:
    assert owner_in_address(SecretStr(address)) == frozenset()


@pytest.mark.parametrize(
    ("failure", "error", "says"),
    [
        ("refused", SourceAuthError, "no longer accepts this secret address"),
        ("unreachable", SourceUnavailableError, "could not be reached"),
        ("too_large", DownloadTooLargeError, "larger than 30 MB"),
    ],
)
async def test_a_failure_never_repeats_the_secret_address(
    failure: str, error: type[TrackerError], says: str
) -> None:
    with pytest.raises(error) as raised:
        await read(FakeDownload(failure=failure))

    assert says in raised.value.message
    assert "private-" not in raised.value.message
    assert "calendar.google.com" not in raised.value.message
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__ is True


async def test_a_refusal_is_not_taken_for_an_outage() -> None:
    with pytest.raises(SourceAuthError) as raised:
        await read(FakeDownload(failure="refused"))

    assert not isinstance(raised.value, SourceUnavailableError)


async def test_the_real_download_is_used_by_default_and_follows_its_answer() -> None:
    """The real downloader, against a made-up server: a gone address is a refusal."""
    with respx.mock:
        respx.get(FASTMAIL_ADDRESS).mock(return_value=httpx.Response(404))
        with pytest.raises(SourceAuthError):
            await read(None, FASTMAIL_ADDRESS)


async def test_the_real_download_reads_a_served_calendar() -> None:
    content = calendar_file(vevent("intro@google.com"))
    with respx.mock:
        respx.get(FASTMAIL_ADDRESS).mock(return_value=httpx.Response(200, content=content))
        found = await CalendarFeed(WebDownload().fetch).read(
            SecretStr(FASTMAIL_ADDRESS),
            start=NOW - timedelta(days=30),
            end=NOW + timedelta(days=60),
            owner_addresses=(OWNER,),
            zone=UTC,
        )

    assert len(found.events) == 1
