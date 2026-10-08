"""Which database structure files have been applied, seen from the outside.

The project keeps no table of applied migrations, and Threadline reaches the
database only through Supabase's data API. So each known migration is paired
with one thing it leaves behind — a table, a column, an enum value, an
enum-typed column or a row it rewrites — and its presence stands for the
migration's. A migration that only changes behaviour (a trigger, a function
body) leaves nothing the data API can see, and a migration newer than this
module is unknown to it: both are reported as "unconfirmed" rather than guessed
at, and the set-up judges them by where they sit among the ones it can see.

Every migration from 0003 on is written to be safe to run twice, so applying an
unconfirmed one again is harmless. 0001 and 0002 are not, which is why both have
a probe and are only ever applied when that probe says they are missing. The
newest migration always has a marker: an unconfirmed one after every visible
one would otherwise be offered again on a database that already has it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

#: Extension of a migration file.
MIGRATION_SUFFIX: Final[str] = ".sql"


class StructureProbe(Protocol):
    """Answers whether a database object exists yet."""

    def has_columns(self, table: str, columns: str) -> bool:
        """Tell whether a table or view exists with the given columns."""
        ...

    def accepts_value(self, table: str, column: str, value: str) -> bool:
        """Tell whether a column's enum type knows a value yet."""
        ...

    def is_enum_column(self, table: str, column: str) -> bool:
        """Tell whether a column is enum-typed, so it refuses a value outside its list."""
        ...

    def has_row(self, table: str, matches: Mapping[str, str]) -> bool:
        """Tell whether a table holds a row with all of the given values."""
        ...


@dataclass(frozen=True, slots=True)
class ColumnsProbe:
    """A migration is present when a table or view has these columns."""

    table: str
    columns: str

    def present(self, probe: StructureProbe) -> bool:
        """Ask the database."""
        return probe.has_columns(self.table, self.columns)


@dataclass(frozen=True, slots=True)
class EnumValueProbe:
    """A migration is present when an enum column accepts this value."""

    table: str
    column: str
    value: str

    def present(self, probe: StructureProbe) -> bool:
        """Ask the database."""
        return probe.accepts_value(self.table, self.column, self.value)


@dataclass(frozen=True, slots=True)
class EnumColumnProbe:
    """A migration is present when it has turned a column into an enum.

    A text column with a check constraint filters on any value without
    complaint, so looking for one of the enum's values cannot tell the two
    shapes apart. Only the enum refuses a value it does not list.
    """

    table: str
    column: str

    def present(self, probe: StructureProbe) -> bool:
        """Ask the database."""
        return probe.is_enum_column(self.table, self.column)


@dataclass(frozen=True, slots=True)
class RowProbe:
    """A migration is present when a row it rewrites holds the new values.

    Only for a row nothing but that migration may change: then the new values
    can only be there because the migration ran.
    """

    table: str
    matches: tuple[tuple[str, str], ...]

    def present(self, probe: StructureProbe) -> bool:
        """Ask the database."""
        return probe.has_row(self.table, dict(self.matches))


#: A migration's visible mark: what its presence is judged by.
type MigrationMarker = ColumnsProbe | EnumValueProbe | EnumColumnProbe | RowProbe

#: What each known migration leaves behind; ``None`` when nothing is visible.
KNOWN_MIGRATIONS: Final[dict[str, MigrationMarker | None]] = {
    "0001_schema": ColumnsProbe("app_secrets", "name,encrypted_value"),
    "0002_access_rules": ColumnsProbe("app_owner", "user_id"),
    "0003_people_overview": ColumnsProbe("people_overview", "person_id,has_override"),
    "0004_overdue_and_chase": ColumnsProbe("people_overview", "is_chase_due"),
    "0005_calendar": EnumValueProbe("conversations", "channel", "calendar"),
    "0006_meeting_time": ColumnsProbe("conversations", "meeting_at"),
    "0007_apply_relevance_answers": None,
    "0008_owner_time_zone": ColumnsProbe("app_settings", "time_zone"),
    "0009_categories": ColumnsProbe("categories", "key,label,colour"),
    "0010_status_in_process": ColumnsProbe("status_labels", "status,label"),
    "0011_function_access": None,
    "0012_refresh_trigger": EnumColumnProbe("run_logs", "trigger"),
    "0013_refresh_requests": ColumnsProbe("refresh_requests", "requested_at,target"),
    "0014_refresh_cooldown": ColumnsProbe("refresh_requests", "cooldown_until"),
    # The data API cannot see 0015's unique indexes, but the same file renames
    # the reserved category's group from the seeded "Unknown" to "Not known",
    # and the database's guard lets nothing else change that row.
    "0015_category_names": RowProbe(
        "categories", (("key", "unknown"), ("group_label", "Not known"))
    ),
    # Asked for without the notes' text: the jobs never read what the owner wrote.
    "0016_person_notes": ColumnsProbe("person_notes", "id,person_id"),
    "0017_daily_start": ColumnsProbe("daily_starts", "owner_date,requested_at"),
}


@dataclass(frozen=True, slots=True)
class MigrationFile:
    """One structure file in ``supabase/migrations``.

    Attributes:
        name: The file name without ``.sql``, such as ``0001_schema``.
        path: Where the file is.
    """

    name: str
    path: Path

    def sql(self) -> str:
        """Read the file's content."""
        return self.path.read_text(encoding="utf-8")


@dataclass(frozen=True, slots=True)
class StructureReport:
    """Where each migration stands.

    Attributes:
        present: Confirmed applied.
        missing: Confirmed not applied.
        unconfirmed: Applied or not, the data API cannot tell.
    """

    present: tuple[str, ...]
    missing: tuple[str, ...]
    unconfirmed: tuple[str, ...]


def list_migration_files(directory: Path) -> tuple[MigrationFile, ...]:
    """List the migration files in the order they must be applied.

    Args:
        directory: The ``supabase/migrations`` folder.

    Returns:
        Every ``.sql`` file, sorted by name; empty when the folder is missing.
    """
    if not directory.is_dir():
        return ()
    files = sorted(path for path in directory.iterdir() if path.suffix == MIGRATION_SUFFIX)
    return tuple(MigrationFile(name=path.stem, path=path) for path in files)


def inspect_structure(
    files: tuple[MigrationFile, ...],
    probe: StructureProbe,
) -> StructureReport:
    """Look for each migration's object in the database.

    Args:
        files: The migration files, in order.
        probe: Answers whether an object exists.

    Returns:
        Which migrations are present, missing, or cannot be confirmed.

    Raises:
        DatabaseUnavailableError: If the database could not answer.
    """
    present: list[str] = []
    missing: list[str] = []
    unconfirmed: list[str] = []
    for migration in files:
        seen = is_applied(migration.name, probe)
        if seen is None:
            unconfirmed.append(migration.name)
        elif seen:
            present.append(migration.name)
        else:
            missing.append(migration.name)
    return StructureReport(tuple(present), tuple(missing), tuple(unconfirmed))


def is_applied(name: str, probe: StructureProbe) -> bool | None:
    """Look for one migration's object in the database.

    Args:
        name: The migration's name, such as ``0003_people_overview``.
        probe: Answers whether an object exists.

    Returns:
        Whether it is applied, or ``None`` when the data API cannot tell.

    Raises:
        DatabaseUnavailableError: If the database could not answer.
    """
    marker = KNOWN_MIGRATIONS.get(name)
    if marker is None:
        return None
    return marker.present(probe)
