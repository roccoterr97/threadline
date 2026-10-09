"""The time zone this computer is set to, read without any extra package.

A ``TZ`` setting, when it names a zone, wins. Otherwise macOS and most Linux
systems point ``/etc/localtime`` at a file inside a ``zoneinfo`` folder, whose
path below that folder is the zone's name, such as ``Europe/Paris``. Windows has
no such link: ``tzutil /g`` prints its own name for the zone instead, such as
``Romance Standard Time``, which a table turns into the standard name. Each
source is simply tried in turn, so no check of which system this is is needed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Final

from tracker.shared.constants.windows_time_zones import (
    WINDOWS_NO_DST_SUFFIX,
    WINDOWS_TO_IANA,
    WINDOWS_ZONE_COMMAND,
    WINDOWS_ZONE_TIMEOUT_SECONDS,
)
from tracker.shared.logging import get_logger
from tracker.shared.time_zones import UTC_ZONE, canonical_zone_name

#: The link that names the computer's zone.
LOCALTIME_LINK: Final[Path] = Path("/etc/localtime")

#: The folder name the link points into.
ZONEINFO_FOLDER: Final[str] = "zoneinfo"

#: What is offered when the zone cannot be read.
FALLBACK_ZONE: Final[str] = UTC_ZONE

_log = get_logger(__name__)

#: Reads the Windows zone's name, or ``""`` when there is none to read.
WindowsZoneReader = Callable[[], str]


def read_windows_zone() -> str:
    """Ask Windows for its zone's name with ``tzutil /g``.

    Returns:
        The name as Windows prints it, such as ``W. Europe Standard Time``, or
        ``""`` on a computer without ``tzutil`` or when it did not answer.
    """
    program = shutil.which(WINDOWS_ZONE_COMMAND[0])
    if program is None:
        return ""
    try:
        done = subprocess.run(
            [program, *WINDOWS_ZONE_COMMAND[1:]],
            capture_output=True,
            text=True,
            check=False,
            timeout=WINDOWS_ZONE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        _log.warning("windows_zone_not_read", error_type=type(error).__name__)
        return ""
    return done.stdout if done.returncode == 0 else ""


def detect_time_zone(
    link: Path = LOCALTIME_LINK,
    environment: Mapping[str, str] | None = None,
    windows_zone: WindowsZoneReader = read_windows_zone,
) -> str:
    """Name the computer's time zone, such as ``Europe/Paris``.

    Args:
        link: The ``/etc/localtime`` link; replaced in tests.
        environment: The process environment; replaced in tests.
        windows_zone: Reads the Windows zone's name; replaced in tests.

    Returns:
        The zone's name, or ``UTC`` when it cannot be read.
    """
    environment = os.environ if environment is None else environment
    from_setting = environment.get("TZ", "").lstrip(":")
    for candidate in (from_setting, _zone_from_link(link)):
        known = canonical_zone_name(candidate)
        if known is not None:
            return known
    return zone_from_windows_name(windows_zone()) or FALLBACK_ZONE


def zone_from_windows_name(windows_name: str) -> str | None:
    """Turn a Windows zone name into the standard one.

    Args:
        windows_name: What ``tzutil /g`` printed, such as ``Romance Standard Time``.

    Returns:
        The standard name, such as ``Europe/Paris``, or ``None`` when the name
        is not in the table or this computer does not know the zone.
    """
    cleaned = windows_name.strip().removesuffix(WINDOWS_NO_DST_SUFFIX)
    standard = WINDOWS_TO_IANA.get(cleaned)
    return canonical_zone_name(standard) if standard else None


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
