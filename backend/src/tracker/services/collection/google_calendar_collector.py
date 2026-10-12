"""Collect a calendar read from its secret iCalendar address, such as Google Calendar's.

The owner pastes the calendar's "secret address in iCal format" once; no
sign-in or app approval is involved. The same reader works for any private
``.ics`` address (iCloud, Fastmail, Proton), but the set-up offers it as
Google Calendar. Meetings are filed exactly like the Outlook calendar's, by
:mod:`tracker.services.collection.meeting_filing`, on the same calendar channel.

Without an address the collector reads nothing and reports "not configured",
which is not a failure.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from tracker.domain.enums import Channel
from tracker.domain.rules import RulePack
from tracker.infrastructure.ical.feed import CalendarFeed, Download
from tracker.repositories import Repositories
from tracker.services.collection.meeting_filing import MeetingFiler
from tracker.services.collection.models import CollectionReport, SaveStep
from tracker.shared.clock import Clock
from tracker.shared.config import Settings
from tracker.shared.constants.collection import CALENDAR_FUTURE_DAYS, CALENDAR_PAST_DAYS
from tracker.shared.logging import get_logger

_log = get_logger(__name__)


class GoogleCalendarCollector:
    """Reads a calendar from its secret address and stores the meetings with other people."""

    def __init__(
        self,
        repositories: Repositories,
        settings: Settings,
        clock: Clock,
        rules: RulePack,
        download: Download | None = None,
    ) -> None:
        """Bind the collector to the database, the configuration and a clock.

        Args:
            repositories: The repository container.
            settings: The process configuration.
            clock: Supplies the current instant and the owner's time zone.
            rules: The owner's collection rules.
            download: Fetches the calendar file; the real downloader when omitted.
        """
        self._repositories = repositories
        self._settings = settings
        self._clock = clock
        self._rules = rules
        self._feed = CalendarFeed(download)

    def collect(self) -> CollectionReport:
        """Read the calendar around today and store the meetings with people.

        Returns:
            What the run found and wrote, or a "not configured" report when no
            secret address is saved.

        Raises:
            SourceAuthError: If the calendar no longer accepts the address.
            SourceUnavailableError: If the calendar could not be reached.
            DownloadTooLargeError: If the calendar file is too large to read.
            ValidationFailedError: If the address gave something else than a calendar.
        """
        return asyncio.run(self.read())()

    async def read(self) -> SaveStep:
        """Read the calendar around today, and hand back the step that stores it.

        Returns:
            The step that stores the meetings. Without a saved address it only
            reports "not configured", and no request was made.

        Raises:
            SourceAuthError: If the calendar no longer accepts the address.
            SourceUnavailableError: If the calendar could not be reached.
            DownloadTooLargeError: If the calendar file is too large to read.
            ValidationFailedError: If the address gave something else than a calendar.
        """
        address = self._settings.google_calendar_url
        if address is None:
            _log.info("google_calendar_not_configured")
            return lambda: CollectionReport(channel=Channel.CALENDAR, not_configured=True)
        now = self._clock.now()
        found = await self._feed.read(
            address,
            start=now - timedelta(days=CALENDAR_PAST_DAYS),
            end=now + timedelta(days=CALENDAR_FUTURE_DAYS),
            owner_addresses=self._settings.owner_email_addresses,
            zone=self._clock.zone,
        )
        filer = MeetingFiler(
            self._repositories,
            self._settings,
            self._clock,
            self._rules,
            also_owner=found.owner_addresses,
        )
        return lambda: filer.file(found.events, now)
