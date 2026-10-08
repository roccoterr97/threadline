"""The on-time morning start, as the database reports it.

A timer in the owner's database (pg_cron, migration 0016) asks the
``refresh-now`` function every 15 minutes to start the daily run once its time
has passed, because GitHub's own schedule often starts it hours late. This is
what the set-up and the doctor read back about it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time


@dataclass(frozen=True, slots=True)
class DailyStartStatus:
    """Where the on-time morning start stands.

    Attributes:
        job_scheduled: The database's timer exists and is active.
        switched_on: The function's address and key are saved in Vault.
        run_at: The daily time the database holds, or ``None`` without settings.
        time_zone: The zone that time is read in, or ``None`` without settings.
        last_started_on: The last owner-local day it started a run, if any.
    """

    job_scheduled: bool
    switched_on: bool
    run_at: time | None
    time_zone: str | None
    last_started_on: date | None

    @property
    def ready(self) -> bool:
        """Whether the timer runs and knows where to call."""
        return self.job_scheduled and self.switched_on

    def matches(self, run_at: time, time_zone: str) -> bool:
        """Whether the database holds this daily time, in this zone."""
        return self.run_at == run_at and self.time_zone == time_zone
