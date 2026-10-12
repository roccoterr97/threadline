"""Made-up calendar files, shaped like the one Google Calendar's secret address serves.

Every test builds its calendar from :func:`vevent` and :func:`calendar_file`, so
no test reaches the network, and :class:`FakeDownload` stands in for the
download, recording what it was asked for.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from tracker.shared.errors import (
    DownloadTooLargeError,
    SourceRequestRejectedError,
    SourceUnavailableError,
)

OWNER = "sam.rivera@mailbox.example"
HANNA = ("hanna.keller@northwind.example", "Hanna Keller")
#: A secret address shaped like Google's, for a calendar of another Google account.
GOOGLE_ADDRESS = (
    "https://calendar.google.com/calendar/ical/sam.rivera%40gmail.example/"
    "private-0123456789abcdef/basic.ics"
)
#: What the organiser typed into the invitation; it must never be stored.
ORGANISER_NOTES = "Dial-in code 4411, salary band attached"

_ROME = (
    "BEGIN:VTIMEZONE",
    "TZID:Europe/Rome",
    "BEGIN:STANDARD",
    "DTSTART:19701025T030000",
    "TZOFFSETFROM:+0200",
    "TZOFFSETTO:+0100",
    "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU",
    "END:STANDARD",
    "BEGIN:DAYLIGHT",
    "DTSTART:19700329T020000",
    "TZOFFSETFROM:+0100",
    "TZOFFSETTO:+0200",
    "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU",
    "END:DAYLIGHT",
    "END:VTIMEZONE",
)


def vevent(
    uid: str,
    *,
    summary: str = "Operations Associate - Intro Call",
    start: str = "DTSTART:20260924T090000Z",
    end: str = "DTEND:20260924T094500Z",
    organizer: tuple[str, str] | None = HANNA,
    attendees: Sequence[tuple[str, str, str]] = ((OWNER, OWNER, "ACCEPTED"),),
    status: str = "CONFIRMED",
    last_modified: str | None = "20260915T100000Z",
    extra: Sequence[str] = (),
) -> str:
    """One event, written the way Google writes it, description included."""
    lines = [
        "BEGIN:VEVENT",
        start,
        end,
        "DTSTAMP:20260918T070000Z",
        f"UID:{uid}",
        *extra,
    ]
    if organizer is not None:
        lines.append(f"ORGANIZER;CN={organizer[1]}:mailto:{organizer[0]}")
    lines.extend(
        f"ATTENDEE;CUTYPE=INDIVIDUAL;ROLE=REQ-PARTICIPANT;PARTSTAT={answer};CN={name};"
        f"X-NUM-GUESTS=0:mailto:{address}"
        for address, name, answer in attendees
    )
    lines.append("CREATED:20260914T100000Z")
    if last_modified is not None:
        lines.append(f"LAST-MODIFIED:{last_modified}")
    lines.extend(
        [
            f"DESCRIPTION:{ORGANISER_NOTES}",
            "LOCATION:Meeting room 4",
            "SEQUENCE:0",
            f"STATUS:{status}",
            f"SUMMARY:{summary}",
            "TRANSP:OPAQUE",
            "END:VEVENT",
        ]
    )
    return "\r\n".join(lines)


def calendar_file(*events: str, name: str = OWNER) -> bytes:
    """A whole calendar file holding the events, named after its owner as Google does."""
    lines = [
        "BEGIN:VCALENDAR",
        "PRODID:-//Google Inc//Google Calendar 70.9054//EN",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{name}",
        "X-WR-TIMEZONE:Europe/Rome",
        *_ROME,
        *events,
        "END:VCALENDAR",
    ]
    return ("\r\n".join(lines) + "\r\n").encode()


@dataclass
class FakeDownload:
    """Serves one calendar file, or fails the way the real download fails."""

    content: bytes = field(default_factory=lambda: calendar_file(vevent("intro@google.com")))
    #: ``"refused"``, ``"unreachable"`` or ``"too_large"`` to fail instead.
    failure: str | None = None
    calls: list[tuple[str, int]] = field(default_factory=list)

    async def __call__(self, url: str, max_bytes: int) -> bytes:
        self.calls.append((url, max_bytes))
        # The real download names the address it fetched in every error.
        if self.failure == "refused":
            raise SourceRequestRejectedError(f"{url} answered status 404")
        if self.failure == "unreachable":
            raise SourceUnavailableError(f"{url} could not be downloaded")
        if self.failure == "too_large":
            raise DownloadTooLargeError(f"{url} is larger than {max_bytes} bytes")
        return self.content
