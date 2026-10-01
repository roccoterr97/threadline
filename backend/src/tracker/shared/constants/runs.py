"""Limits for the run log: when a run that never finished counts as interrupted."""

from __future__ import annotations

from typing import Final

#: Hours after which a run still marked "running" is taken to have died part-way
#: (for example, GitHub stopped the job). A daily run takes ten minutes, so this
#: leaves a wide margin; the dashboard's "Refresh now" keeps its own, shorter,
#: 30-minute window for deciding whether a run is still going.
INTERRUPTED_RUN_AFTER_HOURS: Final[int] = 3

#: The code stored on the step an interrupted run never finished.
RUN_INTERRUPTED_CODE: Final[str] = "run_interrupted"

#: The technical note stored with it, for the run page.
RUN_INTERRUPTED_DETAIL: Final[str] = (
    "The run stopped part-way and never finished. It was closed when a later run started."
)
