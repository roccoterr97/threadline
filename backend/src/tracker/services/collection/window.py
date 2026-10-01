"""How far back a collection run looks.

The first run reads the last thirty days. Every later run reads from the last
successful run — for the mailboxes, the last run whose mailbox read succeeded —
minus an overlap (two days; more for LinkedIn), because a
message can reach a mailbox later than it was sent and a run that ended at 07:00
must not create a hole for anything that arrived at 06:59.

A refresh between two mornings reads less: only what is new since the last
time that one source was read successfully, minus a few hours.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from tracker.domain.enums import RunStep
from tracker.repositories import Repositories
from tracker.shared.clock import Clock
from tracker.shared.constants.collection import (
    INITIAL_WINDOW_DAYS,
    OVERLAP_DAYS,
    REFRESH_OVERLAP_HOURS,
)


def window_start(
    clock: Clock,
    *,
    last_run_at: datetime | None = None,
    since: datetime | None = None,
    overlap_days: int = OVERLAP_DAYS,
) -> datetime:
    """Work out the earliest moment a run collects from.

    Args:
        clock: Supplies the current instant.
        last_run_at: When the last successful run finished, if there was one.
        since: An explicit start the owner asked for, which beats everything.
        overlap_days: How far before the last run to start, for a source that
            delivers late.

    Returns:
        The start of the window, in UTC.
    """
    if since is not None:
        return since
    if last_run_at is None:
        return clock.now() - timedelta(days=INITIAL_WINDOW_DAYS)
    return last_run_at - timedelta(days=overlap_days)


def last_successful_run_at(repositories: Repositories) -> datetime | None:
    """Look up when the last clean run started.

    Args:
        repositories: The repository container.

    Returns:
        The start of the newest successful run, or ``None`` when none has
        succeeded yet — which makes the next run a first run.
    """
    run = repositories.run_logs.find_latest_successful()
    return run.started_at if run is not None else None


def last_collected_at(repositories: Repositories, step: RunStep) -> datetime | None:
    """Look up when the newest run that read one source successfully started.

    Unlike :func:`last_successful_run_at`, a run another source made partial
    still counts, so one failing source does not widen this one's window day
    after day.

    Args:
        repositories: The repository container.
        step: The source's collection step, such as ``collect_email``.

    Returns:
        That run's start, or ``None`` when the source was never read
        successfully — which makes the next read a first read.
    """
    collected = repositories.run_step_logs.find_latest_successful(step)
    if collected is None:
        return None
    run = repositories.run_logs.get(collected.run_id)
    return run.started_at if run is not None else None


def refresh_since(repositories: Repositories, step: RunStep) -> datetime | None:
    """Work out where a refresh starts reading one source.

    It is the start of the newest run in which that source's collection
    succeeded — even a run another source made partial — minus
    :data:`REFRESH_OVERLAP_HOURS`.

    Args:
        repositories: The repository container.
        step: The source's collection step, such as ``collect_email``.

    Returns:
        The start of the window, or ``None`` when the source was never read
        successfully, which leaves the usual window in charge.
    """
    collected_at = last_collected_at(repositories, step)
    if collected_at is None:
        return None
    return collected_at - timedelta(hours=REFRESH_OVERLAP_HOURS)
