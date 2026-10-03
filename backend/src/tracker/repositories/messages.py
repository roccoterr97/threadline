"""Data access for ``messages``."""

from __future__ import annotations

from collections.abc import Sequence
from itertools import batched
from typing import ClassVar, Final
from uuid import UUID

from supabase import Client

from tracker.domain.models import Message
from tracker.repositories.base import ALL_COLUMNS, SupabaseRepository
from tracker.shared.constants.collection import DATABASE_BATCH_SIZE
from tracker.shared.constants.pagination import DEFAULT_PAGE_SIZE

#: The only column a counting query needs.
CONVERSATION_ID_COLUMN: Final[str] = "conversation_id"

#: Who sent a message; read on its own when only the participants matter.
SENDER_COLUMN: Final[str] = "sender_identifier"


class MessageRepository(SupabaseRepository[Message]):
    """Messages, one row per message per thread."""

    table_name: ClassVar[str] = "messages"
    conflict_columns: ClassVar[tuple[str, ...]] = ("conversation_id", "source_message_id")
    order_column: ClassVar[str] = "sent_at"

    def __init__(self, client: Client) -> None:
        """Bind the repository to the shared Supabase client."""
        super().__init__(client, Message)

    def list_for_conversation(
        self,
        conversation_id: UUID,
        *,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> list[Message]:
        """List the messages of one thread, newest first.

        Args:
            conversation_id: The thread's identifier.
            limit: How many rows to return.
            offset: How many rows to skip.

        Returns:
            The page of messages.
        """
        self._check_page(limit, offset)
        return self._select_page(
            lambda: self._table().select(ALL_COLUMNS).eq("conversation_id", str(conversation_id)),
            limit=limit,
            offset=offset,
        )

    def count_by_conversation(self, conversation_ids: Sequence[UUID]) -> dict[UUID, int]:
        """Count the messages of several threads without reading their text.

        Only the ``conversation_id`` column is selected, so no body ever leaves
        the database for a job that just needs a number.

        Args:
            conversation_ids: The threads to count. An empty sequence is a no-op.

        Returns:
            How many messages each thread holds; threads with none are absent.
        """
        counts: dict[UUID, int] = {}
        for batch in batched(conversation_ids, DATABASE_BATCH_SIZE):
            rows = self._select_every(
                lambda query, values=[str(item) for item in batch]: query.in_(
                    CONVERSATION_ID_COLUMN, values
                ),
                "count_by_conversation",
                columns=f"id,{CONVERSATION_ID_COLUMN}",
            )
            for row in rows:
                key = UUID(str(row[CONVERSATION_ID_COLUMN]))
                counts[key] = counts.get(key, 0) + 1
        return counts

    def list_senders(self, conversation_ids: Sequence[UUID]) -> list[tuple[UUID, str]]:
        """Say who sent something in several threads, without reading any text.

        Only the thread and sender columns are selected, so no body leaves the
        database for a job that only needs to know who took part.

        Args:
            conversation_ids: The threads to read. An empty sequence is a no-op.

        Returns:
            One ``(thread, sender)`` pair per message that names its sender.
        """
        senders: list[tuple[UUID, str]] = []
        for batch in batched(conversation_ids, DATABASE_BATCH_SIZE):
            rows = self._select_every(
                lambda query, values=[str(item) for item in batch]: query.in_(
                    CONVERSATION_ID_COLUMN, values
                ),
                "list_senders",
                columns=f"id,{CONVERSATION_ID_COLUMN},{SENDER_COLUMN}",
            )
            senders.extend(
                (UUID(str(row[CONVERSATION_ID_COLUMN])), str(row[SENDER_COLUMN]))
                for row in rows
                if row.get(SENDER_COLUMN)
            )
        return senders

    def list_threads_from(self, senders: Sequence[str]) -> list[tuple[UUID, str]]:
        """Find the threads some addresses wrote in, without reading any text.

        Args:
            senders: Sender identifiers, as stored. An empty sequence is a no-op.

        Returns:
            One ``(thread, sender)`` pair per message those addresses sent.
        """
        found: list[tuple[UUID, str]] = []
        for batch in batched(senders, DATABASE_BATCH_SIZE):
            rows = self._select_every(
                lambda query, values=list(batch): query.in_(SENDER_COLUMN, values),
                "list_threads_from",
                columns=f"id,{CONVERSATION_ID_COLUMN},{SENDER_COLUMN}",
            )
            found.extend(
                (UUID(str(row[CONVERSATION_ID_COLUMN])), str(row[SENDER_COLUMN])) for row in rows
            )
        return found

    def list_for_conversations(self, conversation_ids: Sequence[UUID]) -> list[Message]:
        """Fetch the messages of several threads in one request.

        Args:
            conversation_ids: The threads to read. An empty sequence is a no-op.

        Returns:
            The messages, newest first.
        """
        messages = self._select_in(
            CONVERSATION_ID_COLUMN, conversation_ids, "list_for_conversations"
        )
        # The pages come back ordered by primary key, so the joined result is
        # sorted here to keep the documented newest-first contract.
        messages.sort(key=lambda message: message.sent_at, reverse=True)
        return messages
