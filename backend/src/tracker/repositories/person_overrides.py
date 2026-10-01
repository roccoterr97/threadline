"""Data access for ``person_overrides``."""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar
from uuid import UUID

from supabase import Client

from tracker.domain.models import PersonOverride
from tracker.repositories.base import ALL_COLUMNS, SupabaseRepository


class PersonOverrideRepository(SupabaseRepository[PersonOverride]):
    """What the owner corrected by hand. These values beat the assessment."""

    table_name: ClassVar[str] = "person_overrides"
    conflict_columns: ClassVar[tuple[str, ...]] = ("person_id",)

    def __init__(self, client: Client) -> None:
        """Bind the repository to the shared Supabase client."""
        super().__init__(client, PersonOverride)

    def list_for_people(self, person_ids: Sequence[UUID]) -> list[PersonOverride]:
        """Fetch the overrides of several people in one request.

        Args:
            person_ids: The people to read. An empty sequence is a no-op.

        Returns:
            The overrides found; people the owner never corrected are absent.
        """
        return self._select_in("person_id", person_ids, "list_for_people")

    def find_for_person(self, person_id: UUID) -> PersonOverride | None:
        """Fetch the override of one person.

        Args:
            person_id: The person's identifier.

        Returns:
            The override, or ``None`` when the owner has corrected nothing.
        """
        rows = self._run(
            lambda: self._table()
            .select(ALL_COLUMNS)
            .eq("person_id", str(person_id))
            .limit(1)
            .execute(),
            "find_for_person",
        )
        return self._first(rows)

    def uses_category(self, key: str) -> bool:
        """Whether any override names a category.

        Args:
            key: The category key.

        Returns:
            True when at least one override has that category.
        """
        rows = self._run(
            lambda: self._table().select("id").eq("person_type", key).limit(1).execute(),
            "uses_category",
        )
        return bool(rows)
