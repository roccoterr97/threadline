"""The steps of the set-up, by name."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from tracker.services.setup.context import SetupContext


class StepName(StrEnum):
    """Every step, in the order the full set-up runs them."""

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
