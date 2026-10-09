"""Keep two runs of the same kind from working at the same time.

Two daily runs, or two refreshes, going together would collect and assess the
same messages twice and record into each other's steps. GitHub already queues
its own runs one behind the other (the workflow's concurrency groups), but a
run started anywhere else — the Mac, Claude's cloud, by hand — is not in that
queue. So a new run first looks for an open run of its own kind.

GitHub never lets two of its runs of one kind overlap, so when GitHub starts a
run, an open run that GitHub itself started cannot still be going: it died
before it could close, and is closed as interrupted straight away instead of
three hours later. Any other open run is taken to be going, and the new run is
refused unless the owner says to start anyway.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from tracker.domain.enums import RunTrigger
from tracker.domain.models import RunLog

#: The triggers of runs that GitHub Actions starts and queues itself.
GITHUB_TRIGGERS: Final[frozenset[RunTrigger]] = frozenset({RunTrigger.GITHUB, RunTrigger.REFRESH})

#: Where each kind of trigger runs, in the owner's words.
_WHERE: Final[dict[RunTrigger, str]] = {
    RunTrigger.GITHUB: "on GitHub",
    RunTrigger.REFRESH: "on GitHub, from Refresh now",
    RunTrigger.CLOUD: "in Claude's cloud",
    RunTrigger.MAC: "on the Mac",
    RunTrigger.MANUAL: "by hand",
}


@dataclass(frozen=True)
class OpenRuns:
    """The open runs of the new run's kind, sorted by what they mean for it.

    Attributes:
        left_behind: Runs that cannot still be going; closed as interrupted.
        going: Runs that may still be going; the new run waits for them.
    """

    left_behind: tuple[RunLog, ...]
    going: tuple[RunLog, ...]


def sort_open_runs(open_runs: Sequence[RunLog], trigger: RunTrigger) -> OpenRuns:
    """Tell the open runs of the new run's kind that died from those still going.

    Args:
        open_runs: Runs of the same kind still marked running and not yet
            three hours old.
        trigger: What is starting the new run.

    Returns:
        The runs, sorted.
    """
    if trigger not in GITHUB_TRIGGERS:
        return OpenRuns(left_behind=(), going=tuple(open_runs))
    left_behind = tuple(run for run in open_runs if run.trigger is trigger)
    going = tuple(run for run in open_runs if run.trigger is not trigger)
    return OpenRuns(left_behind=left_behind, going=going)


def already_going_message(run: RunLog, *, refresh: bool) -> str:
    """Say which run is in the way, and what the owner can do.

    Args:
        run: The open run the new one would overlap.
        refresh: Whether the runs are refreshes.

    Returns:
        One plain sentence for the command's error line.
    """
    kind = "refresh" if refresh else "daily run"
    started = run.started_at.strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"another {kind} is already going: it started {_WHERE[run.trigger]} at {started}. "
        "Wait for it to finish. If it stopped without finishing, start this one again "
        "with --force, which closes the old one as interrupted"
    )
