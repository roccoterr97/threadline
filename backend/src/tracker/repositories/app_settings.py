"""Data access for ``app_settings``: the one row of owner settings."""

from __future__ import annotations

from typing import ClassVar, Final

from supabase import Client

from tracker.domain.models import AppSettings
from tracker.repositories.base import ALL_COLUMNS, SupabaseReader

#: Column that is always true and unique, so the table holds exactly one row.
SINGLETON_COLUMN: Final[str] = "singleton"

#: Column holding the owner's IANA time zone.
TIME_ZONE_COLUMN: Final[str] = "time_zone"

#: Column holding the preset the owner chose.
PRESET_COLUMN: Final[str] = "preset"


class AppSettingsRepository(SupabaseReader[AppSettings]):
    """The owner's settings the database needs, such as the time zone.

    The dashboard may read the row; only the service key the Python jobs use
    may write it.
    """

    table_name: ClassVar[str] = "app_settings"

    def __init__(self, client: Client) -> None:
        """Bind the repository to the shared Supabase client."""
        super().__init__(client, AppSettings)

    def save_time_zone(self, time_zone: str) -> AppSettings | None:
        """Write the owner's time zone into the one settings row.

        The row is keyed on its singleton column, so this creates it when it is
        missing and updates it otherwise, and never touches its identifier.

        Args:
            time_zone: An IANA zone name, already validated by the configuration.

        Returns:
            The row as stored, or ``None`` if the database returned nothing.
        """
        payload = [{SINGLETON_COLUMN: True, TIME_ZONE_COLUMN: time_zone}]
        rows = self._run(
            lambda: self._table().upsert(payload, on_conflict=SINGLETON_COLUMN).execute(),
            "save_time_zone",
        )
        return self._first(rows)

    def save_preset(self, preset: str) -> AppSettings | None:
        """Remember the preset the owner chose.

        Args:
            preset: The preset's name, already checked against the shipped ones.

        Returns:
            The row as stored, or ``None`` if the database returned nothing.
        """
        payload = [{SINGLETON_COLUMN: True, PRESET_COLUMN: preset}]
        rows = self._run(
            lambda: self._table().upsert(payload, on_conflict=SINGLETON_COLUMN).execute(),
            "save_preset",
        )
        return self._first(rows)

    def read_preset(self) -> str | None:
        """Return the preset the owner chose, if any.

        Returns:
            The preset's name, or ``None`` when none was chosen.
        """
        rows = self._run(
            lambda: self._table().select(ALL_COLUMNS).eq(SINGLETON_COLUMN, True).limit(1).execute(),
            "read_preset",
        )
        settings = self._first(rows)
        return settings.preset if settings is not None else None
