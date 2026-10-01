"""Words both versions of the morning summary share.

The plain-text and the HTML body must say exactly the same thing, so the
headings, the way a date is written and the way a count is written live here
once and are used by both renderers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Final

ATTENTION_HEADING: Final[str] = "Something needs your attention"
DO_TODAY_HEADING: Final[str] = "Do today"
OVERDUE_HEADING: Final[str] = "Overdue: replies you owe"
CHASE_HEADING: Final[str] = "Time to chase"
REPLIED_HEADING: Final[str] = "Replied since yesterday"
REVIEW_HEADING: Final[str] = "To review"
KEY_HEADING: Final[str] = "LinkedIn key"
NOBODY: Final[str] = "nobody"
NO_QUESTIONS: Final[str] = "no questions waiting"


@dataclass(frozen=True, slots=True)
class Branding:
    """How the summary names Threadline and marks its own subject line.

    Both come from the owner's configuration, never from a session at run time.

    Attributes:
        product_name: What Threadline calls itself in the e-mail.
        subject_prefix: How every subject starts. The mailbox collector ignores
            mail whose subject starts with it, so the summary is never read back.
    """

    product_name: str
    subject_prefix: str


_MONTHS: Final[tuple[str, ...]] = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)

_WEEKDAYS: Final[tuple[str, ...]] = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def format_day(value: date) -> str:
    """Render a date the way a person writes it: ``8 Oct 2026``.

    Args:
        value: The date to render.

    Returns:
        The date as day, short month and year.
    """
    return f"{value.day} {_MONTHS[value.month - 1]} {value.year}"


def format_weekday(value: date) -> str:
    """Render a date with its weekday: ``Mon 21 Sep 2026``.

    Args:
        value: The date to render.

    Returns:
        The short weekday followed by the date.
    """
    return f"{_WEEKDAYS[value.weekday()]} {format_day(value)}"


def count(number: int, noun: str) -> str:
    """Render a count with its noun in the right number.

    Args:
        number: How many.
        noun: The singular noun.

    Returns:
        ``1 question`` or ``3 questions``.
    """
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def more_on_dashboard(hidden: int) -> str:
    """Say how many people did not fit in a section.

    Args:
        hidden: How many were left out.

    Returns:
        The sentence pointing at the dashboard.
    """
    return f"and {hidden} more on the dashboard"


def questions_waiting(open_questions: int) -> str:
    """Say how many yes-or-no questions are waiting.

    Args:
        open_questions: How many are unanswered.

    Returns:
        The sentence for the review section.
    """
    return f"{count(open_questions, 'question')} waiting for a yes or no"
