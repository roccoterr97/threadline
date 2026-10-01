"""Recording the assessment as its step of the run.

The assessment is two commands with the judging in between, and sometimes a
third: a verdict file that was rejected is answered again and imported on its
own. Each of them adds its share to the one ``assess`` step, so the step shows
everybody assessed in the run and not only what the last command saw.
"""

from __future__ import annotations

from uuid import UUID

from tracker.domain.enums import RunStep
from tracker.services.runs.run_recorder import RunRecorder, StepOutcome, StepResult


def record_assessment(
    recorder: RunRecorder, run_id: UUID, *, assessed: int, sent_to_review: int
) -> None:
    """Record the assessment as a finished step, adding to what the run already counted.

    Args:
        recorder: Writes the run's steps.
        run_id: The run the step belongs to.
        assessed: How many people this command assessed.
        sent_to_review: How many of them became a question for the owner.
    """
    earlier = recorder.find_step(run_id, RunStep.ASSESS)
    found_before = (earlier.items_found or 0) if earlier is not None else 0
    new_before = (earlier.items_new or 0) if earlier is not None else 0
    recorder.record_step(
        run_id,
        StepOutcome(
            step=RunStep.ASSESS,
            result=StepResult.SUCCESS,
            items_found=found_before + assessed,
            items_new=new_before + sent_to_review,
        ),
    )
