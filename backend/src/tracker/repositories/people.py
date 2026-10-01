"""Data access for ``people``."""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar
from uuid import UUID

from supabase import Client

from tracker.domain.enums import Relevance
from tracker.domain.models import Person
from tracker.repositories.base import ALL_COLUMNS, SupabaseRepository
from tracker.shared.constants.pagination import DEFAULT_PAGE_SIZE


class PersonRepository(SupabaseRepository[Person]):
    """Everyone the owner is in touch with."""

    table_name: ClassVar[str] = "people"

    def __init__(self, client: Client) -> None:
        """Bind the repository to the shared Supabase client."""
        super().__init__(client, Person)

    def list_by_relevance(
        self,
        relevance: Relevance,
        *,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> list[Person]:
        """List people whose relevance has the given value.

        Args:
            relevance: The value to filter on.
            limit: How many rows to return.
            offset: How many rows to skip.

        Returns:
            The page of people.
        """
        self._check_page(limit, offset)
        return self._select_page(
            lambda: self._table().select(ALL_COLUMNS).eq("relevance", relevance.value),
            limit=limit,
            offset=offset,
        )

    def list_by_ids(self, person_ids: Sequence[UUID]) -> list[Person]:
        """Fetch several people in one request, avoiding a row-by-row loop.

        Args:
            person_ids: The identifiers to fetch. An empty sequence is a no-op.

        Returns:
            The people found, in database order.
        """
        return self._select_in("id", person_ids, "list_by_ids")

    def uses_category(self, key: str) -> bool:
        """Whether any person names a category.

        Args:
            key: The category key.

        Returns:
            True when at least one person has that category.
        """
        rows = self._run(
            lambda: self._table().select("id").eq("person_type", key).limit(1).execute(),
            "uses_category",
        )
        return bool(rows)
