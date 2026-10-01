"""Runs every check side by side, whatever the others found."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

import httpx

from tracker.services.doctor.models import Check, CheckResult, CheckStatus, problem
from tracker.shared.concurrency import gather_all
from tracker.shared.errors import DatabaseUnavailableError, SourceUnavailableError, TrackerError
from tracker.shared.logging import get_logger

#: Advice for a failure that looks like an outage rather than a wrong setting.
OUTAGE_FIX: Final[str] = (
    "If this is a network problem or an outage, try again in a few minutes; "
    "in the cloud, check the environment's allowed domains"
)

_OUTAGE_ERRORS: Final[tuple[type[TrackerError], ...]] = (
    DatabaseUnavailableError,
    SourceUnavailableError,
)

_log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DoctorReport:
    """Every check's result, in the order the checks were given."""

    results: tuple[CheckResult, ...]

    @property
    def healthy(self) -> bool:
        """Whether no check found a problem. Warnings do not count."""
        return all(result.status is not CheckStatus.PROBLEM for result in self.results)


class DoctorService:
    """Runs independent checks and collects one result from each."""

    def __init__(self, checks: Sequence[Check]) -> None:
        """Bind the service to its checks.

        Args:
            checks: The checks, in the order they are shown.
        """
        self._checks = tuple(checks)

    async def run(self) -> DoctorReport:
        """Run every check once, side by side.

        Nearly all of a check is waiting for a service to answer, so the waits
        overlap instead of adding up. A check that never waits still runs to
        its end before the next one starts.

        Returns:
            The report, in the order the checks were given whichever answered
            first. A check that fails never stops the others.
        """
        # An expected failure is already a problem line by the time it gets
        # here, so the others are only ever stopped by a programming error.
        results = await gather_all(self._run_one(check) for check in self._checks)
        report = DoctorReport(tuple(results))
        _log.info("doctor_finished", healthy=report.healthy, checks=len(results))
        return report

    @staticmethod
    async def _run_one(check: Check) -> CheckResult:
        """Run one check, turning an expected failure into a problem line."""
        try:
            return await check.run()
        except TrackerError as error:
            fix = f"{OUTAGE_FIX}. {check.fix}" if isinstance(error, _OUTAGE_ERRORS) else check.fix
            return problem(check.name, error.message, fix)
        except httpx.HTTPError as error:
            _log.error(
                "doctor_check_unreachable", check=check.name, error_type=type(error).__name__
            )
            return problem(check.name, "the service could not be reached", OUTAGE_FIX)
