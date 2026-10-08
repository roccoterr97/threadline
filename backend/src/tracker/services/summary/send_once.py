"""Making sure one run's summary reaches the owner once.

Two records say that a run's summary went out: the run's ``summary_email``
step, and a small file next to the summary file, written the moment the mail
server accepted the message. The file comes first because it is local: when the
database cannot be reached just after the mail went, the step cannot be
recorded, and the file alone still stops a second copy.

When neither record exists the summary is sent, even if an earlier attempt was
cut off at a moment when it may already have gone. That is the one doubt left,
and it is settled on purpose: a second copy of the owner's own summary is a
nuisance; a missing one is a morning without it, which the owner is told to
read as "the run did not start".
"""

from __future__ import annotations

from pathlib import Path
from typing import Final
from uuid import UUID

from tracker.domain.enums import RunStatus, RunStep
from tracker.domain.models import RunLog
from tracker.services.assessment.work_files import remove_work_file
from tracker.services.runs.run_recorder import RunRecorder
from tracker.services.summary.once_a_day import OnceADay, summary_went_out
from tracker.shared.errors import ValidationFailedError
from tracker.shared.logging import get_logger

#: Added to the summary file's name to name the file that says it was sent.
SENT_MARKER_SUFFIX: Final[str] = ".sent"

_log = get_logger(__name__)


def sent_marker(summary_file: Path) -> Path:
    """Name the file that records that a summary file was sent.

    Args:
        summary_file: The summary file ``tracker summary build`` wrote.

    Returns:
        The file beside it; it lives in the work directory and goes with it.
    """
    return summary_file.with_name(summary_file.name + SENT_MARKER_SUFFIX)


class SendOnce:
    """Knows whether a run's summary already went out, and remembers when it does."""

    def __init__(self, recorder: RunRecorder, summary_file: Path) -> None:
        """Bind the guard to the run log and to the summary file.

        Args:
            recorder: Reads the run's ``summary_email`` step.
            summary_file: The summary file; the sent marker sits beside it.
        """
        self._recorder = recorder
        self._summary_file = summary_file
        self._marker = sent_marker(summary_file)

    def already_sent(self, run_id: UUID) -> bool:
        """Whether this run's summary already went out.

        Args:
            run_id: The run.

        Returns:
            ``True`` when the marker names this run or the run recorded a
            ``summary_email`` step that went out. A summary skipped because
            today's had already gone (see :mod:`once_a_day`) did not go out.
        """
        if self._marked(run_id):
            return True
        step = self._recorder.find_step(run_id, RunStep.SUMMARY_EMAIL)
        return step is not None and summary_went_out(step)

    def remember(self, run_id: UUID) -> None:
        """Note on disk that this run's summary was accepted by the mail server.

        A marker that cannot be written is logged, not raised: the mail has
        gone, and the run's step is still about to record it.

        Args:
            run_id: The run whose summary went out.
        """
        try:
            self._marker.write_text(str(run_id), encoding="utf-8")
        except OSError as error:
            _log.warning("summary_sent_marker_not_written", error_type=type(error).__name__)

    def refuse_a_new_summary(self, run: RunLog | None) -> None:
        """Stop a second summary for a run still open whose summary already went out.

        The copy built earlier is removed too, so no route — the SMTP command
        or a session sending through the Gmail connector — has a file left to
        send again. A run already closed may still be reported on, by hand.

        Args:
            run: The run the summary would report on.

        Raises:
            ValidationFailedError: If that run is open and its summary went out.
        """
        if run is None or run.status is not RunStatus.RUNNING or not self.already_sent(run.id):
            return
        remove_work_file(self._summary_file)
        _log.info("summary_already_sent", run_id=str(run.id))
        message = "this run's summary was already sent, so no new one was built"
        raise ValidationFailedError(message)

    def skip_when_sent_today(
        self, run: RunLog | None, once_a_day: OnceADay, *, send_again: bool
    ) -> RunLog | None:
        """Build no summary for a run still open when another daily run sent today's.

        The skip is recorded as this run's ``summary_email`` step, and the
        copy built earlier is removed, so neither route has a file to send.
        A run already closed may still be reported on, by hand.

        Args:
            run: The run the summary would report on.
            once_a_day: Finds today's summary and records the skip.
            send_again: The owner asked for another copy on purpose.

        Returns:
            The run whose summary already went out today, when this one was
            skipped; ``None`` when the summary should be built.
        """
        if run is None or run.status is not RunStatus.RUNNING:
            return None
        earlier = once_a_day.skip_if_sent_today(run, self._recorder, send_again=send_again)
        if earlier is not None:
            remove_work_file(self._summary_file)
        return earlier

    def _marked(self, run_id: UUID) -> bool:
        """Whether the marker beside the summary file names this run."""
        if not self._marker.is_file():
            return False
        try:
            return self._marker.read_text(encoding="utf-8").strip() == str(run_id)
        except OSError as error:
            _log.warning("summary_sent_marker_not_read", error_type=type(error).__name__)
            return False
