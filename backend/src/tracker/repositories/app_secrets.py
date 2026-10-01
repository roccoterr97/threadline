"""Data access for ``app_secrets``."""

from __future__ import annotations

from typing import ClassVar

from supabase import Client

from tracker.domain.models import AppSecret
from tracker.repositories.base import ALL_COLUMNS, SupabaseRepository


class AppSecretRepository(SupabaseRepository[AppSecret]):
    """Encrypted values the jobs need between runs, such as the mailbox key.

    No logged-in or anonymous role can read this table; only the service key
    the Python jobs use reaches it.
    """

    table_name: ClassVar[str] = "app_secrets"
    conflict_columns: ClassVar[tuple[str, ...]] = ("name",)

    def __init__(self, client: Client) -> None:
        """Bind the repository to the shared Supabase client."""
        super().__init__(client, AppSecret)

    def find_by_name(self, name: str) -> AppSecret | None:
        """Fetch one secret by its name.

        Args:
            name: The secret's name.

        Returns:
            The stored secret, or ``None`` when it has never been written.
        """
        rows = self._run(
            lambda: self._table().select(ALL_COLUMNS).eq("name", name).limit(1).execute(),
            "find_by_name",
        )
        return self._first(rows)

    def delete_by_name(self, name: str) -> int:
        """Remove one secret.

        Args:
            name: The secret's name.

        Returns:
            How many rows were deleted.
        """
        rows = self._run(
            lambda: self._table().delete().eq("name", name).execute(),
            "delete_by_name",
        )
        return len(rows)
