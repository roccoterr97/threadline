"""Data access for ``run_step_logs``."""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar
from uuid import UUID

from supabase import Client

from tracker.domain.enums import RunStatus, RunStep
from tracker.domain.models import RunStepLog
from tracker.repositories.base import ALL_COLUMNS, SupabaseRepository


class RunStepLogRepository(SupabaseRepository[RunStepLog]):
    """One row per step of a daily run. Holds counts and error codes only."""

    table_name: ClassVar[str] = "run_step_logs"

    def __init__(self, client: Client) -> None:
        """Bind the repository to the shared Supabase client."""
        super().__init__(client, RunStepLog)

    def list_for_run(self, run_id: UUID) -> list[RunStepLog]:
        """List the steps of one run.

        Args:
            run_id: The run's identifier.

        Returns:
            The steps, oldest first.
        """
        rows = self._select_every(
            lambda: self._table().select(ALL_COLUMNS).eq("run_id", str(run_id)),
            "list_for_run",
        )
        found = self._to_models(rows)
        # The database fills created_at, so a row built in memory has none yet;
        # those sort last rather than breaking the comparison.
        found.sort(key=lambda step: (step.created_at is not None, step.created_at))
        return found

    def list_for_runs(self, run_ids: Sequence[UUID]) -> list[RunStepLog]:
        """List the steps of several runs at once.

        Args:
            run_ids: The runs' identifiers; an empty sequence reads nothing.

        Returns:
            The steps, in no particular order.
        """
        return self._select_in("run_id", run_ids, "list_for_runs")

    def find_latest_successful(self, step: RunStep) -> RunStepLog | None:
        """Fetch the most recent time one step finished cleanly.

        A refresh reads a source from the last time that source was read
        successfully, even when another source failed in the same run.

        Args:
            step: The step to look for, such as ``collect_email``.

        Returns:
            The newest successful record of that step, or ``None``.
        """
        rows = self._run(
            lambda: self._table()
            .select(ALL_COLUMNS)
            .eq("step", step.value)
            .eq("status", RunStatus.SUCCESS.value)
            .order("created_at", desc=True)
            .limit(1)
            .execute(),
            "find_latest_successful",
        )
        return self._first(rows)
