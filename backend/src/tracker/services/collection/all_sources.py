"""Reading every source at the same time, and storing them one after another.

The waiting in a collection is all on the outside: LinkedIn, the mailboxes and
the calendar each take their time to answer, and none of them needs another's
answer. So they are all asked together. Storing is different. Each source adds
people to a list it has just read, and the calendar looks up who the mail
collector filed an invitation under — so what was read is stored in a fixed
order, one source at a time.

A source that fails never stops the others: its failure is kept next to the
others' results, and the run records it as that step's outcome.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from uuid import UUID

from tracker.domain.enums import Channel, RunStep
from tracker.services.collection.models import CollectionReport, SaveStep
from tracker.services.runs.run_recorder import RunRecorder, StepOutcome, StepResult
from tracker.shared.concurrency import gather_all
from tracker.shared.errors import TrackerError
from tracker.shared.logging import get_logger

_log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Source:
    """One source the daily run collects from.

    Attributes:
        channel: Which source it is, for the printed result.
        step: The run step its result is recorded under.
        read: Makes every request to the source and hands back the step that
            stores what was read (a collector's ``read``).
    """

    channel: Channel
    step: RunStep
    read: Callable[[], Awaitable[SaveStep]]


@dataclass(frozen=True, slots=True)
class SourceOutcome:
    """What collecting one source came to.

    Attributes:
        source: The source.
        report: The counts, when it was read and stored (or is not set up).
        failure: Why it could not be read or stored, otherwise ``None``.
    """

    source: Source
    report: CollectionReport | None = None
    failure: TrackerError | None = None

    @property
    def succeeded(self) -> bool:
        """Whether the source is set up and was read and stored."""
        return self.report is not None and not self.report.not_configured


@dataclass(frozen=True, slots=True)
class _Read:
    """One source after the reading half: the step that stores it, or its failure."""

    source: Source
    save: SaveStep | None = None
    failure: TrackerError | None = None


class AllSourcesCollector:
    """Collects every source: read together, stored in order."""

    def __init__(self, lanes: Sequence[Sequence[Source]]) -> None:
        """Bind the collector to its sources.

        Args:
            lanes: The sources, grouped. Lanes are read at the same time. The
                sources inside one lane are read one after another: put two
                sources in the same lane when they renew the same sign-in key,
                so that two renewals are never under way at once. Sources are
                stored in the order they appear here, lane after lane.
        """
        self._lanes = tuple(tuple(lane) for lane in lanes)

    def collect(self) -> tuple[SourceOutcome, ...]:
        """Read every source, then store each one.

        Returns:
            One outcome per source, in the order the sources were given.
        """
        reads = asyncio.run(self._read_everything())
        return tuple(_store(read) for read in reads)

    async def _read_everything(self) -> list[_Read]:
        """Read the lanes side by side."""
        per_lane = await gather_all(self._read_lane(lane) for lane in self._lanes)
        return [read for lane in per_lane for read in lane]

    @staticmethod
    async def _read_lane(lane: Sequence[Source]) -> list[_Read]:
        """Read the sources of one lane, one after another."""
        return [await _read(source) for source in lane]


def record_outcomes(recorder: RunRecorder, run_id: UUID, outcomes: Sequence[SourceOutcome]) -> None:
    """Record each source's outcome as its step of the run.

    A source that is not set up is left out: it is not a step of this run.

    Args:
        recorder: Writes the run's steps.
        run_id: The run the steps belong to.
        outcomes: What :meth:`AllSourcesCollector.collect` returned.
    """
    for outcome in outcomes:
        step = _step_outcome(outcome)
        if step is not None:
            recorder.record_step(run_id, step)


async def _read(source: Source) -> _Read:
    """Run one source's reading half, keeping a failure instead of raising it."""
    try:
        return _Read(source, save=await source.read())
    except TrackerError as error:
        _log.error("source_not_read", step=source.step.value, code=error.code, detail=error.message)
        return _Read(source, failure=error)


def _store(read: _Read) -> SourceOutcome:
    """Run one source's storing half, keeping a failure instead of raising it."""
    if read.save is None:
        return SourceOutcome(read.source, failure=read.failure)
    try:
        return SourceOutcome(read.source, report=read.save())
    except TrackerError as error:
        _log.error(
            "source_not_stored", step=read.source.step.value, code=error.code, detail=error.message
        )
        return SourceOutcome(read.source, failure=error)


def _step_outcome(outcome: SourceOutcome) -> StepOutcome | None:
    """Turn one source's outcome into the step to record, if there is one."""
    if outcome.failure is not None:
        return StepOutcome(
            step=outcome.source.step, result=StepResult.FAILED, error_code=outcome.failure.code
        )
    report = outcome.report
    if report is None or report.not_configured:
        return None
    return StepOutcome(
        step=outcome.source.step,
        result=StepResult.SUCCESS,
        items_found=report.conversations_found,
        items_new=report.conversations_new,
    )
