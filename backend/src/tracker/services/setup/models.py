"""The steps of the set-up, by name."""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Protocol

from tracker.services.setup.context import SetupContext


class StepGroup(StrEnum):
    """The two halves of the set-up: what the first morning e-mail needs, and the extras."""

    CORE = "core"
    EXTRAS = "extras"


class StepName(StrEnum):
    """Every step; ``core_steps`` and ``extra_steps`` in ``wizard`` give each half's order."""

    SUPABASE = "supabase"
    ENCRYPTION = "encryption"
    DATABASE = "database"
    LOGIN = "login"
    CATEGORIES = "categories"
    TIME_ZONE = "timezone"
    MAILBOX = "mailbox"
    MICROSOFT = "microsoft"
    LINKEDIN = "linkedin"
    DASHBOARD = "dashboard"
    SCHEDULE = "schedule"
    GITHUB = "github"
    REFRESH = "refresh"
    CLOUD = "cloud"

    @property
    def group(self) -> StepGroup:
        """The half of the set-up this step belongs to."""
        return StepGroup.EXTRAS if self in EXTRA_STEPS else StepGroup.CORE


#: The optional steps, run together by ``tracker setup extras``. Every other step is core.
EXTRA_STEPS: Final[frozenset[StepName]] = frozenset(
    {StepName.LINKEDIN, StepName.REFRESH, StepName.CLOUD}
)


class Step(Protocol):
    """One step. It raises a TrackerError when it cannot finish."""

    #: The name typed after ``tracker setup``.
    name: StepName

    #: A short title shown above the step.
    title: str

    async def is_done(self, ctx: SetupContext) -> bool:
        """Tell whether a full run may skip this step."""
        ...

    async def run(self, ctx: SetupContext) -> None:
        """Do the step, checking live before anything is written."""
        ...
