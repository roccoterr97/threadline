"""Data access for ``person_notes``."""

from __future__ import annotations

from typing import ClassVar, Final
from uuid import UUID

from postgrest import APIError, ReturnMethod
from postgrest.base_request_builder import APIResponse
from supabase import Client

from tracker.domain.models import PersonNote
from tracker.repositories.base import SupabaseReader
from tracker.shared.logging import get_logger

#: Error codes the data API answers when a table does not exist yet: Postgres's
#: own, and the one Supabase's API gives for a table it has never seen.
MISSING_TABLE_CODES: Final[frozenset[str]] = frozenset({"42P01", "PGRST205"})

_log = get_logger(__name__)


class _TableMissingError(Exception):
    """Internal signal: the notes table has not been created yet."""


class PersonNoteRepository(SupabaseReader[PersonNote]):
    """The notes the owner types on the dashboard.

    The jobs never write a note and never read its text. They only keep a note
    with its person when two records of that person are joined.
    """

    table_name: ClassVar[str] = "person_notes"

    def __init__(self, client: Client) -> None:
        """Bind the repository to the shared Supabase client."""
        super().__init__(client, PersonNote)

    def move_to_person(self, from_person_id: UUID, to_person_id: UUID) -> None:
        """Point every note of one person at another, in one request.

        Nothing is read back, so no note's text passes through Python. Running
        it twice changes nothing more. A database that does not have the table
        yet (migration 0016 not applied) holds no note, so there is nothing to
        move and nothing to report as a failure.

        Args:
            from_person_id: The person whose notes move.
            to_person_id: The person who gets them.

        Raises:
            DatabaseUnavailableError: If the database could not be reached or
                refused the request for any other reason.
        """
        try:
            self._respond(lambda: self._move(from_person_id, to_person_id), "move_to_person")
        except _TableMissingError:
            _log.info("person_notes_table_missing", operation="move_to_person")

    def _move(self, from_person_id: UUID, to_person_id: UUID) -> APIResponse:
        """Send the update, telling a missing table apart from a real refusal."""
        try:
            return (
                self._table()
                .update({"person_id": str(to_person_id)}, returning=ReturnMethod.minimal)
                .eq("person_id", str(from_person_id))
                .execute()
            )
        except APIError as error:
            if str(error.code) in MISSING_TABLE_CODES:
                raise _TableMissingError from error
            raise
