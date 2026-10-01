"""Running one part of a command that does several things.

A few commands fold what used to be separate steps of the daily run into one:
``run start --prepare``, ``people tidy`` and ``run finish --clean``. Every part
is an existing command and still prints what it prints on its own. A part that
fails is reported on one line and the command carries on, the way the recipe
used to carry on from one failed command to the next.
"""

from __future__ import annotations

from collections.abc import Callable

import typer

from tracker.shared.errors import TrackerError
from tracker.shared.logging import get_logger

_log = get_logger(__name__)


def attempt(name: str, part: Callable[[], None]) -> bool:
    """Run one part, turning a known failure into one printed line.

    Args:
        name: The command the part stands for, as the printed line names it.
        part: The part to run. It prints its own result.

    Returns:
        Whether the part finished.
    """
    try:
        part()
    except TrackerError as error:
        _log.error("part_failed", part=name, code=error.code, detail=error.message)
        typer.echo(f"{name} failed · code={error.code}")
        return False
    return True
