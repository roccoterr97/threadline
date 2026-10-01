"""Data access for ``person_states``."""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar
from uuid import UUID

from supabase import Client

from tracker.domain.models import PersonState
from tracker.repositories.base import ALL_COLUMNS, SupabaseRepository


class PersonStateRepository(SupabaseRepository[PersonState]):
    """The assessment's current view, one row per person."""

    table_name: ClassVar[str] = "person_states"
    conflict_columns: ClassVar[tuple[str, ...]] = ("person_id",)

    def __init__(self, client: Client) -> None:
        """Bind the repository to the shared Supabase client."""
        super().__init__(client, PersonState)

    def list_for_people(self, person_ids: Sequence[UUID]) -> list[PersonState]:
        """Fetch the states of several people in one request.

        Args:
            person_ids: The people to read. An empty sequence is a no-op.

        Returns:
            The states found.
        """
        return self._select_in("person_id", person_ids, "list_for_people")

    def find_for_person(self, person_id: UUID) -> PersonState | None:
        """Fetch the state of one person.

        Args:
            person_id: The person's identifier.

        Returns:
            The state, or ``None`` when the person has not been assessed yet.
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
