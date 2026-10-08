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

PERSON_COLUMN = "person_id"
OTHER_PERSON_COLUMN = "other_person_id"


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
            lambda query: query.eq("kind", kind.value),
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
        return self._select_in(PERSON_COLUMN, person_ids, "list_for_people")

    def list_naming_people(self, person_ids: Sequence[UUID]) -> list[ReviewItem]:
        """Fetch every question that names any of several people, on either side.

        A "same person?" question names a second record in ``other_person_id``.
        The database removes the question when either record goes, so a merge
        has to find both kinds before it removes one.

        Args:
            person_ids: The people to look for. An empty sequence is a no-op.

        Returns:
            The review items found, each once.
        """
        found = {
            item.id: item
            for column in (PERSON_COLUMN, OTHER_PERSON_COLUMN)
            for item in self._select_in(column, person_ids, "list_naming_people")
        }
        return list(found.values())

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

    def list_every_unanswered(self) -> list[ReviewItem]:
        """Fetch every question the owner has not answered yet.

        Returns:
            The unanswered review items, in the order :meth:`list_unanswered`
            pages them: oldest question last.
        """
        return self._list_every(lambda query: query.is_("answer", None), "list_every_unanswered")
