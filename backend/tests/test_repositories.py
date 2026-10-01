"""Repositories read and write through the query builder, and map failures."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

from tests.conftest import SERVER_ROW_CAP, FakeSupabaseClient, as_client
from tracker.domain.enums import Channel, Direction, Relevance
from tracker.domain.models import Conversation, Message, Organisation, Person, PersonIdentity
from tracker.repositories import Repositories
from tracker.repositories.organisations import OrganisationRepository
from tracker.shared.constants.collection import DATABASE_BATCH_SIZE
from tracker.shared.errors import DatabaseUnavailableError, ValidationFailedError


def test_bulk_upsert_writes_and_reads_back(repositories: Repositories) -> None:
    organisation = Organisation(name="Northwind Robotics", email_domain="northwind.example")

    written = repositories.organisations.bulk_upsert([organisation])

    assert [record.id for record in written] == [organisation.id]
    assert repositories.organisations.get(organisation.id) is not None


def test_bulk_upsert_of_nothing_touches_the_database(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
) -> None:
    assert repositories.organisations.bulk_upsert([]) == []
    assert fake_client.executed == []


def test_running_a_write_twice_creates_no_duplicate(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
) -> None:
    identity = PersonIdentity(
        person_id=uuid4(),
        channel=Channel.EMAIL,
        identifier="anna@example.com",
    )

    repositories.person_identities.bulk_upsert([identity])
    repositories.person_identities.bulk_upsert([identity])

    assert len(fake_client.tables["person_identities"]) == 1


def test_natural_keys_match_the_database_contract() -> None:
    assert OrganisationRepository.conflict_columns == ("id",)


def test_get_returns_none_when_the_row_is_absent(repositories: Repositories) -> None:
    assert repositories.people.get(uuid4()) is None


def test_lookup_by_natural_key(repositories: Repositories) -> None:
    conversation = Conversation(channel=Channel.LINKEDIN, source_conversation_id="thread-9")
    repositories.conversations.bulk_upsert([conversation])

    found = repositories.conversations.find_by_source(Channel.LINKEDIN, "thread-9")

    assert found is not None
    assert found.id == conversation.id


def test_list_by_relevance_filters(repositories: Repositories) -> None:
    relevant = Person(full_name="Anna Vermeer", relevance=Relevance.RELEVANT)
    noise = Person(full_name="Newsletter Robot", relevance=Relevance.NOISE)
    repositories.people.bulk_upsert([relevant, noise])

    found = repositories.people.list_by_relevance(Relevance.RELEVANT)

    assert [person.full_name for person in found] == ["Anna Vermeer"]


def test_delete_by_ids_removes_only_those_rows(repositories: Repositories) -> None:
    kept = Organisation(name="Kept")
    removed = Organisation(name="Removed")
    repositories.organisations.bulk_upsert([kept, removed])

    deleted = repositories.organisations.delete_by_ids([removed.id])

    assert deleted == 1
    assert repositories.organisations.get(kept.id) is not None
    assert repositories.organisations.get(removed.id) is None


def test_messages_are_read_newest_first(repositories: Repositories) -> None:
    conversation_id = uuid4()
    older = Message(
        conversation_id=conversation_id,
        source_message_id="m1",
        direction=Direction.OUTBOUND,
        sent_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    newer = Message(
        conversation_id=conversation_id,
        source_message_id="m2",
        direction=Direction.INBOUND,
        sent_at=datetime(2026, 9, 15, tzinfo=UTC),
    )
    repositories.messages.bulk_upsert([older, newer])

    found = repositories.messages.list_for_conversation(conversation_id)

    assert [message.source_message_id for message in found] == ["m2", "m1"]


def test_an_unreasonable_page_size_is_refused(repositories: Repositories) -> None:
    with pytest.raises(ValidationFailedError, match="page size"):
        repositories.people.list(limit=5000)


def test_a_negative_offset_is_refused(repositories: Repositories) -> None:
    with pytest.raises(ValidationFailedError, match="offset"):
        repositories.people.list(offset=-1)


def test_a_transport_failure_becomes_a_typed_error() -> None:
    class BrokenClient(FakeSupabaseClient):
        def table(self, table_name: str) -> object:  # type: ignore[override]
            raise httpx.ConnectError("no route to host")

    repository = OrganisationRepository(as_client(BrokenClient()))

    with pytest.raises(DatabaseUnavailableError, match="organisations"):
        repository.list()


def test_the_typed_error_does_not_leak_the_driver_message() -> None:
    class BrokenClient(FakeSupabaseClient):
        def table(self, table_name: str) -> object:  # type: ignore[override]
            raise httpx.ConnectError("secret-looking internal detail")

    repository = OrganisationRepository(as_client(BrokenClient()))

    with pytest.raises(DatabaseUnavailableError) as raised:
        repository.list()

    assert "secret-looking internal detail" not in raised.value.message


def test_a_long_id_filter_is_split_into_several_requests(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
) -> None:
    """A filter longer than one batch would overflow the query string.

    Supabase receives ``in`` filters in the URL, so asking for several hundred
    identifiers in one request is refused. Reading them back must therefore
    return every row while sending more than one request.
    """
    people = [Person(full_name=f"Person {index}") for index in range(DATABASE_BATCH_SIZE + 5)]
    repositories.people.bulk_upsert(people)
    fake_client.executed.clear()

    found = repositories.people.list_by_ids([person.id for person in people])

    assert {person.id for person in found} == {person.id for person in people}
    reads = [entry for entry in fake_client.executed if entry == ("people", "select")]
    assert len(reads) > 1


def test_a_long_delete_filter_is_split_too(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
) -> None:
    people = [Person(full_name=f"Person {index}") for index in range(DATABASE_BATCH_SIZE + 5)]
    repositories.people.bulk_upsert(people)
    fake_client.executed.clear()

    deleted = repositories.people.delete_by_ids([person.id for person in people])

    assert deleted == len(people)
    assert repositories.people.list_by_ids([person.id for person in people]) == []


def test_more_rows_than_one_answer_can_hold_are_all_returned(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
) -> None:
    """Supabase truncates a large answer silently, so the read must page.

    Asking for every row in one request comes back capped, with HTTP 200 and no
    warning, which looks exactly like a complete answer.
    """
    person_id = uuid4()
    conversation = Conversation(
        person_id=person_id,
        channel=Channel.EMAIL,
        source_conversation_id="thread-1",
        relevance=Relevance.RELEVANT,
    )
    repositories.conversations.bulk_upsert([conversation])
    messages = [
        Message(
            conversation_id=conversation.id,
            source_message_id=f"m{index}",
            direction=Direction.INBOUND,
            sent_at=datetime(2026, 9, 1, tzinfo=UTC),
        )
        for index in range(SERVER_ROW_CAP + 25)
    ]
    repositories.messages.bulk_upsert(messages)
    fake_client.executed.clear()

    found = repositories.messages.list_for_conversations([conversation.id])

    assert len(found) == SERVER_ROW_CAP + 25


def test_the_same_natural_key_twice_in_one_batch_does_not_lose_the_batch(
    repositories: Repositories,
) -> None:
    """Postgres refuses an upsert that would touch one row twice — and refuses
    the whole statement, so a single duplicate would take every other record
    with it. LinkedIn began serving its whole archive twice on 2026-09-19.
    """
    person_id = uuid4()
    conversation = Conversation(
        person_id=person_id,
        channel=Channel.EMAIL,
        source_conversation_id="thread-1",
        relevance=Relevance.RELEVANT,
    )
    repositories.conversations.bulk_upsert([conversation])
    same = [
        Message(
            conversation_id=conversation.id,
            source_message_id="m-1",
            direction=Direction.INBOUND,
            sent_at=datetime(2026, 9, 1, tzinfo=UTC),
            body=text,
        )
        for text in ("first copy", "second copy")
    ]
    other = Message(
        conversation_id=conversation.id,
        source_message_id="m-2",
        direction=Direction.INBOUND,
        sent_at=datetime(2026, 9, 2, tzinfo=UTC),
        body="kept",
    )

    written = repositories.messages.bulk_upsert([*same, other])

    stored = repositories.messages.list_for_conversations([conversation.id])
    assert len(written) == 2
    assert {message.source_message_id for message in stored} == {"m-1", "m-2"}
    assert next(m for m in stored if m.source_message_id == "m-1").body == "second copy"
