"""Downloads a calendar from its secret address and reads the events of a window.

The download goes through :class:`~tracker.infrastructure.web_download.WebDownload`,
which retries a passing failure and stops once the file grows past
``CALENDAR_FEED_MAX_BYTES``. Its errors name the address they fetched, and this
address is a secret, so each one is replaced here by an error that does not.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime, tzinfo
from typing import Final
from urllib.parse import unquote, urlsplit

from pydantic import SecretStr

from tracker.infrastructure.ical.parser import CalendarFile, is_one_address, read_calendar_file
from tracker.infrastructure.web_download import WebDownload
from tracker.shared.constants.calendar_feed import CALENDAR_FEED_MAX_BYTES
from tracker.shared.errors import (
    DownloadTooLargeError,
    SourceAuthError,
    SourceRequestRejectedError,
    SourceUnavailableError,
)
from tracker.shared.logging import get_logger

#: Downloads a file into memory, refusing one past a size in bytes.
Download = Callable[[str, int], Awaitable[bytes]]

#: Google's secret address names the calendar right after this path segment:
#: ``/calendar/ical/<calendar>/private-<key>/basic.ics``.
_GOOGLE_CALENDAR_SEGMENT: Final[str] = "ical"
_GOOGLE_HOST_SUFFIX: Final[str] = "google.com"
#: Google's own calendars (shared, rooms, holidays) are named on this domain;
#: none of them is a person's address.
_GOOGLE_CALENDAR_DOMAIN: Final[str] = "calendar.google.com"

_REFUSED: Final[str] = (
    "the calendar no longer accepts this secret address: it was reset, or secret "
    "addresses are turned off for your account"
)
_TOO_LARGE: Final[str] = (
    f"the calendar file is larger than {CALENDAR_FEED_MAX_BYTES // (1024 * 1024)} MB, "
    "more than Threadline reads"
)
_UNREACHABLE: Final[str] = "the calendar could not be reached"

_log = get_logger(__name__)


class CalendarFeed:
    """Reads a calendar through its secret iCalendar address."""

    def __init__(self, download: Download | None = None) -> None:
        """Bind the feed to a downloader.

        Args:
            download: Fetches a file with a size limit; the real downloader
                when omitted. Tests pass a fake, so they never reach the network.
        """
        self._download = WebDownload().fetch if download is None else download

    async def read(
        self,
        address: SecretStr,
        *,
        start: datetime,
        end: datetime,
        owner_addresses: Iterable[str],
        zone: tzinfo,
    ) -> CalendarFile:
        """Download the calendar and read the events between two moments.

        Args:
            address: The secret address, starting with ``https://``.
            start: Start of the window, as an aware moment.
            end: End of the window, as an aware moment.
            owner_addresses: The owner's own addresses.
            zone: The owner's time zone, for times written without one.

        Returns:
            The events in the window, and every address that is the owner's in
            this calendar: the ones the address and the file name.

        Raises:
            SourceAuthError: If the calendar refused the address.
            SourceUnavailableError: If the calendar could not be reached.
            DownloadTooLargeError: If the file is larger than Threadline reads.
            ValidationFailedError: If the address gave something else than a calendar.
        """
        content = await self._fetch(address)
        in_address = owner_in_address(address)
        # Reading a large calendar takes a while; the other sources keep
        # waiting for their answers in the meantime.
        found = await asyncio.to_thread(
            read_calendar_file,
            content,
            start=start,
            end=end,
            owner_addresses=[*owner_addresses, *in_address],
            zone=zone,
        )
        _log.info("calendar_feed_read", events=len(found.events))
        return CalendarFile(found.events, found.owner_addresses | in_address)

    async def _fetch(self, address: SecretStr) -> bytes:
        """Download the file, with errors that never repeat the address."""
        try:
            return await self._download(address.get_secret_value(), CALENDAR_FEED_MAX_BYTES)
        except SourceRequestRejectedError:
            _log.warning("calendar_feed_refused")
            raise SourceAuthError(_REFUSED) from None
        except DownloadTooLargeError:
            _log.warning("calendar_feed_too_large", limit_bytes=CALENDAR_FEED_MAX_BYTES)
            raise DownloadTooLargeError(_TOO_LARGE) from None
        except SourceUnavailableError:
            _log.warning("calendar_feed_unreachable")
            raise SourceUnavailableError(_UNREACHABLE) from None


def owner_in_address(address: SecretStr) -> frozenset[str]:
    """The owner's address, when the secret address names it, as Google's does.

    Google's address for a main calendar carries its owner's address
    (``…/calendar/ical/sam%40gmail.com/private-…/basic.ics``), so a Google
    account that is not one of the owner's mailboxes is still known as theirs.

    Args:
        address: The secret address.

    Returns:
        That one address, or nothing.
    """
    parts = urlsplit(address.get_secret_value())
    host = (parts.hostname or "").lower()
    if not host.endswith(_GOOGLE_HOST_SUFFIX):
        return frozenset()
    segments = parts.path.split("/")
    if _GOOGLE_CALENDAR_SEGMENT not in segments:
        return frozenset()
    position = segments.index(_GOOGLE_CALENDAR_SEGMENT) + 1
    named = unquote(segments[position]).strip().lower() if position < len(segments) else ""
    if not is_one_address(named) or named.endswith(_GOOGLE_CALENDAR_DOMAIN):
        return frozenset()
    return frozenset({named})
