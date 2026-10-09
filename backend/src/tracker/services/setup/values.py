"""Checks on what the person types, before anything is called or written.

Each function returns the cleaned value or raises
:class:`~tracker.shared.errors.ValidationFailedError` with a sentence that
says what a good value looks like. None of them ever repeats a secret.
"""

from __future__ import annotations

import re
from datetime import date, time
from typing import Final
from urllib.parse import urlsplit

from tracker.shared.constants.setup import LINKEDIN_PROFILE_PREFIX, SUPABASE_HOST_SUFFIX
from tracker.shared.errors import ValidationFailedError
from tracker.shared.time_zones import canonical_zone_name

_PROJECT_REF: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9]{8,40}$")
_EMAIL: Final[re.Pattern[str]] = re.compile(r"^[^@\s,]+@[^@\s,]+\.[^@\s,]+$")
_HTTPS: Final[str] = "https"
_HOST: Final[re.Pattern[str]] = re.compile(
    r"^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$"
)
_MAX_PORT: Final[int] = 65_535
_CLOCK_TIME: Final[re.Pattern[str]] = re.compile(r"^(\d{1,2})(?:[:.](\d{2}))?$")
_REPOSITORY_NAME: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
#: The longest project name Supabase's Management API accepts.
_MAX_PROJECT_NAME_LENGTH: Final[int] = 256
_MONTH_NAMES: Final[tuple[str, ...]] = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)
_SHORT_MONTH_LENGTH: Final[int] = 3
#: Month names and their three-letter forms, plus the common "Sept".
_MONTH_NUMBERS: Final[dict[str, int]] = {
    **{name: number for number, name in enumerate(_MONTH_NAMES, start=1)},
    **{name[:_SHORT_MONTH_LENGTH]: number for number, name in enumerate(_MONTH_NAMES, start=1)},
    "sept": 9,
}
#: A date with the month written as a word, day first or month first. A date
#: made of numbers and slashes is left out on purpose: 03/04/2027 is the third
#: of April to some readers and the fourth of March to others.
_NAMED_MONTH_DATES: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"^(?P<day>\d{1,2})\s+(?P<month>[A-Za-z]+)\.?,?\s+(?P<year>\d{4})$"),
    re.compile(r"^(?P<month>[A-Za-z]+)\.?\s+(?P<day>\d{1,2}),?\s+(?P<year>\d{4})$"),
)
_DATE_FORMS: Final[str] = (
    "write the date as YYYY-MM-DD or with the month's name, for example 2027-03-31 or 31 March 2027"
)


def supabase_url(raw: str) -> str:
    """Accept a project address, or a bare project identifier.

    Args:
        raw: What was typed.

    Returns:
        ``https://<project-ref>.supabase.co``.

    Raises:
        ValidationFailedError: If it is neither.
    """
    cleaned = raw.strip().rstrip("/")
    if _PROJECT_REF.match(cleaned):
        cleaned = f"https://{cleaned}{SUPABASE_HOST_SUFFIX}"
    project_ref(cleaned)
    return cleaned


def project_ref(url: str) -> str:
    """Read the project identifier out of a project address.

    Args:
        url: ``https://<project-ref>.supabase.co``.

    Returns:
        The identifier.

    Raises:
        ValidationFailedError: If the address is not a Supabase project address.
    """
    parts = urlsplit(url.strip())
    host = parts.hostname or ""
    ref = host.removesuffix(SUPABASE_HOST_SUFFIX)
    if parts.scheme != _HTTPS or ref == host or not _PROJECT_REF.match(ref):
        message = "the address should look like https://<project-id>.supabase.co"
        raise ValidationFailedError(message)
    return ref


def non_empty(raw: str, what: str) -> str:
    """Refuse an empty answer.

    Args:
        raw: What was typed.
        what: What was asked for, for the message.

    Returns:
        The value without surrounding spaces.

    Raises:
        ValidationFailedError: If nothing was typed.
    """
    cleaned = raw.strip()
    if not cleaned:
        message = f"{what} cannot be empty"
        raise ValidationFailedError(message)
    return cleaned


def server_name(raw: str) -> str:
    """Accept a server name such as ``imap.example.com``.

    Args:
        raw: What was typed.

    Returns:
        The name in lower case.

    Raises:
        ValidationFailedError: If it is not a plain server name.
    """
    cleaned = raw.strip().lower()
    if not _HOST.match(cleaned):
        message = "that is not a server name, such as imap.example.com"
        raise ValidationFailedError(message)
    return cleaned


def port_number(raw: str) -> int:
    """Accept a port number such as 993.

    Args:
        raw: What was typed.

    Returns:
        The number.

    Raises:
        ValidationFailedError: If it is not a port number.
    """
    cleaned = raw.strip()
    if not cleaned.isdigit() or not 0 < int(cleaned) <= _MAX_PORT:
        message = "that is not a port number, such as 993"
        raise ValidationFailedError(message)
    return int(cleaned)


def email_address(raw: str) -> str:
    """Accept one e-mail address.

    Args:
        raw: What was typed.

    Returns:
        The address in lower case.

    Raises:
        ValidationFailedError: If it does not look like an address.
    """
    cleaned = raw.strip().lower()
    if not _EMAIL.match(cleaned):
        message = "that does not look like an e-mail address, such as you@example.com"
        raise ValidationFailedError(message)
    return cleaned


