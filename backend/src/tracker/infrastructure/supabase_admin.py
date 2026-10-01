"""Set-up and diagnosis work on Supabase that the repositories do not do.

The repositories read and write Threadline's own rows. Setting up a project
needs a few other things: seeing whether a table, column or value exists yet,
finding or creating the dashboard login, and recording who owns the dashboard.
All of it goes through the same service-key client, over HTTPS.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final, cast

import httpx
from postgrest import APIError
from supabase import Client, SupabaseException
from supabase_auth.errors import AuthError

from tracker.shared.constants.setup import AUTH_USERS_MAX_PAGES, AUTH_USERS_PAGE_SIZE
from tracker.shared.errors import DatabaseUnavailableError, SourceAuthError
from tracker.shared.logging import get_logger

#: Error codes the data API answers when a table, a column or an enum value
#: does not exist yet — "not set up", as opposed to "broken".
MISSING_OBJECT_CODES: Final[frozenset[str]] = frozenset(
    {"42P01", "42703", "22P02", "PGRST200", "PGRST204", "PGRST205"}
)

#: Auth server code for "a user with this address already exists".
EMAIL_EXISTS_CODE: Final[str] = "email_exists"

#: Auth server statuses meaning the key is not the secret one.
REFUSED_KEY_STATUSES: Final[frozenset[int]] = frozenset({401, 403})

_OWNER_TABLE: Final[str] = "app_owner"
_OWNER_COLUMN: Final[str] = "user_id"

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


class _ExistingUserError(Exception):
    """Internal signal: the login to create is already there."""


def _unavailable(operation: str, error: Exception) -> DatabaseUnavailableError:
    """Log one clean line and build the typed error."""
    _log.error("supabase_admin_failed", operation=operation, error_type=type(error).__name__)
    message = f"Supabase did not answer the {operation} request"
    return DatabaseUnavailableError(message)
