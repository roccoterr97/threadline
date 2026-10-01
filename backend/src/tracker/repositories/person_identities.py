"""Data access for ``person_identities``."""

from __future__ import annotations

from collections.abc import Sequence
from itertools import batched
from typing import ClassVar
from uuid import UUID

from supabase import Client

from tracker.domain.enums import Channel
from tracker.domain.models import PersonIdentity
from tracker.repositories.base import ALL_COLUMNS, SupabaseRepository
from tracker.shared.constants.collection import DATABASE_BATCH_SIZE


class PersonIdentityRepository(SupabaseRepository[PersonIdentity]):
    """The addresses a person can be reached at, one row per channel."""

    table_name: ClassVar[str] = "person_identities"
    conflict_columns: ClassVar[tuple[str, ...]] = ("channel", "identifier")

    def __init__(self, client: Client) -> None:
        """Bind the repository to the shared Supabase client."""
        super().__init__(client, PersonIdentity)

    def find_by_identifier(self, channel: Channel, identifier: str) -> PersonIdentity | None:
        """Look an identity up by its natural key.

        Args:
            channel: Where the identifier is used.
            identifier: A LinkedIn profile link or a lower-case e-mail address.

        Returns:
            The identity, or ``None`` when it is unknown.
        """
        value = identifier.strip().lower() if channel is Channel.EMAIL else identifier.strip()
        rows = self._run(
            lambda: self._table()
            .select(ALL_COLUMNS)
            .eq("channel", channel.value)
            .eq("identifier", value)
            .limit(1)
            .execute(),
            "find_by_identifier",
        )
        return self._first(rows)

    def list_by_identifiers(
        self,
        channel: Channel,
        identifiers: Sequence[str],
    ) -> list[PersonIdentity]:
        """Fetch several identities of one channel in one request.

        The matcher uses this to learn, in a single round trip, which of the
        addresses a run discovered already belong to somebody.

        Args:
            channel: Where the identifiers are used.
            identifiers: The values to look up. An empty sequence is a no-op.

        Returns:
            The identities that are already stored.
        """
        wanted = [
            value.strip().lower() if channel is Channel.EMAIL else value.strip()
            for value in identifiers
            if value.strip()
        ]
        found: list[PersonIdentity] = []
        for batch in batched(wanted, DATABASE_BATCH_SIZE):
            rows = self._select_every(
                lambda values=list(batch): self._table()
                .select(ALL_COLUMNS)
                .eq("channel", channel.value)
                .in_("identifier", values),
                "list_by_identifiers",
            )
            found.extend(self._to_models(rows))
        return found

    def list_for_person(self, person_id: UUID) -> list[PersonIdentity]:
        """List every identity belonging to one person.

        Args:
            person_id: The person's identifier.

        Returns:
            The person's identities.
        """
        rows = self._select_every(
            lambda: self._table().select(ALL_COLUMNS).eq("person_id", str(person_id)),
            "list_for_person",
        )
        return self._to_models(rows)
