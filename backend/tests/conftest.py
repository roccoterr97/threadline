"""Shared test fixtures.

No test touches the network, the real ``.env`` file, or the wall clock. The
Supabase client is replaced by a small in-memory fake that behaves like the
query builder the repositories use.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Self, cast
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from supabase import Client

from tracker.domain.rules import RulePack
from tracker.infrastructure.database import reset_database_client_cache
from tracker.repositories import Repositories, build_repositories
from tracker.services.profile.loader import preset_path, read_profile
from tracker.shared import config
from tracker.shared.clock import FixedClock
from tracker.shared.config import Settings
from tracker.shared.logging import configure_logging

ENVIRONMENT_VARIABLES = (
    "APP_ENV",
    "LOG_LEVEL",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_ANON_KEY",
    "TOKEN_ENCRYPTION_KEY",
    "OWNER_LINKEDIN_PROFILE_URL",
    "OWNER_EMAIL_ADDRESSES",
    "LINKEDIN_ACCESS_TOKEN",
    "LINKEDIN_TOKEN_EXPIRES_ON",
    "DASHBOARD_BASE_URL",
    "SUMMARY_RECIPIENT",
    "OWNER_DISPLAY_NAME",
    "OWNER_TIME_ZONE",
    "OWNER_WEEKEND_DAYS",
    "PRODUCT_NAME",
    "SUMMARY_SUBJECT_PREFIX",
    "MAIL_SOURCES",
    "IMAP_PROVIDER",
    "IMAP_HOST",
    "IMAP_PORT",
    "IMAP_USERNAME",
    "SUMMARY_DELIVERY",
    "SMTP_HOST",
    "SMTP_PORT",
)

#: A throwaway Fernet key, made afresh for every test session. No test depends
#: on its value, only on it being valid and the same throughout one session.
TEST_ENCRYPTION_KEY: Final[str] = Fernet.generate_key().decode()

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def isolated_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[None]:
    """Hide the real ``.env`` and any inherited variable from every test."""
    configure_logging()
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "absent.env")
    for name in ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    config.reset_settings_cache()
    reset_database_client_cache()
    yield
    config.reset_settings_cache()
    reset_database_client_cache()


@pytest.fixture
def valid_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set every required variable to a made-up but well-formed value."""
    monkeypatch.setenv("SUPABASE_URL", "https://sample-project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", TEST_ENCRYPTION_KEY)
    monkeypatch.setenv("OWNER_LINKEDIN_PROFILE_URL", "https://www.linkedin.com/in/sam")
    monkeypatch.setenv("OWNER_EMAIL_ADDRESSES", "sam.rivera@mailbox.example, Sam@Other.Example")
    config.reset_settings_cache()


