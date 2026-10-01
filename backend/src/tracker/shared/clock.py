"""Injectable clock.

Nothing in the application calls :func:`datetime.now` directly. Services take a
:class:`Clock`, so tests stay deterministic and a run can be replayed at a fixed
point in time.

A clock knows two things: the instant, always in UTC, and the owner's time
zone. Instants are stored and compared in UTC; *dates* — "today", the day a
message arrived — are read in the owner's zone, because a follow-up due "today"
means the owner's today, not Greenwich's.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, tzinfo
from typing import Protocol, runtime_checkable
from zoneinfo import ZoneInfo


@runtime_checkable
class Clock(Protocol):
    """Reads the current moment in UTC and the current day in the owner's zone."""

    @property
    def zone(self) -> tzinfo:
        """The owner's time zone, which decides what a date is."""
        ...

    def now(self) -> datetime:
        """Return the current instant as a timezone-aware UTC datetime."""
        ...

    def today(self) -> date:
        """Return the current date in the owner's time zone."""
        ...


class SystemClock:
    """Clock backed by the operating system."""

    def __init__(self, zone: tzinfo = UTC) -> None:
        """Bind the clock to the owner's time zone.

        Args:
            zone: The zone dates are read in. Defaults to UTC for callers that
                only need instants, such as the secret store.
        """
        self._zone = zone

    @property
    def zone(self) -> tzinfo:
        """The owner's time zone."""
        return self._zone

    def now(self) -> datetime:
        """Return the current instant as a timezone-aware UTC datetime."""
        return datetime.now(UTC)

    def today(self) -> date:
        """Return the current date in the owner's time zone."""
        return self.now().astimezone(self._zone).date()


class FixedClock:
    """Clock frozen at one instant, for tests and for replaying a run."""

    def __init__(self, moment: datetime, zone: tzinfo = UTC) -> None:
        """Freeze the clock.

        Args:
            moment: The instant to report. Must be timezone-aware.
            zone: The owner's time zone, which decides what today is.

        Raises:
            ValueError: If ``moment`` has no timezone.
        """
        if moment.tzinfo is None:
            message = "FixedClock requires a timezone-aware datetime"
            raise ValueError(message)
        self._moment = moment.astimezone(UTC)
        self._zone = zone

    @property
    def zone(self) -> tzinfo:
        """The owner's time zone."""
        return self._zone

    def now(self) -> datetime:
        """Return the frozen instant in UTC."""
        return self._moment

    def today(self) -> date:
        """Return the date of the frozen instant in the owner's time zone."""
        return self._moment.astimezone(self._zone).date()


def zone_label(zone: tzinfo) -> str:
    """Name a time zone the way the owner configured it: ``Europe/Rome`` or ``UTC``.

    Args:
        zone: The time zone.

    Returns:
        Its IANA name when it has one, otherwise its abbreviation.
    """
    if isinstance(zone, ZoneInfo):
        return zone.key
    return zone.tzname(None) or str(zone)
