"""Which database structure files have been applied, seen from the outside.

The project keeps no table of applied migrations, and Threadline reaches the
database only through Supabase's data API. So each known migration is paired
with one object it creates — a table, a column or an enum value — and the
object's presence stands for the migration's. A migration that only changes
behaviour (a trigger, a function body) leaves nothing the data API can see, and
a migration newer than this module is unknown to it: both are reported as
"unconfirmed" rather than guessed at.

Every migration from 0003 on is written to be safe to run twice, so applying an
unconfirmed one again is harmless. 0001 and 0002 are not, which is why both have
a probe and are only ever applied when that probe says they are missing.
"""

from __future__ import annotations

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


#: What each known migration leaves behind; ``None`` when nothing is visible.
KNOWN_MIGRATIONS: Final[dict[str, ColumnsProbe | EnumValueProbe | None]] = {
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
    "0012_refresh_trigger": EnumValueProbe("run_logs", "trigger", "refresh"),
    "0013_refresh_requests": ColumnsProbe("refresh_requests", "requested_at,target"),
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