@pytest.fixture
def settings(valid_environment: None, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Configuration built from the made-up environment, LinkedIn key included."""
    monkeypatch.setenv("LINKEDIN_ACCESS_TOKEN", "made-up-linkedin-key")
    config.reset_settings_cache()
    return config.get_settings()


@pytest.fixture
def settings_without_linkedin_key(valid_environment: None) -> Settings:
    """Configuration with no LinkedIn key, as a fresh checkout has."""
    return config.get_settings()


@pytest.fixture
def clock() -> FixedClock:
    """A clock frozen at a fixed instant."""
    return FixedClock(datetime(2026, 9, 18, 7, 0, tzinfo=UTC))


class FakeResponse:
    """Stands in for the query builder's response object."""

    def __init__(self, data: list[dict[str, Any]]) -> None:
        """Hold the rows a query returned."""
        self.data = data


class FakeQuery:
    """A tiny in-memory imitation of the Supabase query builder."""

    def __init__(self, rows: list[dict[str, Any]], client: FakeSupabaseClient, table: str) -> None:
        """Bind the query to one table of the fake client."""
        self._rows = rows
        self._client = client
        self._table = table
        self._filters: list[tuple[str, str, Any]] = []
        self._order: tuple[str, bool] | None = None
        self._range: tuple[int, int] | None = None
        self._limit: int | None = None
        self._operation = "select"
        self._payload: list[dict[str, Any]] = []

    def select(self, *_columns: str, **_options: Any) -> Self:
        """Start a read."""
        self._operation = "select"
        return self

    def upsert(self, json: list[dict[str, Any]], **options: Any) -> Self:
        """Start a write keyed on ``on_conflict``."""
        self._operation = "upsert"
        self._payload = list(json)
        self._client.conflict_columns[self._table] = str(options.get("on_conflict", "id"))
        return self

    def delete(self, **_options: Any) -> Self:
        """Start a delete."""
        self._operation = "delete"
        return self

    def eq(self, column: str, value: Any) -> Self:
        """Keep rows whose column equals ``value``."""
        self._filters.append((column, "eq", value))
        return self

    def in_(self, column: str, values: list[Any]) -> Self:
        """Keep rows whose column is one of ``values``."""
        self._filters.append((column, "in", list(values)))
        return self

    def is_(self, column: str, value: Any) -> Self:
        """Keep rows whose column is null or the given literal."""
        self._filters.append((column, "is", value))
        return self

    def order(self, column: str, *, desc: bool = False, **_options: Any) -> Self:
        """Sort the result."""
        self._order = (column, desc)
        return self

    def limit(self, size: int, **_options: Any) -> Self:
        """Cap the number of rows."""
        self._limit = size
        return self

    def range(self, start: int, end: int, **_options: Any) -> Self:
        """Return the rows between two positions, both included."""
        self._range = (start, end)
        return self

    def execute(self) -> FakeResponse:
        """Run the query against the in-memory rows."""
        self._client.executed.append((self._table, self._operation))
        if self._operation == "upsert":
            return FakeResponse(self._apply_upsert())
        matched = self._matching()
        if self._operation == "delete":
            for row in matched:
                self._rows.remove(row)
            return FakeResponse(matched)
        return FakeResponse(self._page(matched))

    def _matching(self) -> list[dict[str, Any]]:
        """Return the rows that satisfy every filter."""
        return [row for row in self._rows if all(self._keeps(row, f) for f in self._filters)]

    @staticmethod
    def _keeps(row: dict[str, Any], condition: tuple[str, str, Any]) -> bool:
        """Decide whether one row satisfies one filter."""
        column, operator, value = condition
        actual = row.get(column)
        if operator == "eq":
            return str(actual) == str(value)
        if operator == "in":
            return str(actual) in {str(item) for item in value}
        return actual is None if value is None else str(actual) == str(value)

    def _page(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Apply ordering, range and limit."""
        result = list(rows)
        if self._order is not None:
            column, desc = self._order
            result.sort(key=lambda row: str(row.get(column) or ""), reverse=desc)
        if self._range is not None:
            start, end = self._range
            result = result[start : end + 1]
        if self._limit is not None:
            result = result[: self._limit]
        # Supabase caps every answer, whatever range was asked for, and says
        # nothing about it. Modelling the cap here is what makes a query that
        # forgets to page fail in the tests instead of in production.
        return result[:SERVER_ROW_CAP]

    def _apply_upsert(self) -> list[dict[str, Any]]:
        """Replace rows matching the natural key, insert the rest."""
        keys = self._client.conflict_columns[self._table].split(",")
        written: list[dict[str, Any]] = []
        for candidate in self._payload:
            signature = tuple(str(candidate.get(key)) for key in keys)
            existing = next(
                (row for row in self._rows if tuple(str(row.get(k)) for k in keys) == signature),
                None,
            )
            if existing is not None:
                existing.update(candidate)
                written.append(existing)
                continue
            # The database fills in a primary key the payload left out.
            candidate.setdefault("id", str(uuid4()))
            self._rows.append(candidate)
            written.append(candidate)
        return written


#: The collection rules every test runs under: the job-search preset's, which
#: reproduce the rules Threadline had before they became a preset's.
JOB_SEARCH_RULES: Final[RulePack] = read_profile(preset_path("job_search")).rules

#: Rows Supabase returns at most for one request, however large a range is asked for.
SERVER_ROW_CAP: Final[int] = 1000


class FakeSupabaseClient:
    """An in-memory stand-in for the Supabase client."""

    def __init__(self, tables: dict[str, list[dict[str, Any]]] | None = None) -> None:
        """Start with the given rows, or with empty tables."""
        self.tables: dict[str, list[dict[str, Any]]] = tables or {}
        self.conflict_columns: dict[str, str] = {}
        self.executed: list[tuple[str, str]] = []

    def table(self, table_name: str) -> FakeQuery:
        """Return a query builder for one table."""
        rows = self.tables.setdefault(table_name, [])
        return FakeQuery(rows, self, table_name)


@pytest.fixture
def fake_client() -> FakeSupabaseClient:
    """An empty in-memory database."""
    return FakeSupabaseClient()


@pytest.fixture
def repositories(fake_client: FakeSupabaseClient) -> Repositories:
    """Repositories wired to the in-memory database."""
    return build_repositories(as_client(fake_client))


def as_client(fake: FakeSupabaseClient) -> Client:
    """Present the fake where a real Supabase client is expected.

    Args:
        fake: The in-memory stand-in.

    Returns:
        The same object, typed as the real client so repositories accept it.
    """
    return cast("Client", fake)


@pytest.fixture(autouse=True)
def _no_real_waiting(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never really sleep between retries.

    The retry policy is deliberately slow in production. Tests assert on what
    would have been waited, never by waiting, so the whole suite stays fast and
    free of any dependence on the wall clock.
    """
    monkeypatch.setattr("tracker.shared.http.SOURCE_REQUEST_DELAY_SECONDS", 0.0)
    monkeypatch.setattr("tracker.shared.http.SOURCE_RETRY_AFTER_CAP_SECONDS", 0.0)
    monkeypatch.setattr("tracker.repositories.base.REQUEST_DELAY_SECONDS", 0.0)
    monkeypatch.setattr("tracker.infrastructure.imap.session.SOURCE_REQUEST_DELAY_SECONDS", 0.0)
