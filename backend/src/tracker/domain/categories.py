"""The categories the owner sorts people into.

A category ("Startup", "Investor", "Prospect"…) is data, not code: the owner
chooses them in their profile and ``tracker profile apply`` writes them to the
``categories`` table. No rule anywhere branches on a category, so any list the
owner writes is safe. One key is reserved: :data:`UNKNOWN_CATEGORY_KEY`, which
every person starts with and which can never be removed.
"""

from __future__ import annotations

import re
from collections.abc import Collection
from enum import StrEnum
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from tracker.shared.constants.profile import (
    CATEGORY_KEY_PATTERN,
    MAX_DESCRIPTION_LENGTH,
    MAX_LABEL_LENGTH,
)

#: The reserved category every person starts with.
UNKNOWN_CATEGORY_KEY: Final[str] = "unknown"

#: Not a category: the dashboard's filters use it to mean "every category".
ALL_CATEGORIES_KEY: Final[str] = "all"

#: Keys a profile may not define.
RESERVED_CATEGORY_KEYS: Final[frozenset[str]] = frozenset(
    {UNKNOWN_CATEGORY_KEY, ALL_CATEGORIES_KEY}
)

#: Where ``unknown`` sits in every list: after anything the owner defines.
UNKNOWN_SORT_ORDER: Final[int] = 1000

#: A category key as it is stored, filtered on and written by the AI.
CategoryKey = Annotated[str, StringConstraints(pattern=CATEGORY_KEY_PATTERN)]

#: A short piece of on-screen text.
Label = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_LABEL_LENGTH)
]

#: A description written for the AI and for the owner.
Description = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=MAX_DESCRIPTION_LENGTH)
]


class ColourSlot(StrEnum):
    """The named colours a category may use; the dashboard owns the exact shades."""

    VIOLET = "violet"
    CYAN = "cyan"
    ORANGE = "orange"
    PINK = "pink"
    INDIGO = "indigo"
    TEAL = "teal"
    OLIVE = "olive"
    BROWN = "brown"
    GREY = "grey"


class Category(BaseModel):
    """One category, as the profile defines it.

    Attributes:
        key: The stored value, such as ``vc``. Never shown on screen.
        label: What one person of this kind is called, such as "Investor".
        group_label: What several are called, such as "Investors".
        description: Who belongs here, written for the AI.
        colour: The palette slot the dashboard colours it with.
        sort_order: Position in every list, lowest first.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: CategoryKey
    label: Label
    group_label: Label
    description: Description = ""
    colour: ColourSlot
    sort_order: int = Field(ge=0, le=UNKNOWN_SORT_ORDER)


#: The reserved category, exactly as the database holds it once 0015 is applied.
UNKNOWN_CATEGORY: Final[Category] = Category(
    key=UNKNOWN_CATEGORY_KEY,
    label="Not known",
    group_label="Not known",
    description="Not clear from the conversation yet.",
    colour=ColourSlot.GREY,
    sort_order=UNKNOWN_SORT_ORDER,
)

#: Longest key :func:`key_for` makes, matching :data:`CATEGORY_KEY_PATTERN`.
_MAX_KEY_LENGTH: Final[int] = 31

#: Put in front of a key that would not start with a letter.
_KEY_PREFIX: Final[str] = "c_"

_NOT_KEY_CHARACTERS: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9]+")


def key_for(label: str, taken: Collection[str]) -> str:
    """Make a new category's key from its label.

    The same rule as the dashboard's: lower case, anything but letters and
    digits becomes ``_``, a leading letter is guaranteed, and a key already
    taken — or reserved — gets ``_2``, ``_3``… added.

    Args:
        label: The label the owner typed, such as "Press contacts".
        taken: Keys already in use.

    Returns:
        A free key, such as ``press_contacts``.
    """
    base = _NOT_KEY_CHARACTERS.sub("_", label.lower()).strip("_") or "category"
    if not base[0].isalpha():
        base = f"{_KEY_PREFIX}{base}"
    base = base[:_MAX_KEY_LENGTH].rstrip("_")
    unavailable = set(taken) | RESERVED_CATEGORY_KEYS
    candidate, number = base, 1
    while candidate in unavailable:
        number += 1
        suffix = f"_{number}"
        candidate = f"{base[: _MAX_KEY_LENGTH - len(suffix)]}{suffix}"
    return candidate
