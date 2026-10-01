"""What a run amounts to, decided from the steps it recorded."""

from __future__ import annotations

from tracker.domain.enums import RunStatus


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
