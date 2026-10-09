"""Set-up and diagnosis work on Supabase that the repositories do not do.

The repositories read and write Threadline's own rows. Setting up a project
needs a few other things: seeing whether a table, column or value exists yet,
finding or creating the dashboard login, recording who owns the dashboard, and
switching on the on-time morning start (the daily time, and the timer's
address and key, which the database keeps in Vault). All of it goes through
the same service-key client, over HTTPS.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date, time
from typing import Any, Final, cast

import httpx
from postgrest import APIError
from pydantic import SecretStr
from supabase import Client, SupabaseException
from supabase_auth.errors import AuthError

from tracker.domain.daily_start import DailyStartStatus
from tracker.shared.constants.setup import (
    AUTH_USERS_MAX_PAGES,
    AUTH_USERS_PAGE_SIZE,
    DAILY_START_SAVE_FUNCTION,
    DAILY_START_STATUS_FUNCTION,
)
from tracker.shared.errors import (
    DatabaseStructureMissingError,
    DatabaseUnavailableError,
    SourceAuthError,
)
from tracker.shared.logging import get_logger

#: Error codes the data API answers when a table, a column or an enum value
#: does not exist yet — "not set up", as opposed to "broken".
MISSING_OBJECT_CODES: Final[frozenset[str]] = frozenset(
    {"42P01", "42703", "22P02", "PGRST200", "PGRST204", "PGRST205"}
)

#: Postgres code for "not a value of this enum" — only an enum column says it.
INVALID_ENUM_VALUE_CODE: Final[str] = "22P02"

#: A value no Threadline enum lists, used to see whether a column is an enum.
UNLISTED_ENUM_VALUE: Final[str] = "threadline-structure-probe"

#: Auth server code for "a user with this address already exists".
EMAIL_EXISTS_CODE: Final[str] = "email_exists"

#: Auth server statuses meaning the key is not the secret one.
REFUSED_KEY_STATUSES: Final[frozenset[int]] = frozenset({401, 403})

#: Error codes meaning a newer structure file has not been applied: a missing
#: table, column or database function.
STRUCTURE_MISSING_CODES: Final[frozenset[str]] = frozenset(
    {"42P01", "42703", "42883", "PGRST202", "PGRST204", "PGRST205"}
)

_OWNER_TABLE: Final[str] = "app_owner"
_OWNER_COLUMN: Final[str] = "user_id"
_SETTINGS_TABLE: Final[str] = "app_settings"
_SINGLETON_COLUMN: Final[str] = "singleton"
#: How a daily time is written for Postgres' ``time`` column.
_TIME_FORMAT: Final[str] = "%H:%M"

_log = get_logger(__name__)


class SupabaseAdmin:
    """Structure probes and the dashboard owner, on the service-key client."""

    def __init__(self, client: Client) -> None:
        """Bind the helper to a client made with the secret key.

        Args:
            client: A Supabase client authenticated with the service key.
        """
        self._client = client

    def has_columns(self, table: str, columns: str) -> bool:
        """Tell whether a table or view exists with the given columns.

        Args:
            table: Name in the ``public`` schema.
            columns: Comma-separated column names.

        Returns:
            ``False`` when the table or a column is missing.

        Raises:
            DatabaseUnavailableError: If the database could not answer.
        """
        return self._answers(lambda: self._client.table(table).select(columns).limit(1).execute())

    def accepts_value(self, table: str, column: str, value: str) -> bool:
        """Tell whether a column's enum type knows a value yet.

        Args:
            table: Name in the ``public`` schema.
            column: An enum-typed column of that table.
            value: The value to look for.

        Returns:
            ``False`` when the database rejects the value as unknown.

        Raises:
            DatabaseUnavailableError: If the database could not answer.
        """
        return self._answers(
            lambda: self._client.table(table).select(column).eq(column, value).limit(1).execute()
        )

    def is_enum_column(self, table: str, column: str) -> bool:
        """Tell whether a column is enum-typed, by filtering on a value no enum lists.

        An enum column refuses the value outright; a text column — even one
        with a check constraint — simply finds no row.

        Args:
            table: Name in the ``public`` schema.
            column: The column to look at.

        Returns:
            ``True`` only when the database refuses the value as not in the enum.

        Raises:
            DatabaseUnavailableError: If the database could not answer.
        """
        try:
            self._client.table(table).select(column).eq(column, UNLISTED_ENUM_VALUE).limit(
                1
            ).execute()
        except APIError as error:
            code = str(error.code)
            if code == INVALID_ENUM_VALUE_CODE:
                return True
            if code in MISSING_OBJECT_CODES:
                return False
            raise _unavailable("probe", error) from error
        except (SupabaseException, httpx.HTTPError) as error:
            raise _unavailable("probe", error) from error
        return False

    def has_row(self, table: str, matches: Mapping[str, str]) -> bool:
        """Tell whether a table holds a row with all of the given values.

        Args:
            table: Name in the ``public`` schema.
            matches: Column names and the value each must hold.

        Returns:
            ``False`` when no row matches, or the table or a column is missing.

        Raises:
            DatabaseUnavailableError: If the database could not answer.
        """
        query = self._client.table(table).select(",".join(matches))
        for column, value in matches.items():
            query = query.eq(column, value)
        try:
            response = query.limit(1).execute()
        except APIError as error:
            if str(error.code) in MISSING_OBJECT_CODES:
                return False
            raise _unavailable("probe", error) from error
        except (SupabaseException, httpx.HTTPError) as error:
            raise _unavailable("probe", error) from error
        return bool(response.data)

    def owner_ids(self) -> tuple[str, ...]:
        """List the logins recorded as the dashboard owner.

        Returns:
            Their identifiers, empty when nobody is recorded yet.

        Raises:
            DatabaseUnavailableError: If the database could not answer.
        """
        response = self._call(
            lambda: self._client.table(_OWNER_TABLE).select(_OWNER_COLUMN).execute()
        )
        rows = cast("list[dict[str, object]]", response.data)
        return tuple(str(row[_OWNER_COLUMN]) for row in rows)

    def add_owner(self, user_id: str) -> None:
        """Record a login as the dashboard owner. Running it twice changes nothing.

        Args:
            user_id: The login's identifier in Supabase Auth.

        Raises:
            DatabaseUnavailableError: If the database could not answer.
        """
        self._call(
            lambda: (
                self._client.table(_OWNER_TABLE)
                .upsert([{_OWNER_COLUMN: user_id}], on_conflict=_OWNER_COLUMN)
                .execute()
            )
        )

    def find_user_id(self, email: str) -> str | None:
        """Find a login by its e-mail address.

        Args:
            email: The address, compared case-insensitively.

        Returns:
            The login's identifier, or ``None`` when there is none.

        Raises:
            SourceAuthError: If the key is not the secret one.
            DatabaseUnavailableError: If Supabase could not answer.
        """
        wanted = email.strip().lower()
        for page in range(1, AUTH_USERS_MAX_PAGES + 1):
            users = self._auth(
                lambda page=page: self._client.auth.admin.list_users(
                    page=page, per_page=AUTH_USERS_PAGE_SIZE
                )
            )
            for user in users:
                if (user.email or "").lower() == wanted:
                    return user.id
            if len(users) < AUTH_USERS_PAGE_SIZE:
                return None
        return None

    def user_email(self, user_id: str) -> str | None:
        """Read the e-mail address a login signs in with.

        Args:
            user_id: The login's identifier in Supabase Auth, as recorded for the owner.

        Returns:
            The address, or ``None`` when the login has none.

        Raises:
            SourceAuthError: If the key is not the secret one.
            DatabaseUnavailableError: If Supabase could not answer, or has no such login.
        """
        response = self._auth(lambda: self._client.auth.admin.get_user_by_id(user_id))
        return response.user.email or None

    def create_confirmed_user(self, email: str) -> str | None:
        """Create a login that can sign in by e-mailed link straight away.

        Args:
            email: The owner's address.

        Returns:
            The new login's identifier, or ``None`` when one already existed.

        Raises:
            SourceAuthError: If the key is not the secret one.
            DatabaseUnavailableError: If Supabase could not answer.
        """
        try:
            response = self._auth(
                lambda: self._client.auth.admin.create_user(
                    {"email": email.strip(), "email_confirm": True}
                )
            )
        except _ExistingUserError:
            return None
        return response.user.id

    def check_service_key(self) -> None:
        """Make one small call only the secret key may make.

        Raises:
            SourceAuthError: If the key is not the secret one.
            DatabaseUnavailableError: If Supabase could not answer.
        """
        self._auth(lambda: self._client.auth.admin.list_users(page=1, per_page=1))

    def save_daily_schedule(self, run_at: time, time_zone: str) -> None:
        """Write the daily time and its zone into the one settings row.

        Args:
            run_at: The daily run's time of day.
            time_zone: The IANA zone it is read in, already checked.

        Raises:
            DatabaseStructureMissingError: If the database lacks the daily time (0016).
            DatabaseUnavailableError: If the database could not answer.
        """
        row = {
            _SINGLETON_COLUMN: True,
            "time_zone": time_zone,
            "daily_run_time": run_at.strftime(_TIME_FORMAT),
        }
        self._structure_call(
            "daily_schedule",
            lambda: (
                self._client.table(_SETTINGS_TABLE)
                .upsert([row], on_conflict=_SINGLETON_COLUMN)
                .execute()
            ),
        )

    def save_daily_start(self, function_url: str, key: SecretStr) -> None:
        """Save the timer's address and key in Vault, and make sure the timer exists.

        Args:
            function_url: The function's scheduled path, where the timer calls.
            key: The shared key; it goes to the database function only.

        Raises:
            DatabaseStructureMissingError: If the database lacks the function (0016).
            DatabaseUnavailableError: If the database could not answer or refused.
        """
        arguments = {"function_url": function_url, "shared_key": key.get_secret_value()}
        self._structure_call(
            "daily_start", lambda: self._client.rpc(DAILY_START_SAVE_FUNCTION, arguments).execute()
        )

    def daily_start_status(self) -> DailyStartStatus:
        """Read whether the on-time morning start is switched on.

        Returns:
            Its state, as the database reports it.

        Raises:
            DatabaseStructureMissingError: If the database lacks the function (0016).
            DatabaseUnavailableError: If the database could not answer.
        """
        response = self._structure_call(
            "daily_start_status",
            lambda: self._client.rpc(DAILY_START_STATUS_FUNCTION, {}).execute(),
        )
        return _read_daily_start(response.data)

    def _structure_call[T](self, operation: str, action: Callable[[], T]) -> T:
        """Run one data call; a missing object means a structure file is not applied."""
        try:
            return action()
        except APIError as error:
            if str(error.code) in STRUCTURE_MISSING_CODES:
                message = "the database does not have the on-time morning start yet"
                raise DatabaseStructureMissingError(message) from error
            raise _unavailable(operation, error) from error
        except (SupabaseException, httpx.HTTPError) as error:
            raise _unavailable(operation, error) from error

    def _answers(self, action: Callable[[], object]) -> bool:
        """Run a probe; a "does not exist" answer means ``False``."""
        try:
            action()
        except APIError as error:
            if str(error.code) in MISSING_OBJECT_CODES:
                return False
            raise _unavailable("probe", error) from error
        except (SupabaseException, httpx.HTTPError) as error:
            raise _unavailable("probe", error) from error
        return True

    def _call[T](self, action: Callable[[], T]) -> T:
        """Run one data call, typing every failure."""
        try:
            return action()
        except (APIError, SupabaseException, httpx.HTTPError) as error:
            raise _unavailable("owner", error) from error

    def _auth[T](self, action: Callable[[], T]) -> T:
        """Run one auth admin call, typing every failure."""
        try:
            return action()
        except AuthError as error:
            status = getattr(error, "status", None)
            if error.code == EMAIL_EXISTS_CODE:
                raise _ExistingUserError from error
            if status in REFUSED_KEY_STATUSES:
                message = "Supabase refused the secret key"
                raise SourceAuthError(message) from error
            raise _unavailable("auth", error) from error
        except httpx.HTTPError as error:
            raise _unavailable("auth", error) from error


def _read_daily_start(data: object) -> DailyStartStatus:
    """Read the status the database function returns, refusing any other shape."""
    if not isinstance(data, dict):
        _log.error("supabase_admin_failed", operation="daily_start_status", error_type="shape")
        message = "Supabase answered the daily_start_status request with something unexpected"
        raise DatabaseUnavailableError(message)
    row = cast("dict[str, Any]", data)
    run_at, zone, last = row.get("daily_run_time"), row.get("time_zone"), row.get("last_started_on")
    return DailyStartStatus(
        job_scheduled=row.get("job_scheduled") is True,
        switched_on=row.get("switched_on") is True,
        run_at=time.fromisoformat(run_at) if isinstance(run_at, str) else None,
        time_zone=zone if isinstance(zone, str) else None,
        last_started_on=date.fromisoformat(last) if isinstance(last, str) else None,
    )


class _ExistingUserError(Exception):
    """Internal signal: the login to create is already there."""


def _unavailable(operation: str, error: Exception) -> DatabaseUnavailableError:
    """Log one clean line and build the typed error."""
    _log.error("supabase_admin_failed", operation=operation, error_type=type(error).__name__)
    message = f"Supabase did not answer the {operation} request"
    return DatabaseUnavailableError(message)
