"""Google Calendar, optional: read through the calendar's secret address.

No Google sign-in and no app approval: Google Calendar gives every calendar a
"secret address in iCal format", and whoever has it can read the calendar.
The step has one stop, the one thing only the person can do: copy that
address and paste it. Pressing Enter instead skips the step. The address is
checked once (downloaded and read), saved in ``.env`` and sent to GitHub
without a question, since sending it is the only useful answer.

Any other private ``.ics`` address (iCloud, Fastmail, Proton) works the same.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

from pydantic import SecretStr

from tracker.infrastructure.ical.feed import CalendarFeed
from tracker.services.setup.context import SetupContext
from tracker.services.setup.github_values import offer_to_send
from tracker.services.setup.models import StepName
from tracker.shared.calendar_address import calendar_feed_address
from tracker.shared.constants.calendar_feed import (
    GOOGLE_CALENDAR_GUIDE_SECTION,
    GOOGLE_CALENDAR_SETTINGS_PAGE,
    GOOGLE_CALENDAR_URL_SETTING,
)
from tracker.shared.constants.collection import CALENDAR_FUTURE_DAYS, CALENDAR_PAST_DAYS
from tracker.shared.constants.mailbox import ImapProvider
from tracker.shared.errors import ValidationFailedError

#: The setting that names the IMAP mailbox's provider.
_IMAP_PROVIDER: Final[str] = "IMAP_PROVIDER"

_HOW_TO_COPY: Final[tuple[str, ...]] = (
    "Threadline reads your Google Calendar through its secret address: no Google",
    "sign-in, and nothing to approve. On the Google Calendar page that opens:",
    "  1. On the left, under 'Settings for my calendars', click your calendar.",
    "  2. Click 'Integrate calendar'.",
    "  3. Under 'Secret address in iCal format', click the copy button.",
    "Then paste it here. It stays hidden, and Threadline keeps it like a password.",
    "No 'Secret address'? Your organisation's Google administrator has turned it",
    f"off; press Enter to skip. Every click is in {GOOGLE_CALENDAR_GUIDE_SECTION}.",
)

_PROMPT: Final[str] = "Secret address in iCal format (press Enter to skip)"

_SKIPPED: Final[str] = (
    f"Skipped. Run 'uv run tracker setup {StepName.GOOGLE_CALENDAR}' whenever you want it."
)


class GoogleCalendarStep:
    """Saves the calendar's secret address once Google has answered with a calendar."""

    name = StepName.GOOGLE_CALENDAR
    title = "Google Calendar (optional)"

    async def is_done(self, ctx: SetupContext) -> bool:
        """Done when a secret address is saved."""
        return ctx.env.get(GOOGLE_CALENDAR_URL_SETTING) is not None

    async def run(self, ctx: SetupContext) -> None:
        """Show where the address is, take it, check it once, save it and send it on."""
        io = ctx.io
        for line in _HOW_TO_COPY:
            io.say(line)
        io.open_page(GOOGLE_CALENDAR_SETTINGS_PAGE)
        address = await ctx.ask_until_accepted(
            lambda: io.ask_secret(_PROMPT), lambda raw: _check(ctx, raw)
        )
        saved = ctx.env.get(GOOGLE_CALENDAR_URL_SETTING)
        if address is None:
            io.say(_SKIPPED if saved is None else "Kept the address saved before.")
            return
        if saved == address:
            io.say("This address is already saved.")
            return
        ctx.env.set(GOOGLE_CALENDAR_URL_SETTING, address)
        io.say(f"Saved {GOOGLE_CALENDAR_URL_SETTING} in .env.")
        offer_to_send(ctx, [GOOGLE_CALENDAR_URL_SETTING], ask_first=False)


def say_calendar_tip(ctx: SetupContext) -> None:
    """Point a Gmail owner at their Google Calendar, in one line and without a question.

    Args:
        ctx: The set-up's context.
    """
    provider = (ctx.env.get(_IMAP_PROVIDER) or "").strip().lower()
    if provider != ImapProvider.GMAIL or ctx.env.get(GOOGLE_CALENDAR_URL_SETTING) is not None:
        return
    ctx.io.say(
        "Your mailbox is Gmail: add your Google Calendar too, in about a minute: "
        f"uv run tracker setup {StepName.GOOGLE_CALENDAR}"
    )


async def _check(ctx: SetupContext, raw: str) -> str | None:
    """Read the calendar once from the pasted address.

    Returns:
        The tidied address, or ``None`` when nothing was pasted (a skip).

    Raises:
        ValidationFailedError: If it is not a web address, or gives no calendar.
        SourceAuthError: If the calendar refused the address.
        SourceUnavailableError: If the calendar could not be reached.
        DownloadTooLargeError: If the calendar file is too large to read.
    """
    if not raw.strip():
        return None
    try:
        address = calendar_feed_address(raw)
    except ValueError as error:
        raise ValidationFailedError(str(error)) from None
    now = ctx.gateways.clock.now()
    found = await CalendarFeed(ctx.gateways.download).read(
        SecretStr(address),
        start=now - timedelta(days=CALENDAR_PAST_DAYS),
        end=now + timedelta(days=CALENDAR_FUTURE_DAYS),
        owner_addresses=(),
        zone=ctx.gateways.clock.zone,
    )
    count = len(found.events)
    ctx.io.say(
        f"Your calendar answered: {count} event{'' if count == 1 else 's'} in the last "
        f"{CALENDAR_PAST_DAYS} days and the next {CALENDAR_FUTURE_DAYS}."
    )
    return address
