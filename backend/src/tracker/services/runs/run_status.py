"""What a run amounts to, decided from the steps it recorded."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from tracker.domain.enums import RunStatus, RunStep, RunTrigger
from tracker.domain.models import RunStepLog

#: The steps that read a source; a run that recorded none of them collected nothing.
COLLECT_STEPS: Final[frozenset[RunStep]] = frozenset(
    {RunStep.COLLECT_LINKEDIN, RunStep.COLLECT_EMAIL, RunStep.COLLECT_CALENDAR}
)


def derive_run_status(step_statuses: list[RunStatus]) -> RunStatus:
    """Decide what a run amounts to, from the steps it recorded.

    Args:
        step_statuses: The status of every recorded step, in any order.

    Returns:
        ``success`` when every step finished, ``failed`` when none did — which
        includes a run that recorded no step at all, because a run that did
        nothing is not a good morning — and ``partial`` in between.
    """
    if not step_statuses:
        return RunStatus.FAILED
    succeeded = sum(1 for status in step_statuses if status is RunStatus.SUCCESS)
    if succeeded == len(step_statuses):
        return RunStatus.SUCCESS
    if succeeded == 0:
        return RunStatus.FAILED
    return RunStatus.PARTIAL


def derive_status_of_run(
    steps: Sequence[RunStepLog], trigger: RunTrigger, *, summary_pending: bool = False
) -> RunStatus:
    """Decide what a run amounts to, knowing which steps it should have recorded.

    The steps that were recorded all finishing is not enough for ``success``: a
    step that never got recorded (the summary that was not built, the sources
    that were never read) is no failure to count, yet the morning did not work.
    A run that lacks a collect step, or a daily run that lacks its
    ``summary_email`` step, is therefore at most ``partial``.

    Args:
        steps: The steps the run recorded.
        trigger: What started the run; a refresh sends no summary.
        summary_pending: Whether the summary is only now being built, so that
            its step cannot exist yet (the status the summary itself reports).

    Returns:
        The run's status.
    """
    status = derive_run_status([step.status for step in steps])
    if status is not RunStatus.SUCCESS:
        return status
    recorded = {step.step for step in steps}
    collected = not COLLECT_STEPS.isdisjoint(recorded)
    summarised = (
        summary_pending or trigger is RunTrigger.REFRESH or RunStep.SUMMARY_EMAIL in recorded
    )
    return RunStatus.SUCCESS if collected and summarised else RunStatus.PARTIAL
