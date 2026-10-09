"""Where the program is running, and the words that depend on it."""

from __future__ import annotations

import os

from tracker.shared.constants.runtime import (
    CONFIGURATION_FIX_ON_COMPUTER,
    CONFIGURATION_FIX_ON_GITHUB,
    GITHUB_ACTIONS_FLAG,
)


def running_on_github() -> bool:
    """Whether this is a GitHub workflow run rather than someone's computer."""
    return os.environ.get(GITHUB_ACTIONS_FLAG) == "true"


def configuration_fix() -> str:
    """Say what to do about a missing or wrong configuration, where this runs.

    Returns:
        The fix for a computer, or the one for a GitHub workflow run.
    """
    return CONFIGURATION_FIX_ON_GITHUB if running_on_github() else CONFIGURATION_FIX_ON_COMPUTER
