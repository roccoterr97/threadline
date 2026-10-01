"""Data access for ``status_labels``: what the dashboard calls each stage."""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar, Final

from supabase import Client

from tracker.domain.enums import ContactStatus
from tracker.domain.models import StatusLabel
from tracker.repositories.base import SupabaseRepository

#: The natural key every write is keyed on: one row per stage.
STATUS_COLUMN: Final[str] = "status"


class StatusLabelRepository(SupabaseRepository[StatusLabel]):
    """The words for the six stages. Only the Python jobs write them."""

    table_name: ClassVar[str] = "status_labels"
    conflict_columns: ClassVar[tuple[str, ...]] = (STATUS_COLUMN,)

    def __init__(self, client: Client) -> None:
        """Bind the repository to the shared Supabase client."""
        super().__init__(client, StatusLabel)

    def save(self, labels: Mapping[ContactStatus, str]) -> list[StatusLabel]:
        """Create or replace the label of each given stage, keeping row identifiers.

        Args:
            labels: The label for each stage. An empty mapping is a no-op.

        Returns:
            The rows as the database stored them.
        """
        if not labels:
            return []
        payload = [
            {STATUS_COLUMN: status.value, "label": label} for status, label in labels.items()
        ]
        rows = self._run(
            lambda: self._table().upsert(payload, on_conflict=STATUS_COLUMN).execute(),
            "save",
        )
        return self._to_models(rows)
