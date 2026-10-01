"""Data access for ``category_suggestions``: what the chosen preset suggests."""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar, Final

from supabase import Client

from tracker.domain.categories import Category
from tracker.domain.models import CategorySuggestion
from tracker.repositories.base import ALL_COLUMNS, SupabaseRepository

#: The natural key every write is keyed on.
KEY_COLUMN: Final[str] = "key"

#: Columns a write sends. The identifier and the timestamps stay the database's.
_WRITTEN_COLUMNS: Final[tuple[str, ...]] = (
    "key",
    "label",
    "group_label",
    "description",
    "colour",
    "sort_order",
)


class CategorySuggestionRepository(SupabaseRepository[CategorySuggestion]):
    """The preset's suggestions. Only the Python jobs write them; the dashboard reads."""

    table_name: ClassVar[str] = "category_suggestions"
    conflict_columns: ClassVar[tuple[str, ...]] = (KEY_COLUMN,)

    def __init__(self, client: Client) -> None:
        """Bind the repository to the shared Supabase client."""
        super().__init__(client, CategorySuggestion)

    def list_all(self) -> list[CategorySuggestion]:
        """Fetch every suggestion.

        Returns:
            The suggestions by sort order, then by key.
        """
        rows = self._select_every(lambda: self._table().select(ALL_COLUMNS), "list_all")
        return sorted(self._to_models(rows), key=lambda row: (row.sort_order, row.key))

    def replace(self, categories: Sequence[Category]) -> int:
        """Make the suggestions exactly the given categories.

        Args:
            categories: The preset's suggestions, never ``unknown``.

        Returns:
            How many suggestions are stored afterwards.
        """
        wanted = {category.key for category in categories}
        stale = [row.key for row in self.list_all() if row.key not in wanted]
        if stale:
            self._run(
                lambda: self._table().delete().in_(KEY_COLUMN, stale).execute(),
                "replace_delete",
            )
        if categories:
            payload = [category.model_dump(mode="json", include=set(_WRITTEN_COLUMNS))
                       for category in categories]
            self._run(
                lambda: self._table().upsert(payload, on_conflict=KEY_COLUMN).execute(),
                "replace_upsert",
            )
        return len(wanted)