def future_date(raw: str, today: date) -> date:
    """Accept a date that has not passed, written in an unambiguous way.

    ``2027-03-31``, ``31 Mar 2027``, ``31 March 2027`` and ``March 31, 2027``
    are all accepted. A date made only of numbers and slashes is refused,
    because its day and month cannot be told apart.

    Args:
        raw: What was typed.
        today: Today's date.

    Returns:
        The date.

    Raises:
        ValidationFailedError: If it is malformed, ambiguous or already past.
    """
    parsed = _written_date(raw.strip())
    if parsed < today:
        message = "that date has already passed - the key would not work"
        raise ValidationFailedError(message)
    return parsed


def _written_date(cleaned: str) -> date:
    """Read a date written YYYY-MM-DD or with the month's name."""
    try:
        return _named_month_date(cleaned) or date.fromisoformat(cleaned)
    except ValueError as error:
        raise ValidationFailedError(_DATE_FORMS) from error


def _named_month_date(cleaned: str) -> date | None:
    """Read a date such as ``31 Mar 2027`` or ``March 31, 2027``.

    Returns:
        The date, or ``None`` when no month is written as a word.

    Raises:
        ValueError: If the day does not exist in that month.
    """
    for form in _NAMED_MONTH_DATES:
        found = form.match(cleaned)
        month = _MONTH_NUMBERS.get(found.group("month").lower()) if found else None
        if found is not None and month is not None:
            return date(int(found.group("year")), month, int(found.group("day")))
    return None


def linkedin_profile(raw: str) -> str:
    """Accept a LinkedIn profile address.

    Args:
        raw: What was typed.

    Returns:
        The address, with a trailing slash.

    Raises:
        ValidationFailedError: If it is not a profile address.
    """
    cleaned = raw.strip()
    if not cleaned.startswith(LINKEDIN_PROFILE_PREFIX) or cleaned == LINKEDIN_PROFILE_PREFIX:
        message = f"the address should start with {LINKEDIN_PROFILE_PREFIX}"
        raise ValidationFailedError(message)
    return cleaned if cleaned.endswith("/") else f"{cleaned}/"


def web_address(raw: str) -> str:
    """Accept an https address with no path, such as a published dashboard.

    Args:
        raw: What was typed.

    Returns:
        The address without a trailing slash.

    Raises:
        ValidationFailedError: If it is not an https address.
    """
    cleaned = raw.strip().rstrip("/")
    parts = urlsplit(cleaned)
    if parts.scheme != _HTTPS or not parts.hostname:
        message = "the address should start with https://, for example https://you.netlify.app"
        raise ValidationFailedError(message)
    return cleaned


def merged_addresses(existing: str | None, address: str) -> str:
    """Add one address to a comma-separated list, once.

    Args:
        existing: The list so far, or ``None``.
        address: The address to add.

    Returns:
        The list with the address in it.
    """
    current = [part.strip().lower() for part in (existing or "").split(",") if part.strip()]
    if address.lower() not in current:
        current.append(address.lower())
    return ",".join(current)


def daily_time(raw: str) -> time:
    """Accept a time of day on the 24-hour clock, such as ``07:00`` or ``18:30``.

    Args:
        raw: What was typed; ``7`` means 07:00.

    Returns:
        The time.

    Raises:
        ValidationFailedError: If it is not a time of day.
    """
    found = _CLOCK_TIME.match(raw.strip())
    try:
        if found is None:
            raise ValueError(raw)
        return time(int(found.group(1)), int(found.group(2) or 0))
    except ValueError as error:
        message = "write the time on the 24-hour clock, such as 07:00 or 18:30"
        raise ValidationFailedError(message) from error


def time_zone(raw: str) -> str:
    """Accept a time-zone name this machine knows, such as ``Europe/Rome``, in any case.

    Args:
        raw: What was typed.

    Returns:
        The name as the time-zone database spells it, or ``UTC``.

    Raises:
        ValidationFailedError: If the zone is unknown.
    """
    canonical = canonical_zone_name(raw)
    if canonical is None:
        message = "that is not a time-zone name, such as Europe/Rome, America/New_York or UTC"
        raise ValidationFailedError(message)
    return canonical


def project_name(raw: str) -> str:
    """Accept a name for a Supabase project.

    Args:
        raw: What was typed.

    Returns:
        The name without surrounding spaces.

    Raises:
        ValidationFailedError: If it is empty or longer than Supabase allows.
    """
    cleaned = raw.strip()
    if not cleaned or len(cleaned) > _MAX_PROJECT_NAME_LENGTH:
        message = f"give the project a name of 1 to {_MAX_PROJECT_NAME_LENGTH} characters"
        raise ValidationFailedError(message)
    return cleaned


def list_number(raw: str, count: int) -> int:
    """Accept the number of an item in a list shown as ``1.``, ``2.`` and so on.

    Args:
        raw: What was typed.
        count: How many items the list has.

    Returns:
        The number, from 1 to ``count``.

    Raises:
        ValidationFailedError: If it is not one of the numbers shown.
    """
    cleaned = raw.strip().rstrip(".")
    if not cleaned.isdigit() or not 1 <= int(cleaned) <= count:
        message = f"type a number from 1 to {count}"
        raise ValidationFailedError(message)
    return int(cleaned)


def repository_name(raw: str) -> str:
    """Accept a name GitHub allows for a new repository, such as ``threadline``.

    Args:
        raw: What was typed.

    Returns:
        The name, without surrounding spaces.

    Raises:
        ValidationFailedError: If GitHub would refuse it.
    """
    cleaned = raw.strip()
    if not _REPOSITORY_NAME.match(cleaned) or cleaned in {".", ".."}:
        message = "use only letters, digits, '-', '_' or '.', such as threadline"
        raise ValidationFailedError(message)
    return cleaned
