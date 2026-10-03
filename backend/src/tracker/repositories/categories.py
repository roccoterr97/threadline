"""Data access for ``categories``: the kinds of person the owner sorts people into."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar, Final

from supabase import Client

from tracker.domain.models import CategoryRecord
from tracker.repositories.base import SupabaseRepository

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
    "archived_at",
)


class CategoryRepository(SupabaseRepository[CategoryRecord]):
    """The owner's categories. Only the Python jobs write them; the dashboard reads."""

    table_name: ClassVar[str] = "categories"
    conflict_columns: ClassVar[tuple[str, ...]] = (KEY_COLUMN,)

    def __init__(self, client: Client) -> None:
        """Bind the repository to the shared Supabase client."""
        super().__init__(client, CategoryRecord)

    def list_all(self) -> list[CategoryRecord]:
        """Fetch every category, archived ones included.

        Returns:
            The categories in display order: by sort order, then by key.
        """
        rows = self._select_every(lambda query: query, "list_all")
        return sorted(self._to_models(rows), key=lambda row: (row.sort_order, row.key))

    def active_keys(self) -> frozenset[str]:
        """Return the keys of the categories that are not archived.

        Returns:
            The keys a new assessment may use.
        """
        return frozenset(row.key for row in self.list_all() if row.archived_at is None)

    def save(self, records: Sequence[CategoryRecord]) -> list[CategoryRecord]:
        """Create or replace categories by key, keeping each row's identifier.

        Every column but the identifier and the timestamps is written, so a
        category that comes back into the profile is un-archived by the same
        call that renames it.

        Args:
            records: The categories to write. An empty sequence is a no-op.

        Returns:
            The rows as the database stored them.
        """
        if not records:
            return []
        payload = [_written(record) for record in records]
        rows = self._run(
            lambda: self._table().upsert(payload, on_conflict=KEY_COLUMN).execute(),
            "save",
        )
        return self._to_models(rows)

    def delete_by_keys(self, keys: Sequence[str]) -> int:
        """Delete categories nobody uses any more.

        The database refuses to delete a category a person or an override
        still names, so callers archive those instead.

        Args:
            keys: The keys to delete. An empty sequence is a no-op.

        Returns:
            How many rows were deleted.
        """
        if not keys:
            return 0
        rows = self._run(
            lambda: self._table().delete().in_(KEY_COLUMN, list(keys)).execute(),
            "delete_by_keys",
        )
        return len(rows)


def _written(record: CategoryRecord) -> dict[str, Any]:
    """Render the columns of one category a write may set."""
    row = record.to_row()
    return {column: row[column] for column in _WRITTEN_COLUMNS}
