"""Where the owner's profile lives, and the limits its values must respect.

The profile decides the categories people are sorted into, the words used for
the six stages, and the guidance the assessment follows. The limits mirror the
check constraints in ``supabase/migrations/0009_categories.sql`` and
``0010_status_in_process.sql``, so a profile that loads here can always be
written there.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from tracker.shared.config import REPOSITORY_ROOT

#: Folder holding the shipped presets and the owner's own profile.
PROFILE_DIRECTORY: Final[Path] = REPOSITORY_ROOT / "profile"

#: The owner's own profile. Ignored by git: it describes what they track.
PROFILE_FILE: Final[Path] = PROFILE_DIRECTORY / "profile.toml"

#: The presets shipped with the project, one ``<name>.toml`` each.
PRESET_DIRECTORY: Final[Path] = PROFILE_DIRECTORY / "presets"

#: Preset used when the owner has no profile of their own yet.
DEFAULT_PRESET: Final[str] = "job_search"

#: Template the assessment guide is rendered from.
GUIDE_TEMPLATE_FILE: Final[Path] = PROFILE_DIRECTORY / "assessment-guide.template.md"

#: The rendered guide the assessment helper reads.
GUIDE_FILE: Final[Path] = REPOSITORY_ROOT / "docs" / "assessment-guide.md"

#: Shape of a category key: it is stored, put in URLs and written by the AI.
CATEGORY_KEY_PATTERN: Final[str] = r"^[a-z][a-z0-9_]{0,30}$"

#: Longest category label, group label or stage label.
MAX_LABEL_LENGTH: Final[int] = 40

#: Longest description of a category or a stage.
MAX_DESCRIPTION_LENGTH: Final[int] = 1000

#: Most categories a profile may hold, besides ``unknown``. The dashboard's grid
#: is designed for up to this many columns.
MAX_CATEGORIES: Final[int] = 8

#: Longest paragraph of guidance or wording in a profile.
MAX_GUIDANCE_LENGTH: Final[int] = 4000
