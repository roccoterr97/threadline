"""Shared behaviour for every table and view repository.

Repositories are the only code that knows the database exists. They speak the
Supabase HTTPS query builder, hand back domain models, and translate any
transport or API failure into :class:`DatabaseUnavailableError` so no driver
message reaches an operator.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from itertools import batched
from typing import Any, ClassVar, cast
from uuid import UUID

import httpx
from postgrest import APIError
from postgrest.base_request_builder import APIResponse
from pydantic import BaseModel
from supabase import Client, SupabaseException

from tracker.domain.models import Record
from tracker.shared.constants.collection import DATABASE_BATCH_SIZE
from tracker.shared.constants.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from tracker.shared.constants.retry import REQUEST_ATTEMPTS, REQUEST_DELAY_SECONDS
from tracker.shared.errors import DatabaseUnavailableError, ValidationFailedError
from tracker.shared.logging import get_logger

ALL_COLUMNS = "*"
_log = get_logger(__name__)

#: How the retry loop waits. Replaced in tests so they never really wait.
_sleep: Callable[[float], None] = time.sleep


class SupabaseReader[RowT: BaseModel]:
    """Read one table or view through the Supabase HTTPS API."""

    #: Name of the table or view in the ``public`` schema.
    table_name: ClassVar[str]

    #: Column a plain :meth:`list` call sorts on.
    order_column: ClassVar[str] = "created_at"

    #: Whether :meth:`list` sorts descending.
    order_descending: ClassVar[bool] = True

    #: Attempts made for one request. The start-up probe lowers this to one,
    #: because it runs its own, slower retry loop on top.
    request_attempts: int = REQUEST_ATTEMPTS

    def __init__(self, client: Client, model: type[RowT]) -> None:
        """Bind the repository to a client and to its model.

        Args:
            client: The shared Supabase client.
            model: The model each row is validated into.
        """
        self._client = client
        self._model = model

    def list(self, *, limit: int = DEFAULT_PAGE_SIZE, offset: int = 0) -> list[RowT]:
        """Fetch one page of rows.

        Args:
            limit: How many rows to return, at most :data:`MAX_PAGE_SIZE`.
            offset: How many rows to skip.

        Returns:
            The page of rows.
        """
        self._check_page(limit, offset)
        return self._select_page(
            lambda: self._table().select(ALL_COLUMNS), limit=limit, offset=offset
        )

    def _select_page(
        self,
        build_query: Callable[[], Any],
        *,
        limit: int,
        offset: int,
    ) -> list[RowT]:
        """Apply ordering and range to a filtered query, then run it.

        Args:
            build_query: Builds the query, filters included. It runs inside the
                error boundary so a transport failure is typed like any other.
            limit: How many rows to return.
            offset: How many rows to skip.

        Returns:
            The page of rows.
        """
        rows = self._run(
            lambda: build_query()
            .order(self.order_column, desc=self.order_descending)
            .range(offset, offset + limit - 1)
            .execute(),
            "list",
        )
        return self._to_models(rows)

    def _select_in(
        self,
        column: str,
        values: Sequence[UUID | str],
        operation: str,
    ) -> list[RowT]:
        """Select the rows whose ``column`` matches any of ``values``.

        Supabase receives the filter in the query string, so a few hundred
        identifiers would overflow the URL and the request would be refused.
        The filter is therefore sent in batches and the results joined here.

        Args:
            column: The column to match on.
            values: The values to look for. An empty sequence is a no-op.
            operation: The name used in the log line if a request fails.

        Returns:
            The matching rows, in no particular order.
        """
        if not values:
            return []
        found: list[RowT] = []
        for batch in batched(values, DATABASE_BATCH_SIZE):
            wanted = [str(item) for item in batch]
            rows = self._select_every(
                lambda w=wanted: self._table().select(ALL_COLUMNS).in_(column, w),
                operation,
            )
            found.extend(self._to_models(rows))
        return found

    def _select_every(
        self,
        build: Callable[[], Any],
        operation: str,
    ) -> list[dict[str, Any]]:
        """Read every row a query matches, one server page at a time.

        Supabase answers at most a fixed number of rows however large a range
        is asked for, and says nothing when it truncates. Asking for "all of
        them" in one request therefore returns a plausible, wrong answer. This
        walks the pages until one comes back empty — not merely short, because
        a short page is also what a lowered server cap looks like.

        Rows are ordered by primary key so that paging cannot repeat or skip a
        row; callers that need another order sort the joined result themselves.

        Args:
            build: Makes a fresh query builder each time it is called.
            operation: The name used in the log line if a request fails.

        Returns:
            Every matching row.
        """
        collected: list[dict[str, Any]] = []
        offset = 0
        while True:
            rows = self._run(
                lambda start=offset: build()
                .order("id")
                .range(start, start + MAX_PAGE_SIZE - 1)
                .execute(),
                operation,
            )
            collected.extend(rows)
            if not rows:
                return collected
            offset += len(rows)

    def _table(self) -> Any:  # noqa: ANN401 - the builder type changes along the call chain
        """Return a fresh query builder for this table or view."""
        return self._client.table(self.table_name)

    def _to_models(self, rows: Sequence[dict[str, Any]]) -> list[RowT]:
        """Validate raw rows into models."""
        return [self._model.model_validate(row) for row in rows]

    def _first(self, rows: Sequence[dict[str, Any]]) -> RowT | None:
        """Validate the first row, or return ``None`` when there is none."""
        if not rows:
            return None
        return self._model.model_validate(rows[0])

    def _unavailable(self, operation: str, error: Exception) -> DatabaseUnavailableError:
        """Log one clean line and build the operator-facing error.

        Args:
            operation: Name of the repository method that failed.
            error: The underlying failure, which is never shown to the caller.

        Returns:
            The typed error to raise.
        """
        _log.error(
            "database_request_failed",
            table=self.table_name,
            operation=operation,
            error_type=type(error).__name__,
        )
        message = f"database request failed on {self.table_name}.{operation}"
        return DatabaseUnavailableError(message)

    def _run(self, action: Callable[[], APIResponse], operation: str) -> list[dict[str, Any]]:
        """Execute a query and map any transport failure to a typed error.

        Args:
            action: Thunk that performs the request.
            operation: Name of the repository method, used in the log line.

        Returns:
            The rows the database returned.

        Raises:
            DatabaseUnavailableError: If the database could not be reached or
                refused the request.
        """
        for attempt in range(1, self.request_attempts + 1):
            try:
                response = action()
            except (SupabaseException, httpx.HTTPError) as error:
                # The connection failed, so the database never answered. Every
                # write here is an upsert on a natural key or a delete by id,
                # both safe to repeat, so a dropped connection mid-run is worth
                # another try rather than ending the morning's collection.
                if attempt == self.request_attempts:
                    raise self._unavailable(operation, error) from error
                _log.warning(
                    "database_request_retried",
                    table=self.table_name,
                    operation=operation,
                    attempt=attempt,
                    attempts=self.request_attempts,
                )
                _sleep(REQUEST_DELAY_SECONDS)
            except APIError as error:
                # The database answered and refused. Asking again would only
                # get the same refusal.
                raise self._unavailable(operation, error) from error
            else:
                # PostgREST types its payload as generic JSON; every table we
                # read returns objects, and the model validation proves it.
                return cast("list[dict[str, Any]]", response.data)
        message = "retry loop ended without an answer"  # pragma: no cover
        raise DatabaseUnavailableError(message)  # pragma: no cover

    @staticmethod
    def _check_page(limit: int, offset: int) -> None:
        """Reject a page request the database should not be asked for.

        Raises:
            ValidationFailedError: If the page size or the offset is out of range.
        """
        if limit < 1 or limit > MAX_PAGE_SIZE:
            message = f"page size must be between 1 and {MAX_PAGE_SIZE}"
            raise ValidationFailedError(message)
        if offset < 0:
            message = "page offset cannot be negative"
            raise ValidationFailedError(message)


class SupabaseRepository[ModelT: Record](SupabaseReader[ModelT]):
    """Read and write one table.

    Subclasses declare the natural key that makes a write idempotent, then add
    the lookups their table needs.
    """

    #: Columns forming the natural key used by :meth:`bulk_upsert`.
    conflict_columns: ClassVar[tuple[str, ...]] = ("id",)

    def get(self, record_id: UUID) -> ModelT | None:
        """Fetch one record by primary key.

        Args:
            record_id: The record's identifier.

        Returns:
            The record, or ``None`` when no row has that identifier.
        """
        rows = self._run(
            lambda: self._table().select(ALL_COLUMNS).eq("id", str(record_id)).limit(1).execute(),
            "get",
        )
        return self._first(rows)

    def bulk_upsert(self, records: Sequence[ModelT]) -> list[ModelT]:
        """Write records in batches, replacing any row with the same natural key.

        Args:
            records: The records to write. An empty sequence is a no-op.

        Returns:
            The records as the database stored them.
        """
        if not records:
            return []
        on_conflict = ",".join(self.conflict_columns)
        unique = self._last_of_each_key(records)
        written: list[ModelT] = []
        for start in range(0, len(unique), DATABASE_BATCH_SIZE):
            payload = [record.to_row() for record in unique[start : start + DATABASE_BATCH_SIZE]]
            rows = self._run(
                lambda batch=payload: self._table()
                .upsert(batch, on_conflict=on_conflict)
                .execute(),
                "bulk_upsert",
            )
            written.extend(self._to_models(rows))
        return written


    def _last_of_each_key(self, records: Sequence[ModelT]) -> list[ModelT]:
        """Keep one record per natural key, the last one wins.

        A source can hand us the same thing twice in one pass — LinkedIn began
        serving its whole archive twice on 2026-09-19. Postgres refuses an
        upsert that would touch the same row twice in a single statement, and
        it refuses the *whole* batch, so one duplicate would lose every other
        record with it. Keeping the last occurrence matches what a second
        statement would have left behind.

        Args:
            records: The records about to be written, in order.

        Returns:
            The records with earlier duplicates of a natural key removed.
        """
        by_key: dict[tuple[str, ...], ModelT] = {}
        for record in records:
            row = record.to_row()
            key = tuple(str(row.get(column)) for column in self.conflict_columns)
            by_key[key] = record
        if len(by_key) != len(records):
            _log.debug(
                "duplicate_natural_keys_dropped",
                table=self.table_name,
                offered=len(records),
                kept=len(by_key),
            )
        return list(by_key.values())

    def delete_by_ids(self, record_ids: Sequence[UUID]) -> int:
        """Delete records by primary key.

        Args:
            record_ids: The identifiers to remove. An empty sequence is a no-op.

        Returns:
            How many rows were deleted.
        """
        if not record_ids:
            return 0
        deleted = 0
        for batch in batched(record_ids, DATABASE_BATCH_SIZE):
            rows = self._run(
                lambda wanted=[str(item) for item in batch]: self._table()
                .delete()
                .in_("id", wanted)
                .execute(),
                "delete_by_ids",
            )
            deleted += len(rows)
        return deleted
