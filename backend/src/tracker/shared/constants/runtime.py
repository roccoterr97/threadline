"""Fixed words and flags that depend on where the program runs.

None of it is a secret or differs between machines, so it is code rather than
configuration.
"""

from __future__ import annotations

from typing import Final

#: GitHub sets this variable to "true" in every workflow run.
GITHUB_ACTIONS_FLAG: Final[str] = "GITHUB_ACTIONS"

#: What to do when the configuration is missing or wrong on a computer, as the
#: doctor and a failed command both say it.
CONFIGURATION_FIX_ON_COMPUTER: Final[str] = "run 'uv run tracker setup'"

#: The same, said on GitHub, where the settings are secrets of the repository.
CONFIGURATION_FIX_ON_GITHUB: Final[str] = (
    "add the missing secrets with 'uv run tracker setup github'"
)
