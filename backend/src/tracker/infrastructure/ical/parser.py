"""Turns a calendar file into the events of a window, repeating ones expanded.

A calendar file names each meeting once, with its repetition rule (``RRULE``),
the days left out (``EXDATE``) and the occurrences that were moved
(``RECURRENCE-ID``). ``recurring-ical-events`` unfolds all of that into one
entry per occurrence inside the window, in the time zone each one was set in
(``TZID``, or the calendar's own ``X-WR-TIMEZONE``).

Only what Threadline writes a meeting's text from is copied out of each entry:
its title, times, people, status and the owner's answer. The description,
location and conference details are never read.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from typing import Any, Final

import icalendar
import recurring_ical_events

from tracker.domain.calendar import CalendarEvent, MeetingResponse
from tracker.shared.constants.calendar_feed import NOT_A_PERSON_TYPES
from tracker.shared.errors import ValidationFailedError

#: Every calendar file starts with this line (after an optional byte-order mark).
_FILE_START: Final[bytes] = b"BEGIN:VCALENDAR"
_BYTE_ORDER_MARK: Final[bytes] = b"\xef\xbb\xbf"
#: How much of the file is looked at to tell a calendar from a web page.
_HEAD_BYTES: Final[int] = 256
_MAILTO: Final[str] = "mailto:"
_CANCELLED: Final[str] = "CANCELLED"
_ONE_DAY: Final[timedelta] = timedelta(days=1)
_STAMP: Final[str] = "%Y%m%dT%H%M%SZ"
_DAY_STAMP: Final[str] = "%Y%m%d"
#: A single e-mail address, as a calendar names its owner.
_ONE_ADDRESS: Final[re.Pattern[str]] = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")

#: The owner's answer, as a calendar file spells it (``PARTSTAT``).
_ANSWERS: Final[dict[str, MeetingResponse]] = {
    "ACCEPTED": MeetingResponse.ACCEPTED,
    "TENTATIVE": MeetingResponse.TENTATIVE,
    "DECLINED": MeetingResponse.DECLINED,
}

_NOT_A_CALENDAR: Final[str] = (
    "this address did not give a calendar file - copy the 'Secret address in iCal format'"
)


@dataclass(frozen=True, slots=True)
class CalendarFile:
    """What one calendar file holds for a window.

    Attributes:
        events: One entry per event or occurrence in the window.
        owner_addresses: Addresses the calendar itself names as its owner's
            (Google calls a main calendar by its owner's address).
    """

    events: tuple[CalendarEvent, ...]
    owner_addresses: frozenset[str]


@dataclass(frozen=True, slots=True)
class _Owner:
    """Who the owner is in this calendar, and their time zone for floating times."""

    addresses: frozenset[str]
    zone: tzinfo


def read_calendar_file(
    content: bytes,
    *,
    start: datetime,
    end: datetime,
    owner_addresses: Iterable[str],
    zone: tzinfo,
) -> CalendarFile:
    """Read the events of a window out of a calendar file.

    Args:
        content: The file as downloaded.
        start: Start of the window, as an aware moment.
        end: End of the window, as an aware moment.
        owner_addresses: The owner's own addresses.
        zone: The owner's time zone, for times written without one.

    Returns:
        The events in the window, and the address the calendar belongs to.

    Raises:
        ValidationFailedError: If the content is not a calendar file.
    """
    calendar = _parse(content)
    named = _owner_named_by(calendar)
    owner = _Owner(frozenset(address.lower() for address in owner_addresses) | named, zone)
    repeating = _repeating_ids(calendar)
    try:
        occurrences = recurring_ical_events.of(calendar, skip_bad_series=True).between(start, end)
        events = tuple(
            event
            for component in occurrences
            if (event := _event(component, owner, repeating)) is not None
        )
    except ValueError as error:
        raise ValidationFailedError(_NOT_A_CALENDAR) from error
    return CalendarFile(events=events, owner_addresses=named)


def is_one_address(text: str) -> bool:
    """Whether a piece of text is exactly one e-mail address.

    Args:
        text: The text, already trimmed.

    Returns:
        True for ``sam@example.com``; false for a name, a list or a room id.
    """
    return _ONE_ADDRESS.match(text) is not None


def _parse(content: bytes) -> icalendar.Calendar:
    """Parse the file, refusing anything that is not a calendar (such as a web page)."""
    head = content[:_HEAD_BYTES].lstrip().removeprefix(_BYTE_ORDER_MARK).lstrip()
    if not head.upper().startswith(_FILE_START):
        raise ValidationFailedError(_NOT_A_CALENDAR)
    try:
        return icalendar.Calendar.from_ical(content)
    except ValueError as error:
        raise ValidationFailedError(_NOT_A_CALENDAR) from error


def _owner_named_by(calendar: icalendar.Calendar) -> frozenset[str]:
    """The address a calendar is named after, which is its owner's for Google's main one."""
    name = str(calendar.get("X-WR-CALNAME", "")).strip().lower()
    return frozenset({name}) if is_one_address(name) else frozenset()


def _repeating_ids(calendar: icalendar.Calendar) -> frozenset[str]:
    """The meetings that repeat: each occurrence of those is filed on its own."""
    return frozenset(
        str(component.get("UID", ""))
        for component in calendar.walk("VEVENT")
        if any(component.get(key) is not None for key in ("RRULE", "RDATE", "RECURRENCE-ID"))
    )


def _event(component: Any, owner: _Owner, repeating: frozenset[str]) -> CalendarEvent | None:  # noqa: ANN401 - icalendar is untyped
    """Turn one occurrence into an event, or ``None`` when it has no identifier or start."""
    uid = str(component.get("UID", "")).strip()
    times = _times(component, owner.zone)
    if not uid or times is None:
        return None
    start, end, all_day = times
    occurrence = _occurrence_id(uid, component, repeating)
    organizer = _address(component.get("ORGANIZER"))
    attendees = _attendees(component)
    is_organizer = not organizer[0] or organizer[0] in owner.addresses
    cancelled = str(component.get("STATUS", "")).upper() == _CANCELLED
    modified = _moment(component.get("LAST-MODIFIED"))
    return CalendarEvent(
        event_id=occurrence,
        ical_uid=occurrence,
        revision=_revision(modified, start, cancelled=cancelled),
        subject=str(component.get("SUMMARY", "")).strip(),
        start=start,
        end=end,
        organizer=organizer,
        attendees=attendees,
        is_cancelled=cancelled,
        is_organizer=is_organizer,
        response=(
            MeetingResponse.ORGANIZER if is_organizer else _answer(component, owner.addresses)
        ),
        changed_at=modified or _moment(component.get("CREATED")) or start,
        is_all_day=all_day,
    )


def _occurrence_id(uid: str, component: Any, repeating: frozenset[str]) -> str:  # noqa: ANN401 - icalendar is untyped
    """One identifier per meeting, and per occurrence of a repeating one."""
    recurrence = component.get("RECURRENCE-ID")
    if uid not in repeating or recurrence is None:
        return uid
    return f"{uid}#{_stamp(recurrence.dt)}"


def _revision(modified: datetime | None, start: datetime, *, cancelled: bool) -> str:
    """What changes when the meeting does.

    The last change is the calendar's own word for it. A calendar that does
    not say when an entry last changed is followed by its time and status
    instead, so moving or cancelling it still counts as a change.
    """
    if modified is not None:
        return modified.isoformat()
    return f"{_stamp(start)}-{_CANCELLED.lower()}" if cancelled else _stamp(start)


def _times(component: Any, zone: tzinfo) -> tuple[datetime, datetime, bool] | None:  # noqa: ANN401 - icalendar is untyped
    """Start, end and whether it fills whole days; ``None`` without a start."""
    raw_start = _value(component.get("DTSTART"))
    if not isinstance(raw_start, date):
        return None
    raw_end = _value(component.get("DTEND"))
    if not isinstance(raw_end, date):
        duration = _value(component.get("DURATION"))
        fallback = _ONE_DAY if not isinstance(raw_start, datetime) else timedelta()
        raw_end = raw_start + (duration if isinstance(duration, timedelta) else fallback)
    all_day = not isinstance(raw_start, datetime)
    return _utc_moment(raw_start, zone), _utc_moment(raw_end, zone), all_day


def _utc_moment(value: date, zone: tzinfo) -> datetime:
    """A moment in UTC: a day starts at the owner's midnight; a floating time is theirs."""
    if isinstance(value, datetime):
        moment = value if value.tzinfo is not None else value.replace(tzinfo=zone)
    else:
        moment = datetime.combine(value, time(), tzinfo=zone)
    return moment.astimezone(UTC)


def _stamp(value: date) -> str:
    """Write a moment in UTC, or a day, the compact way calendar files do."""
    if isinstance(value, datetime):
        moment = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return moment.astimezone(UTC).strftime(_STAMP)
    return value.strftime(_DAY_STAMP)


def _moment(prop: Any) -> datetime | None:  # noqa: ANN401 - icalendar is untyped
    """Read a ``LAST-MODIFIED`` or ``CREATED`` value as an aware moment."""
    value = _value(prop)
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _value(prop: Any) -> Any:  # noqa: ANN401 - icalendar is untyped
    """The Python value behind a date, time or duration property, or ``None``."""
    return getattr(prop, "dt", None)


def _attendees(component: Any) -> tuple[tuple[str, str], ...]:  # noqa: ANN401 - icalendar is untyped
    """Everybody invited who is a person with an address; rooms and equipment are not."""
    found: list[tuple[str, str]] = []
    for entry in _listed(component.get("ATTENDEE")):
        kind = str(getattr(entry, "params", {}).get("CUTYPE", "")).upper()
        address, name = _address(entry)
        if address and kind not in NOT_A_PERSON_TYPES:
            found.append((address, name))
    return tuple(found)


def _answer(component: Any, owner: frozenset[str]) -> MeetingResponse:  # noqa: ANN401 - icalendar is untyped
    """The owner's answer, read from their own line among the invitees."""
    for entry in _listed(component.get("ATTENDEE")):
        address, _ = _address(entry)
        if address in owner:
            status = str(getattr(entry, "params", {}).get("PARTSTAT", "")).upper()
            return _ANSWERS.get(status, MeetingResponse.NOT_ANSWERED)
    return MeetingResponse.NOT_ANSWERED


def _listed(value: Any) -> list[Any]:  # noqa: ANN401 - icalendar is untyped
    """A property that may appear once or many times, as a list."""
    if value is None:
        return []
    return list(value) if isinstance(value, list) else [value]


def _address(value: Any) -> tuple[str, str]:  # noqa: ANN401 - icalendar is untyped
    """Read an organiser or invitee as an ``(address, name)`` pair."""
    if value is None:
        return ("", "")
    text = str(value).strip()
    if text.lower().startswith(_MAILTO):
        text = text[len(_MAILTO) :]
    address = text.strip().lower() if is_one_address(text.strip()) else ""
    name = str(getattr(value, "params", {}).get("CN", "")).strip()
    return (address, name)
