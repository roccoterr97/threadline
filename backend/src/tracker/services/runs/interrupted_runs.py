"""Close runs that died part-way, so none stays "running" for ever.

A run whose job was stopped from outside (GitHub cancelled it, the laptop
slept) never reaches ``tracker run finish``. When the next run starts, every run
still marked running that started long enough ago is closed: the first step it
never recorded gets a failed row with the code ``run_interrupted``, which the
dashboard and the morning summary put into plain words, and the run is marked
failed. A run that recorded every step and only missed its closing is closed
with the status its steps add up to, because nothing is missing from it.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from tracker.domain.enums import RunStatus, RunStep, RunTrigger
from tracker.domain.models import RunLog, RunStepLog
from tracker.repositories import Repositories
from tracker.services.runs.run_status import derive_status_of_run
from tracker.shared.constants.runs import (
    INTERRUPTED_RUN_AFTER_HOURS,
    RUN_INTERRUPTED_CODE,
    RUN_INTERRUPTED_DETAIL,
)
from tracker.shared.logging import get_logger

_log = get_logger(__name__)


def close_interrupted_runs(
    repositories: Repositories, now: datetime, unconfigured: frozenset[RunStep]
) -> list[RunLog]:
    """Close every run still marked running that started too long ago.

    Args:
        repositories: The repository container.
        now: The current moment, which becomes the closed runs' finishing time.
        unconfigured: Steps whose source is not set up; never blamed.

    Returns:
        The runs that were closed.
    """
    cutoff = now - timedelta(hours=INTERRUPTED_RUN_AFTER_HOURS)
    stale = [run for run in repositories.run_logs.list_running() if run.started_at < cutoff]
    return [_close(repositories, run, now, unconfigured) for run in stale]


def expected_steps(trigger: RunTrigger) -> tuple[RunStep, ...]:
    """The steps a run records, in the order the recipe runs them.

    Args:
        trigger: What started the run; a refresh sends no summary.

    Returns:
        The steps, in order.
    """
    steps = tuple(RunStep)
    if trigger is RunTrigger.REFRESH:
        return tuple(step for step in steps if step is not RunStep.SUMMARY_EMAIL)
    return steps


def _close(
    repositories: Repositories, run: RunLog, now: datetime, unconfigured: frozenset[RunStep]
) -> RunLog:
    """Record where one run stopped, then close it."""
    recorded = repositories.run_step_logs.list_for_run(run.id)
    done = {step.step for step in recorded}
    stopped_at = next(
        (
            step
            for step in expected_steps(run.trigger)
            if step not in done and step not in unconfigured
        ),
        None,
    )
    status = derive_status_of_run(recorded, run.trigger)
    if stopped_at is not None:
        repositories.run_step_logs.bulk_upsert([_interrupted_step(run, stopped_at)])
        status = RunStatus.FAILED
    closed = run.model_copy(update={"finished_at": now, "status": status})
    repositories.run_logs.bulk_upsert([closed])
    _log.warning(
        "run_interrupted_closed",
        run_id=str(run.id),
        started_at=run.started_at.isoformat(),
        stopped_at=stopped_at.value if stopped_at else None,
        status=status.value,
    )
    return closed


def _interrupted_step(run: RunLog, step: RunStep) -> RunStepLog:
    """The failed row that says a run stopped before this step finished."""
    return RunStepLog(
        run_id=run.id,
        step=step,
        status=RunStatus.FAILED,
        error_code=RUN_INTERRUPTED_CODE,
        error_detail=RUN_INTERRUPTED_DETAIL,
    )
