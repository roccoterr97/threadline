"""One morning summary a day, however many daily runs the day has.

:mod:`send_once` stops one run from sending its summary twice. A day can still
hold two daily runs — GitHub's "Re-run job", a second "Run workflow", a run
started by hand — and each would send a summary of its own. So before a daily
summary goes out, the other daily runs of the owner's day are looked at: when
one of them already sent its summary, this one is skipped, and its
``summary_email`` step is recorded as finished with nothing sent. The owner
can still ask for another copy on purpose.

A skipped send is recorded as a finished step, so the run stays clean, with
``items_new`` at zero: one summary was due, none went out. That zero is what
:func:`summary_went_out` reads, so a skipped run never counts as one whose
summary reached the owner — neither here nor for "replied since yesterday".

A refresh sends no summary, so none of this applies to it.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Final

from tracker.domain.enums import RunStatus, RunStep, RunTrigger
from tracker.domain.models import RunLog, RunStepLog
from tracker.repositories import Repositories
from tracker.services.runs.run_recorder import (
    RunRecorder,
    StepOutcome,
    StepResult,
    triggers_of_kind,
)
from tracker.shared.clock import Clock
from tracker.shared.logging import get_logger

#: ``items_new`` of a ``summary_email`` step that went out: one summary sent.
_SENT: Final[int] = 1

#: ``items_new`` of a ``summary_email`` step that was skipped: nothing sent.
_NOT_SENT: Final[int] = 0

_log = get_logger(__name__)


def summary_went_out(step: RunStepLog) -> bool:
    """Whether a step records a summary that actually reached the owner.

    A step recorded without counts (``items_new`` left out) went out: only a
    skipped send records the zero.

    Args:
        step: Any step of any run.

    Returns:
        ``True`` for a successful ``summary_email`` step that was not skipped.
    """
    return (
        step.step is RunStep.SUMMARY_EMAIL
        and step.status is RunStatus.SUCCESS
        and step.items_new != _NOT_SENT
    )


def skipped_line(earlier: RunLog) -> str:
    """The one line a command prints when it skips the summary.

    Args:
        earlier: The run whose summary already went out today.

    Returns:
        The line, naming that run.
    """
    return f"summary skipped · today's summary already went out with run {earlier.id}"


class OnceADay:
    """Finds a summary already sent on the owner's day, and records a skipped one."""

    def __init__(self, repositories: Repositories, clock: Clock) -> None:
        """Bind the check to the database and to the owner's time zone.

        Args:
            repositories: The repository container.
            clock: Its zone decides where the owner's day begins and ends.
        """
        self._repositories = repositories
        self._clock = clock

    def sent_earlier_today(self, run: RunLog) -> RunLog | None:
        """Find another daily run of the same owner-local day whose summary went out.

        Args:
            run: The run about to send its summary.

        Returns:
            The most recent such run, or ``None`` when this run's summary is
            the day's first — and always ``None`` for a refresh.
        """
        if run.trigger is RunTrigger.REFRESH:
            return None
        day_start, day_end = self._owner_day(run.started_at)
        same_day = [
            other
            for other in self._repositories.run_logs.list_started_since(
                triggers_of_kind(refresh=False), day_start
            )
            if other.id != run.id and other.started_at < day_end
        ]
        if not same_day:
            return None
        steps = self._repositories.run_step_logs.list_for_runs([other.id for other in same_day])
        sent = {step.run_id for step in steps if summary_went_out(step)}
        return max(
            (other for other in same_day if other.id in sent),
            key=lambda other: other.started_at,
            default=None,
        )

    def skip_if_sent_today(
        self, run: RunLog, recorder: RunRecorder, *, send_again: bool
    ) -> RunLog | None:
        """Record this run's summary as skipped when today's already went out.

        Args:
            run: The run about to send its summary.
            recorder: Records the skipped ``summary_email`` step.
            send_again: The owner asked for another copy on purpose; nothing
                is looked up and nothing is skipped.

        Returns:
            The run whose summary already went out today, when this one was
            skipped; ``None`` when this summary should go out.
        """
        if send_again:
            return None
        earlier = self.sent_earlier_today(run)
        if earlier is None:
            return None
        recorder.record_step(run.id, _skipped_outcome(earlier))
        _log.info(
            "summary_skipped_already_sent_today",
            run_id=str(run.id),
            earlier_run_id=str(earlier.id),
        )
        return earlier

    def _owner_day(self, moment: datetime) -> tuple[datetime, datetime]:
        """Return where the owner's day holding ``moment`` starts and ends, in UTC."""
        zone = self._clock.zone
        day = moment.astimezone(zone).date()
        start = datetime.combine(day, time.min, tzinfo=zone)
        end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
        return start.astimezone(UTC), end.astimezone(UTC)


def sent_outcome() -> StepOutcome:
    """The ``summary_email`` step of a summary that went out.

    Returns:
        A finished step counting one summary, sent.
    """
    return StepOutcome(
        RunStep.SUMMARY_EMAIL, StepResult.SUCCESS, items_found=_SENT, items_new=_SENT
    )


def _skipped_outcome(earlier: RunLog) -> StepOutcome:
    """The ``summary_email`` step of a summary skipped because one already went today.

    One summary was due and none was sent; the note names the run that sent
    it, for the run page.
    """
    return StepOutcome(
        RunStep.SUMMARY_EMAIL,
        StepResult.SUCCESS,
        items_found=_SENT,
        items_new=_NOT_SENT,
        error_detail=f"not sent: run {earlier.id} already sent today's summary",
    )
