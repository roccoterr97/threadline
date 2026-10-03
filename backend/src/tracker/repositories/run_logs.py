"""Data access for ``run_logs``."""

from __future__ import annotations

from collections.abc import Collection
from typing import ClassVar

from supabase import Client

from tracker.domain.enums import RunStatus, RunTrigger
from tracker.domain.models import RunLog
from tracker.repositories.base import ALL_COLUMNS, SupabaseRepository


class RunLogRepository(SupabaseRepository[RunLog]):
    """One row per daily run."""

    table_name: ClassVar[str] = "run_logs"
    order_column: ClassVar[str] = "started_at"

    def __init__(self, client: Client) -> None:
        """Bind the repository to the shared Supabase client."""
        super().__init__(client, RunLog)

    def find_latest_successful(self) -> RunLog | None:
        """Fetch the most recently started run that finished cleanly.

        The collectors use it to work out how far back to read: everything since
        that run, minus an overlap, rather than the whole initial window.

        Returns:
            The newest successful run, or ``None`` when none has succeeded yet.
        """
        rows = self._run(
            lambda: self._table()
            .select(ALL_COLUMNS)
            .eq("status", RunStatus.SUCCESS.value)
            .order("started_at", desc=True)
            .limit(1)
            .execute(),
            "find_latest_successful",
        )
        return self._first(rows)

    def find_latest(self, triggers: Collection[RunTrigger]) -> RunLog | None:
        """Fetch the most recently started run of some kinds.

        A refresh and a daily run can be open at the same time; each looks
        only at runs of its own kind, so neither ever takes the other's run.

        Args:
            triggers: Only runs started by one of these count.

        Returns:
            The newest such run, or ``None`` when there is none.
        """
        values = [trigger.value for trigger in triggers]
        rows = self._run(
            lambda: self._table()
            .select(ALL_COLUMNS)
            .in_("trigger", values)
            .order("started_at", desc=True)
            .limit(1)
            .execute(),
            "find_latest",
        )
        return self._first(rows)

    def list_running(self) -> list[RunLog]:
        """List the runs still marked running, oldest first.

        Only a run in progress, or one that died part-way, has this status, so
        the list stays short.

        Returns:
            The runs that have not been closed.
        """
        rows = self._select_every(
            lambda query: query.eq("status", RunStatus.RUNNING.value),
            "list_running",
        )
        return sorted(self._to_models(rows), key=lambda run: run.started_at)
