"""Collect the owner's Microsoft calendar as a source.

This module only reads the Outlook calendar through Microsoft Graph, with the
mailbox's own sign-in. Which meetings are kept, who each is filed under and
what is never stored is decided in :mod:`tracker.services.collection.meeting_filing`,
the same for every calendar.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from tracker.domain.calendar import CalendarEvent
from tracker.domain.enums import Channel
from tracker.domain.rules import RulePack
from tracker.infrastructure.microsoft.auth import MicrosoftAuthenticator
from tracker.infrastructure.microsoft.client import GraphMailbox
from tracker.infrastructure.secret_store import SecretStore
from tracker.repositories import Repositories
from tracker.services.collection.meeting_filing import MeetingFiler
from tracker.services.collection.models import CollectionReport, SaveStep
from tracker.shared.clock import Clock
from tracker.shared.config import Settings
from tracker.shared.constants.collection import CALENDAR_FUTURE_DAYS, CALENDAR_PAST_DAYS
from tracker.shared.logging import get_logger

_log = get_logger(__name__)


class CalendarCollector:
    """Reads the owner's Outlook calendar and stores the meetings with other people."""

    def __init__(
        self,
        repositories: Repositories,
        settings: Settings,
        clock: Clock,
        rules: RulePack,
    ) -> None:
        """Bind the collector to the database, the configuration and a clock.

        Args:
            repositories: The repository container.
            settings: The process configuration.
            clock: Supplies the current instant.
            rules: The owner's collection rules.
        """
        self._repositories = repositories
        self._settings = settings
        self._clock = clock
        self._filer = MeetingFiler(repositories, settings, clock, rules)

    def collect(self) -> CollectionReport:
        """Read the calendar around today and store the meetings with people.

        Returns:
            What the run found and wrote, or a "not configured" report when
            Outlook is not one of the owner's mailboxes.

        Raises:
            SourceAuthError: If nobody has signed in, or Microsoft refused.
            SourceUnavailableError: If the calendar could not be reached.
        """
        return asyncio.run(self.read())()

    async def read(self) -> SaveStep:
        """Read the calendar around today, and hand back the step that stores it.

        Returns:
            The step that stores the meetings. When Outlook is not one of the
            owner's mailboxes it only reports "not configured".

        Raises:
            SourceAuthError: If nobody has signed in, or Microsoft refused.
            SourceUnavailableError: If the calendar could not be reached.
        """
        if not self._settings.outlook_enabled:
            # This calendar is Outlook's; without the Outlook mailbox there is none.
            _log.info("calendar_not_configured")
            return lambda: CollectionReport(channel=Channel.CALENDAR, not_configured=True)
        now = self._clock.now()
        events = await self._events_between(
            now - timedelta(days=CALENDAR_PAST_DAYS),
            now + timedelta(days=CALENDAR_FUTURE_DAYS),
        )
        _log.info("calendar_scanned", events=len(events))
        return lambda: self._filer.file(events, now)

    async def _events_between(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        """Read every event between two moments."""
        store = SecretStore(
            self._repositories.app_secrets,
            self._settings.token_encryption_key,
            self._clock,
        )
        authenticator = MicrosoftAuthenticator.for_settings(store, self._clock, self._settings)
        async with authenticator, GraphMailbox(authenticator) as calendar:
            return await calendar.list_events(start, end)
