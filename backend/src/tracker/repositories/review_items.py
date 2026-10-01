"""Data access for ``review_items``."""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar
from uuid import UUID

from supabase import Client

from tracker.domain.enums import ReviewKind
from tracker.domain.models import ReviewItem
from tracker.repositories.base import ALL_COLUMNS, SupabaseRepository
from tracker.shared.constants.pagination import DEFAULT_PAGE_SIZE


class ReviewItemRepository(SupabaseRepository[ReviewItem]):
    """Questions waiting for the owner's yes or no."""

    table_name: ClassVar[str] = "review_items"

    def __init__(self, client: Client) -> None:
        """Bind the repository to the shared Supabase client."""
        super().__init__(client, ReviewItem)

    def list_by_kind(self, kind: ReviewKind) -> list[ReviewItem]:
        """Fetch every question of one kind, answered or not.

        The matcher uses this to avoid asking the owner the same "same person?"
        question on every run.

        Args:
            kind: Which kind of question to read.

        Returns:
            The review items of that kind.
        """
        rows = self._select_every(
            lambda: self._table().select(ALL_COLUMNS).eq("kind", kind.value),
            "list_by_kind",
        )
        return self._to_models(rows)

    def list_for_people(self, person_ids: Sequence[UUID]) -> list[ReviewItem]:
        """Fetch every question asked about several people, answered or not.

        Args:
            person_ids: The people to read. An empty sequence is a no-op.

        Returns:
            The review items found.
        """
        return self._select_in("person_id", person_ids, "list_for_people")

    def list_unanswered(
        self,
        *,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> list[ReviewItem]:
        """List the questions the owner has not answered yet.

        Args:
            limit: How many rows to return.
            offset: How many rows to skip.

        Returns:
            The page of unanswered review items, oldest question last.
        """
        self._check_page(limit, offset)
        return self._select_page(
            lambda: self._table().select(ALL_COLUMNS).is_("answer", None),
            limit=limit,
            offset=offset,
        )
