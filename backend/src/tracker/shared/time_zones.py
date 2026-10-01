"""Time-zone names, spelled the one way every machine accepts.

macOS finds ``europe/paris`` because its disk ignores case; Linux, where the
daily run goes on GitHub, does not. So a typed name is matched without regard
to case against the zones this machine lists, and the list's own spelling is
what gets stored and used.
"""

from __future__ import annotations

from typing import Final
from zoneinfo import available_timezones

#: The zone that needs no time-zone database, and the default.
UTC_ZONE: Final[str] = "UTC"


def canonical_zone_name(raw: str) -> str | None:
    """Return a zone's name as the time-zone database spells it.

    Args:
        raw: A name as typed, such as ``europe/rome`` or `` UTC ``.

    Returns:
        The canonical name, such as ``Europe/Rome``, or ``None`` when this
        machine knows no zone by that name in any case.
    """
    cleaned = raw.strip()
    if not cleaned:
        return None
    if cleaned.upper() == UTC_ZONE:
        return UTC_ZONE
    known = available_timezones()
    if cleaned in known:
        return cleaned
    wanted = cleaned.casefold()
    return next((name for name in known if name.casefold() == wanted), None)
