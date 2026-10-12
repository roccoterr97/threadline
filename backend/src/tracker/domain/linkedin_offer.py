"""When the morning summary offers LinkedIn to an owner who has not added it.

A full set-up leaves LinkedIn for later, so the summary mentions it, but only
now and then: on the day of the owner's first daily run, then once a week, for
the first four weeks. After that it stays quiet for good, because an owner who
has not added it by then most likely cannot (LinkedIn offers it only to
profiles located in the EEA or Switzerland). Nothing is stored to remember
that the offer was made: the days are counted from the first run.
"""

from __future__ import annotations

from datetime import date

from tracker.shared.constants.summary import LINKEDIN_OFFER_EVERY_DAYS, LINKEDIN_OFFER_FOR_DAYS


def linkedin_offer_due(first_run_day: date, today: date) -> bool:
    """Whether today's summary carries the LinkedIn offer.

    Args:
        first_run_day: The owner's day of their first daily run.
        today: The owner's day of this summary.

    Returns:
        ``True`` on the first run's day and every seventh day after it, within
        the first four weeks.
    """
    days = (today - first_run_day).days
    if days < 0 or days >= LINKEDIN_OFFER_FOR_DAYS:
        return False
    return days % LINKEDIN_OFFER_EVERY_DAYS == 0
