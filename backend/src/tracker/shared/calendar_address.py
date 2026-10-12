"""Checking a calendar's secret address, wherever it is typed or configured.

Both the configuration and the set-up read the address, so the one rule for
what a good one looks like lives here. No message ever repeats the address:
anyone who has it can read the calendar.
"""

from __future__ import annotations

from typing import Final
from urllib.parse import urlsplit, urlunsplit

#: The only scheme a calendar's secret address is fetched over.
_HTTPS: Final[str] = "https"

#: The scheme Apple and others give a calendar subscription; it means HTTPS.
_WEBCAL: Final[str] = "webcal"


def calendar_feed_address(raw: str) -> str:
    """Check and tidy a calendar's secret address, as pasted or configured.

    ``webcal://`` is how calendar apps spell a subscription; it is fetched
    over HTTPS like any other. Plain ``http://`` is refused, so the secret
    address never travels unencrypted.

    Args:
        raw: The address as typed.

    Returns:
        The address, starting with ``https://``.

    Raises:
        ValueError: If it is not a web address with a server name. The message
            never repeats the address, which is a secret.
    """
    cleaned = raw.strip()
    parts = urlsplit(cleaned)
    scheme = parts.scheme.lower()
    if scheme == _WEBCAL:
        parts = parts._replace(scheme=_HTTPS)
    elif scheme != _HTTPS:
        message = "the calendar address must start with https://"
        raise ValueError(message)
    if not parts.hostname or " " in cleaned:
        message = "the calendar address is not a complete web address"
        raise ValueError(message)
    return urlunsplit(parts)
