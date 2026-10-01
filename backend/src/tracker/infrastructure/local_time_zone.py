"""The time zone this computer is set to, read without any extra package.

macOS and most Linux systems point ``/etc/localtime`` at a file inside a
``zoneinfo`` folder, whose path below that folder is the zone's name, such as
``Europe/Paris``. A ``TZ`` setting, when it names a zone, wins over that link.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

#: The link that names the computer's zone.
LOCALTIME_LINK: Final[Path] = Path("/etc/localtime")

#: The folder name the link points into.
ZONEINFO_FOLDER: Final[str] = "zoneinfo"

#: What is offered when the zone cannot be read.
FALLBACK_ZONE: Final[str] = "UTC"


def detect_time_zone(
    link: Path = LOCALTIME_LINK, environment: Mapping[str, str] | None = None
) -> str:
    """Name the computer's time zone, such as ``Europe/Paris``.

    Args:
        link: The ``/etc/localtime`` link; replaced in tests.
        environment: The process environment; replaced in tests.

    Returns:
        The zone's name, or ``UTC`` when it cannot be read.
    """
    environment = os.environ if environment is None else environment
    from_setting = environment.get("TZ", "").lstrip(":")
    for candidate in (from_setting, _zone_from_link(link)):
        if candidate and _is_known(candidate):
            return candidate
    return FALLBACK_ZONE


def _zone_from_link(link: Path) -> str:
    """Read the zone's name from where the link points, or ``""``."""
    try:
        target = link.resolve(strict=True)
    except OSError:
        return ""
    parts = target.parts
    if ZONEINFO_FOLDER not in parts:
        return ""
    index = len(parts) - 1 - parts[::-1].index(ZONEINFO_FOLDER)
    return "/".join(parts[index + 1 :])


def _is_known(name: str) -> bool:
    """Tell whether this machine knows a zone by that name."""
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True
