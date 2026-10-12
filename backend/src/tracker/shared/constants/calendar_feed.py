"""Fixed facts about reading a calendar from its secret iCalendar address.

Google Calendar, iCloud, Fastmail and Proton each give a private calendar an
address that serves the whole calendar as one ``.ics`` file. Threadline reads
the file once per run, so its size is capped here and nowhere else.
"""

from __future__ import annotations

from typing import Final

#: The setting that holds the secret address. It is a secret: anyone with the
#: address can read the whole calendar.
GOOGLE_CALENDAR_URL_SETTING: Final[str] = "GOOGLE_CALENDAR_URL"

#: The most a calendar file may weigh. Google's file holds every event ever
#: made, not just recent ones, so the cap leaves room for years of meetings
#: while still stopping a wrong address that serves something huge.
CALENDAR_FEED_MAX_BYTES: Final[int] = 30 * 1024 * 1024

#: Where Google Calendar's settings open, with each calendar listed on the left.
GOOGLE_CALENDAR_SETTINGS_PAGE: Final[str] = "https://calendar.google.com/calendar/r/settings"

#: The part of the accounts guide that shows every click.
GOOGLE_CALENDAR_GUIDE_SECTION: Final[str] = "'Google Calendar' in docs/setup-your-accounts.md"

#: Calendar-user types that are rooms and equipment, never people.
NOT_A_PERSON_TYPES: Final[frozenset[str]] = frozenset({"RESOURCE", "ROOM"})
