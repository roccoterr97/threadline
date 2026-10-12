"""One calendar event, whichever calendar it came from.

Microsoft Graph and a calendar file (iCalendar, the ``.ics`` format Google,
iCloud, Fastmail and Proton publish) describe a meeting very differently. Each
reader maps its own source onto :class:`CalendarEvent`, so filing a meeting
under the people in it is the same code for every calendar.

An event never carries the description an organiser typed into it: the readers
do not copy it, so nothing downstream can store it by mistake.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class MeetingResponse(StrEnum):
    """The owner's answer to a meeting."""

    ACCEPTED = "accepted"
    TENTATIVE = "tentative"
    DECLINED = "declined"
    ORGANIZER = "organizer"
    NOT_ANSWERED = "not_answered"


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    """One calendar event or occurrence as a reader saw it, without its description.

    Attributes:
        event_id: The calendar's identifier for this event or occurrence.
        ical_uid: The identifier the meeting is filed under: one thread per
            meeting, and per occurrence of a repeating one.
        revision: Changes whenever the meeting does, so a moved or cancelled
            meeting gets a new message and an unchanged one does not.
        subject: The meeting's title, empty when there is none.
        start: When it starts, as an aware moment.
        end: When it ends, as an aware moment.
        organizer: The organiser, as an ``(address, name)`` pair.
        attendees: Everybody invited, as ``(address, name)`` pairs.
        is_cancelled: Whether the meeting was called off.
        is_organizer: Whether the owner organised it.
        response: The owner's answer.
        changed_at: When the event was created or last changed, as an aware moment.
        is_all_day: Whether it fills whole days rather than a stretch of hours.
    """

    event_id: str
    ical_uid: str
    revision: str
    subject: str
    start: datetime
    end: datetime
    organizer: tuple[str, str]
    attendees: tuple[tuple[str, str], ...]
    is_cancelled: bool
    is_organizer: bool
    response: MeetingResponse
    changed_at: datetime
    is_all_day: bool = False
