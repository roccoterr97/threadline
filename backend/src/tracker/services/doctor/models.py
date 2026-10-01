"""What a check is and what it answers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class CheckStatus(StrEnum):
    """How one check ended."""

    OK = "ok"
    WARNING = "warning"
    PROBLEM = "problem"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class CheckResult:
    """One line of the doctor's report.

    Attributes:
        name: What was checked, in plain words.
        status: How it ended.
        detail: What was found. Never a secret, never a stack trace.
        fix: What to do about it, when there is something to do.
    """

    name: str
    status: CheckStatus
    detail: str
    fix: str = ""


class Check(Protocol):
    """One independent live check.

    The doctor runs its checks side by side, so a check never relies on
    another one having run first.

    A check returns its result, or raises a
    :class:`~tracker.shared.errors.TrackerError`; the doctor turns that error
    into a problem line carrying the check's ``fix``.
    """

    #: What is checked, in plain words.
    name: str

    #: What to do when the check raises.
    fix: str

    async def run(self) -> CheckResult:
        """Check once, live."""
        ...


def ok(name: str, detail: str) -> CheckResult:
    """Build a passing result."""
    return CheckResult(name, CheckStatus.OK, detail)


def problem(name: str, detail: str, fix: str) -> CheckResult:
    """Build a failing result."""
    return CheckResult(name, CheckStatus.PROBLEM, detail, fix)


def skipped(name: str, detail: str) -> CheckResult:
    """Build a result for a check that does not apply."""
    return CheckResult(name, CheckStatus.SKIPPED, detail)


def warning(name: str, detail: str, fix: str) -> CheckResult:
    """Build a result that passes but needs attention soon."""
    return CheckResult(name, CheckStatus.WARNING, detail, fix)
