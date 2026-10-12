"""Telling apart the Microsoft refusals a work or school sign-in can meet.

Microsoft refuses a sign-in with an ``AADSTS`` number, both in the answer's
``error_codes`` list and inside its ``error_description``. A few of those
numbers have a fix the owner cannot make by signing in again — the
organisation has to allow the application, or the account is a personal one
— so they become errors of their own, with words that say who can act.
"""

from __future__ import annotations

import re
from typing import Any, Final

from tracker.shared.errors import (
    AdminApprovalRequiredError,
    SourceAuthError,
    WorkAccountRequiredError,
)

#: The organisation decides: consent was never given or was taken back (65001),
#: an admin must approve (90094, 90095), the person is not assigned to the
#: application (50105), a conditional-access policy blocks it (53003), or the
#: organisation switched the application off (7000112).
ADMIN_REFUSALS: Final[frozenset[int]] = frozenset({65001, 90094, 90095, 50105, 53003, 7000112})

#: A personal Microsoft account tried a sign-in for work or school accounts.
PERSONAL_ACCOUNT_REFUSALS: Final[frozenset[int]] = frozenset({500200, 50020})

#: The sign-in application itself is not open to work or school accounts: it
#: is unknown in the organisation (700016) or registered for one directory only
#: (50194). Only another registration, named in ``MICROSOFT_CLIENT_ID``, helps.
APPLICATION_REFUSALS: Final[frozenset[int]] = frozenset({700016, 50194})

ADMIN_MESSAGE: Final[str] = (
    "your organisation does not let you allow Threadline to read Teams chats - "
    "your organisation's IT admin has to allow this"
)
PERSONAL_ACCOUNT_MESSAGE: Final[str] = (
    "Teams chats can be read only with a work or school account, not a personal "
    "Microsoft account - sign in with the account you use for Teams at work"
)
APPLICATION_MESSAGE: Final[str] = (
    "Microsoft does not open this sign-in application to work or school accounts - "
    "set MICROSOFT_CLIENT_ID to your own registration, as docs/setup-your-accounts.md explains"
)

_AADSTS: Final[re.Pattern[str]] = re.compile(r"AADSTS(\d+)")


def named_refusal(payload: dict[str, Any]) -> SourceAuthError | None:
    """Turn a refusal with a known ``AADSTS`` number into an error that says who can fix it.

    Args:
        payload: What the sign-in endpoint answered.

    Returns:
        The error, or ``None`` when the refusal is not one of those numbers.
    """
    codes = refusal_codes(payload)
    if codes & ADMIN_REFUSALS:
        return AdminApprovalRequiredError(ADMIN_MESSAGE)
    if codes & PERSONAL_ACCOUNT_REFUSALS:
        return WorkAccountRequiredError(PERSONAL_ACCOUNT_MESSAGE)
    if codes & APPLICATION_REFUSALS:
        return SourceAuthError(APPLICATION_MESSAGE)
    return None


def refusal_codes(payload: dict[str, Any]) -> frozenset[int]:
    """Read every ``AADSTS`` number a refusal carries.

    Args:
        payload: What the sign-in endpoint answered.

    Returns:
        The numbers, from ``error_codes`` and from the description's text.
    """
    listed = payload.get("error_codes")
    codes: set[int] = set()
    if isinstance(listed, list):
        codes.update(code for code in listed if isinstance(code, int))
    description = payload.get("error_description")
    if isinstance(description, str):
        codes.update(int(number) for number in _AADSTS.findall(description))
    return frozenset(codes)
