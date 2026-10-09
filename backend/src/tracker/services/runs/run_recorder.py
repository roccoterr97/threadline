"""Start a run, record each step, then close the run with an honest status.

The steps of a daily run are independent: LinkedIn failing does not stop the
mailbox, and neither stops the assessment. What the run *is* — a clean morning,
a half-done one or a lost one — is therefore decided at the end, from the steps
that were actually recorded, by :func:`derive_status_of_run`.

Recording the same step twice updates the row it already wrote, so a recipe
that is re-run after a hiccup leaves one row per step rather than two.

A step for a source the owner never set up is not recorded at all: it did not
fail, it did not run, and it must not turn a clean morning into a "partial" one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from uuid import UUID

from tracker.domain.enums import RunStatus, RunStep, RunTrigger
from tracker.domain.models import RunLog, RunStepLog
from tracker.repositories import Repositories
from tracker.services.runs.interrupted_runs import close_interrupted_runs
from tracker.services.runs.run_status import derive_status_of_run
from tracker.shared.clock import Clock
from tracker.shared.config import Settings
from tracker.shared.constants.runs import INTERRUPTED_RUN_AFTER_HOURS
from tracker.shared.constants.summary import MAX_ERROR_DETAIL_LENGTH
from tracker.shared.errors import ValidationFailedError
from tracker.shared.logging import get_logger

#: Error code stored when a step is reported as failed without naming a reason.
DEFAULT_ERROR_CODE = "tracker_error"

_log = get_logger(__name__)


class StepResult(StrEnum):
    """How one step of a run ended.

    A step is over by the time it is recorded, so it is either done or not. The
    richer :class:`~tracker.domain.enums.RunStatus` describes the whole run.
    """

    SUCCESS = "success"
    FAILED = "failed"

    def as_status(self) -> RunStatus:
        """Return the stored status for this result."""
        return RunStatus.SUCCESS if self is StepResult.SUCCESS else RunStatus.FAILED


@dataclass(frozen=True, slots=True)
class StepOutcome:
    """What one step of a run produced.

    Attributes:
        step: Which step this was.
        result: Whether it finished.
        items_found: How many items the step looked at, when it counts any.
        items_new: How many of them were new.
        error_code: Stable code behind a failure, shown to nobody as-is: the
            dashboard and the summary translate it into a sentence.
        error_detail: A short technical note for the run page. Never message
            text, never a secret, never a stack trace.
    """

    step: RunStep
    result: StepResult
    items_found: int | None = None
    items_new: int | None = None
    error_code: str | None = None
    error_detail: str | None = None


def triggers_of_kind(*, refresh: bool) -> frozenset[RunTrigger]:
    """List the triggers of one kind of run: refreshes, or everything else.

    A refresh and a daily run each have their own concurrency group, so one of
    each can be open at the same time; a command acts on the run of its own
    kind, so a refresh can never record into, or close, the morning's run.

    Args:
        refresh: Whether the refresh kind is wanted.

    Returns:
        The triggers that start a run of that kind.
    """
    if refresh:
        return frozenset({RunTrigger.REFRESH})
    return frozenset(trigger for trigger in RunTrigger if trigger is not RunTrigger.REFRESH)


def unconfigured_steps(settings: Settings) -> frozenset[RunStep]:
    """List the steps whose source the owner has not set up.

    Args:
        settings: The process configuration.

    Returns:
        The steps to leave out of the run: ``collect_linkedin`` when LinkedIn
        has no profile address or no key, and ``collect_calendar`` when
        Outlook is not one of the mailboxes (the calendar is Outlook's).
        ``collect_email`` is always set up: at least one mailbox is required.
    """
    unconfigured: set[RunStep] = set()
    if not settings.linkedin_enabled:
        unconfigured.add(RunStep.COLLECT_LINKEDIN)
    if not settings.outlook_enabled:
        unconfigured.add(RunStep.COLLECT_CALENDAR)
    return frozenset(unconfigured)


class RunRecorder:
    """Writes the run log and its steps."""

    def __init__(
        self,
        repositories: Repositories,
        clock: Clock,
        unconfigured: frozenset[RunStep] = frozenset(),
    ) -> None:
        """Bind the recorder to the database and to a clock.

        Args:
            repositories: The repository container.
            clock: Source of the current moment.
            unconfigured: Steps whose source the owner never set up. They are
                never recorded (see :func:`unconfigured_steps`).
        """
        self._repositories = repositories
        self._clock = clock
        self._unconfigured = unconfigured

    def start(self, trigger: RunTrigger) -> RunLog:
        """Open a run.

        Args:
            trigger: What started it.

        Earlier runs still marked running that started long ago are closed
        first, as interrupted (see :mod:`interrupted_runs`).

        Returns:
            The new run, already stored and still ``running``.
        """
        now = self._clock.now()
        close_interrupted_runs(self._repositories, now, self._unconfigured)
        run = RunLog(started_at=now, status=RunStatus.RUNNING, trigger=trigger)
        self._repositories.run_logs.bulk_upsert([run])
        _log.info("run_started", run_id=str(run.id), trigger=trigger.value)
        return run

    def record_step(self, run_id: UUID, outcome: StepOutcome) -> RunStepLog | None:
        """Store the result of one step, replacing an earlier attempt at it.

        Args:
            run_id: The run the step belongs to.
            outcome: What the step produced.

        Returns:
            The stored step row, or ``None`` when the step's source is not set
            up and nothing was stored.
        """
        # A step that will not be stored is not looked up either.
        configured = outcome.step not in self._unconfigured
        existing = self.find_step(run_id, outcome.step) if configured else None
        return self.replace_step(run_id, outcome, existing)

    def replace_step(
        self, run_id: UUID, outcome: StepOutcome, existing: RunStepLog | None
    ) -> RunStepLog | None:
        """Store the result of one step whose earlier row the caller already looked up.

        A caller that read the earlier row to add to its counts hands it over,
        so the run's steps are not listed a second time to find it again.

        Args:
            run_id: The run the step belongs to.
            outcome: What the step produced.
            existing: The row :meth:`find_step` returned for this step of this
                run, or ``None`` when it found none.

        Returns:
            The stored step row, or ``None`` when the step's source is not set
            up and nothing was stored.
        """
        if outcome.step in self._unconfigured:
            _log.info("run_step_not_configured", run_id=str(run_id), step=outcome.step.value)
            return None
        step = RunStepLog(
            run_id=run_id,
            step=outcome.step,
            status=outcome.result.as_status(),
            items_found=outcome.items_found,
            items_new=outcome.items_new,
            error_code=self._error_code(outcome),
            error_detail=_shorten(outcome.error_detail),
        )
        if existing is not None:
            step = step.model_copy(update={"id": existing.id})
        self._repositories.run_step_logs.bulk_upsert([step])
        _log.info(
            "run_step_recorded",
            run_id=str(run_id),
            step=outcome.step.value,
            status=step.status.value,
            error_code=step.error_code,
        )
        return step

    def finish(self, run_id: UUID) -> RunLog:
        """Close a run with the status its steps add up to.

        Args:
            run_id: The run to close.

        Returns:
            The stored run, with its final status and finishing time.

        Raises:
            ValidationFailedError: If no run has that identifier.
        """
        run = self._repositories.run_logs.get(run_id)
        if run is None:
            message = f"no run with identifier {run_id}"
            raise ValidationFailedError(message)
        steps = self._repositories.run_step_logs.list_for_run(run_id)
        finished = run.model_copy(
            update={
                "finished_at": self._clock.now(),
                "status": derive_status_of_run(steps, run.trigger),
            }
        )
        self._repositories.run_logs.bulk_upsert([finished])
        _log.info(
            "run_finished",
            run_id=str(run_id),
            status=finished.status.value,
            steps=len(steps),
        )
        return finished

    def resolve(self, run_id: UUID | None, *, refresh: bool = False) -> RunLog:
        """Find the run a command should act on.

        Without a named run, only the newest run of the caller's kind counts,
        and only while it is still open: when today's ``run start`` failed,
        the newest run is yesterday's, closed, and today's steps must not
        overwrite it; and a refresh going at the same time as the daily run
        has a run of its own, which neither may take for the other's.

        Args:
            run_id: The run the owner named, or ``None`` for the open one.
            refresh: Whether the open run wanted is a refresh rather than a
                daily run. Ignored for a named run.

        Returns:
            The run.

        Raises:
            ValidationFailedError: If that run does not exist, if no run of
                that kind has ever run, or if none is open.
        """
        if run_id is not None:
            return self._named(run_id)
        kind = "refresh" if refresh else "daily run"
        run = self._repositories.run_logs.find_latest(triggers_of_kind(refresh=refresh))
        how_to_start = _how_to_start(refresh=refresh)
        if run is None:
            message = f"there is no {kind} to work with — {how_to_start}"
            raise ValidationFailedError(message)
        if run.status is not RunStatus.RUNNING or self._is_stale(run):
            message = (
                f"no run is open: the latest {kind} has already finished or was abandoned. "
                f"{how_to_start[:1].upper()}{how_to_start[1:]}, or name a run with --run"
            )
            raise ValidationFailedError(message)
        return run

    def _named(self, run_id: UUID) -> RunLog:
        """Fetch the run the owner named, whatever its status."""
        run = self._repositories.run_logs.get(run_id)
        if run is None:
            message = f"no run with identifier {run_id}"
            raise ValidationFailedError(message)
        return run

    def _is_stale(self, run: RunLog) -> bool:
        """Whether an open run started so long ago that it died part-way."""
        age = self._clock.now() - run.started_at
        return age >= timedelta(hours=INTERRUPTED_RUN_AFTER_HOURS)

    def find_step(self, run_id: UUID, step: RunStep) -> RunStepLog | None:
        """Return the row already written for this step of this run, if any.

        Args:
            run_id: The run to look in.
            step: The step to look for.

        Returns:
            The stored step row, or ``None`` when the run has not recorded it.
        """
        recorded = self._repositories.run_step_logs.list_for_run(run_id)
        return next((row for row in recorded if row.step is step), None)

    @staticmethod
    def _error_code(outcome: StepOutcome) -> str | None:
        """Return the code to store, giving a failure without one a stable code."""
        if outcome.result is StepResult.SUCCESS:
            return None
        code = (outcome.error_code or "").strip()
        return code or DEFAULT_ERROR_CODE


def _how_to_start(*, refresh: bool) -> str:
    """Tell the owner how to get a run of the kind a command was looking for.

    ``tracker run start`` on its own opens a daily run, so a command looking
    for a refresh names the refresh trigger, and the way back to the daily or
    manual run that may well be open.
    """
    if refresh:
        return (
            "start one with 'tracker run start --trigger refresh', "
            "or leave out --refresh to use the daily or manual run that is open"
        )
    return "start one with 'tracker run start'"


def _shorten(detail: str | None) -> str | None:
    """Trim a technical note to the stored length, dropping an empty one."""
    if detail is None:
        return None
    cleaned = " ".join(detail.split())
    if not cleaned:
        return None
    return cleaned[:MAX_ERROR_DETAIL_LENGTH]
