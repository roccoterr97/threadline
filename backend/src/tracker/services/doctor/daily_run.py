"""The doctor's look at the newest daily run on GitHub.

The set-up starts the first daily run and ends without waiting for it. A run
that stops (a Claude key Claude refuses stops it in its first minute) makes
GitHub e-mail the owner, and this check says why: it reads the newest daily
run with the GitHub CLI and, when it stopped, the one line the workflow leaves
on why Claude stopped. Without the GitHub CLI signed in, or outside the
owner's own copy, there is nothing to read and the check is skipped.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Final, Protocol

from tracker.infrastructure.github_cli import GitHubRepository, WorkflowRun
from tracker.services.doctor.models import CheckResult, ok, problem, skipped
from tracker.shared.constants.claude import CLAUDE_STOPPED_TITLE
from tracker.shared.constants.github import DAILY_RUN_TITLE

#: The command that makes a new Claude key and saves it on GitHub.
_NEW_CLAUDE_KEY: Final[str] = "uv run tracker setup github"


class DailyRunReader(Protocol):
    """What the check reads with the GitHub CLI."""

    def ready(self) -> bool:
        """Tell whether the CLI is installed and signed in."""
        ...

    def repository(self) -> GitHubRepository | None:
        """Describe the repository this folder belongs to."""
        ...

    def recent_runs(self, repository: str) -> tuple[WorkflowRun, ...]:
        """The workflow's newest runs, newest first."""
        ...

    def run_notes(self, repository: str, run_id: int, title: str) -> tuple[str, ...]:
        """Read the notes with one title that a run's jobs left."""
        ...


@dataclass(slots=True)
class DailyRunCheck:
    """The newest daily run on GitHub finished well, or is still going."""

    github: DailyRunReader
    name: str = "Daily run on GitHub"
    fix: str = "open your copy on github.com, then Actions, to see the newest run"

    async def run(self) -> CheckResult:
        """Read the newest daily run, off the event loop: the GitHub CLI blocks while it reads."""
        return await asyncio.to_thread(self._look)

    def _look(self) -> CheckResult:
        """Find the owner's copy and its newest daily run, and say how it went."""
        if not self.github.ready():
            return skipped(self.name, "the GitHub CLI is not signed in on this computer")
        copy = self.github.repository()
        if copy is None or not copy.is_own_private_copy:
            return skipped(self.name, "this folder is not linked to your private copy on GitHub")
        runs = self.github.recent_runs(copy.name)
        newest = next((run for run in runs if run.title == DAILY_RUN_TITLE), None)
        if newest is None:
            return skipped(self.name, "no daily run yet")
        if not newest.finished:
            return ok(self.name, f"a daily run is going: {newest.url}")
        if newest.succeeded:
            return ok(self.name, "the newest daily run finished well")
        return self._stopped(copy.name, newest)

    def _stopped(self, repository: str, run: WorkflowRun) -> CheckResult:
        """Say why the run stopped, from the line the workflow leaves, and what to do."""
        notes = self.github.run_notes(repository, run.id, CLAUDE_STOPPED_TITLE)
        if notes:
            fix = f"if it is about the Claude key, run '{_NEW_CLAUDE_KEY}'; the run: {run.url}"
            return problem(self.name, f"the newest daily run stopped. {notes[0]}", fix)
        fix = f"open {run.url} and click the step marked with a red cross to see why"
        return problem(self.name, "the newest daily run stopped with a problem", fix)
