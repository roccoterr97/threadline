"""Page sizes for reading lists out of the database.

Nothing that can grow unbounded is read in one go; repositories page instead.
"""

from __future__ import annotations

from typing import Final

#: Rows returned by a repository ``list`` call when the caller asks for no size.
DEFAULT_PAGE_SIZE: Final[int] = 100

#: Largest page a caller may ask a repository for.
MAX_PAGE_SIZE: Final[int] = 1000
