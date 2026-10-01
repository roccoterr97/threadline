"""Data access for ``conversations``."""

from __future__ import annotations

from collections.abc import Sequence
from itertools import batched
from typing import ClassVar
from uuid import UUID

from supabase import Client

from tracker.domain.enums import Channel
from tracker.domain.models import Conversation
from tracker.repositories.base import ALL_COLUMNS, SupabaseRepository
from tracker.shared.constants.collection import DATABASE_BATCH_SIZE


class ConversationRepository(SupabaseRepository[Conversation]):
    """Threads, one row per thread per channel."""

    table_name: ClassVar[str] = "conversations"
    conflict_columns: ClassVar[tuple[str, ...]] = ("channel", "source_conversation_id")

    def __init__(self, client: Client) -> None:
        """Bind the repository to the shared Supabase client."""
        super().__init__(client, Conversation)

    def find_by_source(self, channel: Channel, source_conversation_id: str) -> Conversation | None:
        """Look a thread up by the identifier its source gave it.

        Args:
            channel: Where the thread lives.
            source_conversation_id: The identifier LinkedIn or the mailbox uses.

        Returns:
            The conversation, or ``None`` when it has not been collected yet.
        """
        rows = self._run(
            lambda: self._table()
            .select(ALL_COLUMNS)
            .eq("channel", channel.value)
            .eq("source_conversation_id", source_conversation_id)
            .limit(1)
            .execute(),
            "find_by_source",
        )
        return self._first(rows)

    def list_by_sources(
        self,
        channel: Channel,
        source_conversation_ids: Sequence[str],
    ) -> list[Conversation]:
        """Fetch several threads by the identifiers their source gave them.

        The collectors use this to reuse the primary key a thread already has,
        so a second run updates the same row instead of creating a new one.

        Args:
            channel: Where the threads live.
            source_conversation_ids: The source identifiers to look up. An empty
                sequence is a no-op.

        Returns:
            The conversations that are already stored.
        """
        found: list[Conversation] = []
        for batch in batched(source_conversation_ids, DATABASE_BATCH_SIZE):
            rows = self._select_every(
                lambda values=list(batch): self._table()
                .select(ALL_COLUMNS)
                .eq("channel", channel.value)
                .in_("source_conversation_id", values),
                "list_by_sources",
            )
            found.extend(self._to_models(rows))
        return found

    def list_for_people(self, person_ids: Sequence[UUID]) -> list[Conversation]:
        """Fetch the threads of several people in one request.

        Args:
            person_ids: The people to read. An empty sequence is a no-op.

        Returns:
            The conversations, most recently active first.
        """
        found = self._select_in("person_id", person_ids, "list_for_people")
        # Each batch is ordered on its own, so the merged list is sorted here.
        # Threads that never carried a message sort last.
        found.sort(
            key=lambda conversation: (
                conversation.last_message_at is not None,
                conversation.last_message_at,
            ),
            reverse=True,
        )
        return found

    def list_for_person(self, person_id: UUID) -> list[Conversation]:
        """List every thread linked to one person.

        Args:
            person_id: The person's identifier.

        Returns:
            The person's conversations, most recently active first.
        """
        rows = self._select_every(
            lambda: self._table().select(ALL_COLUMNS).eq("person_id", str(person_id)),
            "list_for_person",
        )
        found = self._to_models(rows)
        found.sort(
            key=lambda conversation: (
                conversation.last_message_at is not None,
                conversation.last_message_at,
            ),
            reverse=True,
        )
        return found
