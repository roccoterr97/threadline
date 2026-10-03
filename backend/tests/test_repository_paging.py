"""Reading every matching row costs one request per page, and still reads them all.

The first request asks the database how many rows match. That total, never the
length of a page, decides when the reading stops: Supabase caps an answer
silently, so a short page proves nothing.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import httpx
import pytest
import respx
from postgrest import CountMethod, SyncPostgrestClient
from structlog.testing import capture_logs
from supabase import Client

from tests.conftest import SERVER_ROW_CAP, FakeQuery, FakeSupabaseClient, as_client
from tracker.domain.enums import Direction, ReviewAnswer, ReviewKind
from tracker.domain.models import Message, Person, Record, ReviewItem
from tracker.repositories import Repositories, build_repositories
from tracker.repositories.people import PersonRepository
from tracker.shared.constants.pagination import MAX_PAGE_SIZE

#: A server cap far below the page size the repositories ask for.
LOWERED_CAP = 10

FIRST_DAY = datetime(2026, 9, 1, tzinfo=UTC)

REST_URL = "https://sample-project.supabase.co/rest/v1"
PEOPLE_URL = f"{REST_URL}/people"

#: Stores some rows and returns the call that reads every one of them back.
type Store = Callable[[Repositories, int], Callable[[], Sequence[Record]]]


def _store_thread(repositories: Repositories, size: int) -> Callable[[], Sequence[Record]]:
    """Store one thread of ``size`` messages; the read filters on that thread."""
    conversation_id = uuid4()
    repositories.messages.bulk_upsert(
        [
            Message(
                conversation_id=conversation_id,
                source_message_id=f"m{index}",
                direction=Direction.INBOUND,
                sent_at=FIRST_DAY,
            )
            for index in range(size)
        ]
    )
    return lambda: repositories.messages.list_for_conversations([conversation_id])


def _store_people(repositories: Repositories, size: int) -> Callable[[], Sequence[Record]]:
    """Store ``size`` people; the read takes the whole table."""
    repositories.people.bulk_upsert([Person(full_name=f"Person {index}") for index in range(size)])
    return repositories.people.list_every


#: The two ways every row is read: a filtered read paged by primary key, and a
#: whole table paged in the order ``list`` returns it.
BOTH_READS = [
    pytest.param("messages", _store_thread, id="filtered read"),
    pytest.param("people", _store_people, id="whole table"),
]


class VanishingRows(FakeSupabaseClient):
    """A database whose rows somebody else deletes once one page has been read."""

    def table(self, table_name: str) -> FakeQuery:
        if (table_name, "select") in self.executed:
            self.tables[table_name].clear()
        return super().table(table_name)


def _stamped(record: Record, created_at: datetime) -> dict[str, Any]:
    """A row as the database stores it, creation time included."""
    return {**record.to_row(), "created_at": created_at.isoformat()}


def _walk_pages[RowT](read_page: Callable[..., list[RowT]]) -> list[RowT]:
    """Read a paged ``list`` method the way callers did before ``list_every``.

    One full page after another until one comes back empty. It is the reference
    the new read must agree with, row for row and in the same order.
    """
    rows: list[RowT] = []
    while True:
        page = read_page(limit=MAX_PAGE_SIZE, offset=len(rows))
        if not page:
            return rows
        rows.extend(page)


def _ids(rows: Sequence[Record]) -> list[UUID]:
    return [row.id for row in rows]


@pytest.mark.parametrize(("table", "store"), BOTH_READS)
def test_a_read_that_fits_in_one_answer_costs_one_request(
    table: str,
    store: Store,
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
) -> None:
    read = store(repositories, 3)
    fake_client.executed.clear()

    found = read()

    assert len(found) == 3
    assert fake_client.executed == [(table, "select")]


@pytest.mark.parametrize(("table", "store"), BOTH_READS)
def test_a_read_of_two_pages_costs_two_requests_and_asks_for_the_total_once(
    table: str,
    store: Store,
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
) -> None:
    read = store(repositories, SERVER_ROW_CAP + 25)
    fake_client.executed.clear()

    found = read()

    assert len({row.id for row in found}) == SERVER_ROW_CAP + 25
    assert fake_client.executed == [(table, "select")] * 2
    assert fake_client.totals_asked == [table]


@pytest.mark.parametrize(("table", "store"), BOTH_READS)
def test_rows_that_fill_the_last_page_exactly_need_no_further_request(
    table: str,
    store: Store,
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
) -> None:
    fake_client.row_cap = LOWERED_CAP
    read = store(repositories, 2 * LOWERED_CAP)
    fake_client.executed.clear()

    found = read()

    assert len({row.id for row in found}) == 2 * LOWERED_CAP
    assert fake_client.executed == [(table, "select")] * 2


@pytest.mark.parametrize(("table", "store"), BOTH_READS)
def test_a_lowered_server_cap_still_reads_every_row(
    table: str,
    store: Store,
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
) -> None:
    """Every page comes back shorter than asked for, and none of them is the last.

    The total decides when to stop, so the read carries on past each short page
    and ends with the one that completes the count.
    """
    fake_client.row_cap = LOWERED_CAP
    read = store(repositories, 2 * LOWERED_CAP + 5)
    fake_client.executed.clear()

    found = read()

    assert len({row.id for row in found}) == 2 * LOWERED_CAP + 5
    assert fake_client.executed == [(table, "select")] * 3


@pytest.mark.parametrize(("table", "store"), BOTH_READS)
def test_an_answer_without_a_total_is_read_until_a_page_comes_back_empty(
    table: str,
    store: Store,
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
) -> None:
    """With nothing to count up to, only an empty page proves the end."""
    fake_client.row_cap = LOWERED_CAP
    fake_client.reports_totals = False
    read = store(repositories, 2 * LOWERED_CAP + 5)
    fake_client.executed.clear()

    found = read()

    assert len({row.id for row in found}) == 2 * LOWERED_CAP + 5
    assert fake_client.executed == [(table, "select")] * 4


@pytest.mark.parametrize(("table", "store"), BOTH_READS)
def test_rows_that_disappear_while_reading_end_the_read(table: str, store: Store) -> None:
    """The total is never reached, and the read must not wait for it."""
    client = VanishingRows()
    client.row_cap = LOWERED_CAP
    read = store(build_repositories(as_client(client)), 2 * LOWERED_CAP + 5)

    found = read()

    assert len(found) == LOWERED_CAP
    assert client.executed.count((table, "select")) == 2


@pytest.mark.parametrize(("table", "store"), BOTH_READS)
@pytest.mark.parametrize("reports_totals", [True, False])
def test_nothing_to_read_costs_one_request(
    table: str,
    store: Store,
    reports_totals: bool,
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
) -> None:
    fake_client.reports_totals = reports_totals
    read = store(repositories, 0)
    fake_client.executed.clear()

    assert read() == []
    assert fake_client.executed == [(table, "select")]


def test_a_whole_table_comes_back_in_the_order_its_pages_had(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
) -> None:
    """Callers keep the first of several candidates, so the order is a contract.

    Three people share each creation time, as the rows of one write do.
    """
    fake_client.row_cap = LOWERED_CAP
    fake_client.tables["people"] = [
        _stamped(Person(full_name=f"Person {index}"), FIRST_DAY + timedelta(hours=index // 3))
        for index in range(2 * LOWERED_CAP + 5)
    ]

    found = repositories.people.list_every()

    assert _ids(found) == _ids(_walk_pages(repositories.people.list))
    assert found[0].created_at == FIRST_DAY + timedelta(hours=8)
    assert found[-1].created_at == FIRST_DAY


def test_every_unanswered_question_comes_back_in_the_order_its_pages_had(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
) -> None:
    fake_client.row_cap = LOWERED_CAP
    fake_client.tables["review_items"] = [
        _stamped(
            ReviewItem(
                kind=ReviewKind.SAME_PERSON,
                question=f"Question {index}",
                answer=ReviewAnswer.YES if index % 4 == 0 else None,
            ),
            FIRST_DAY + timedelta(hours=index // 3),
        )
        for index in range(3 * LOWERED_CAP)
    ]
    fake_client.executed.clear()

    found = repositories.review_items.list_every_unanswered()

    assert fake_client.executed == [("review_items", "select")] * 3
    assert all(item.answer is None for item in found)
    assert _ids(found) == _ids(_walk_pages(repositories.review_items.list_unanswered))
    assert len(found) == 22


def test_one_page_of_a_list_asks_for_no_total(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
) -> None:
    """Counting is extra work for the database; a single page has no use for it."""
    repositories.people.bulk_upsert([Person(full_name="Anna Vermeer")])

    repositories.people.list()

    assert fake_client.totals_asked == []


def test_the_stand_in_reports_a_total_only_when_asked_for_one(
    fake_client: FakeSupabaseClient,
) -> None:
    """The real client fills ``count`` from the answer only for a counted request.

    The total is of every matching row: neither the page asked for nor the
    server's cap changes it.
    """
    fake_client.row_cap = LOWERED_CAP
    fake_client.tables["people"] = [{"id": str(uuid4())} for _ in range(25)]

    plain = fake_client.table("people").select("*").range(0, 4).execute()
    counted = fake_client.table("people").select("*", count=CountMethod.exact).range(0, 4).execute()
    fake_client.reports_totals = False
    silent = fake_client.table("people").select("*", count=CountMethod.exact).range(0, 4).execute()

    assert (len(plain.data), plain.count) == (5, None)
    assert (len(counted.data), counted.count) == (5, 25)
    assert (len(silent.data), silent.count) == (5, None)


def _serve_people(size: int, total: str | None) -> respx.Route:
    """Answer the people table over a mocked transport, two rows at a time.

    Args:
        size: How many people the made-up table holds.
        total: What follows the slash of ``Content-Range`` in the answer to a
            counted request, or ``None`` to leave the header out.

    Returns:
        The route, whose calls are the requests the installed client sent.
    """
    people = [{"id": str(uuid4()), "full_name": f"Person {index}"} for index in range(size)]

    def answer(request: httpx.Request) -> httpx.Response:
        start = int(request.url.params["offset"])
        page = people[start : start + 2]
        span = f"{start}-{start + len(page) - 1}" if page else "*"
        counted = "count=exact" in request.headers.get("prefer", "")
        headers = {"Content-Range": f"{span}/{total if counted else '*'}"}
        return httpx.Response(200, json=page, headers={} if total is None else headers)

    return respx.get(PEOPLE_URL).mock(side_effect=answer)


def _real_people() -> PersonRepository:
    """The people repository on the installed query builder.

    The Supabase client hands every ``table`` call to this PostgREST client, so
    it is the part that sends the preference and reads the total.
    """
    return PersonRepository(cast("Client", SyncPostgrestClient(REST_URL)))


def _preferences(route: respx.Route) -> list[str | None]:
    return [call.request.headers.get("prefer") for call in route.calls]


def test_the_installed_client_asks_for_the_total_with_the_first_page_only() -> None:
    """The stand-in is only as honest as it was written, so this one goes
    through the installed client: the preference it sends, and the total it
    reads back from ``Content-Range``.
    """
    with respx.mock:
        route = _serve_people(3, total="3")

        found = _real_people().list_every()

    assert len(found) == 3
    assert _preferences(route) == ["count=exact", None]
    assert [call.request.url.params["offset"] for call in route.calls] == ["0", "2"]


def test_the_installed_client_reads_a_total_of_zero() -> None:
    with respx.mock:
        route = _serve_people(0, total="0")

        found = _real_people().list_every()

    assert found == []
    assert route.call_count == 1


def test_an_answer_with_no_content_range_is_read_until_an_empty_page() -> None:
    with respx.mock:
        route = _serve_people(3, total=None)

        found = _real_people().list_every()

    assert len(found) == 3
    assert _preferences(route) == ["count=exact", None, None]


def test_a_total_the_installed_client_cannot_read_does_not_fail_the_read() -> None:
    """PostgREST writes ``*`` for "not counted", and the client raises on it.

    The first page is asked for again without a total, and the reading goes on
    until an empty page, as it did before totals were asked for.
    """
    with respx.mock, capture_logs() as logs:
        route = _serve_people(3, total="*")

        found = _real_people().list_every()

    assert len(found) == 3
    assert _preferences(route) == ["count=exact", None, None, None]
    assert [entry["event"] for entry in logs] == ["database_total_unreadable"]
