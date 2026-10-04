"""The owner's hand-typed notes stay with their person, and stay on the dashboard.

The jobs do one thing with ``person_notes``: when two records of one person are
joined, the notes of the record that goes move to the one that stays. They
never read a note's text, so it reaches neither the assessment nor the summary.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from postgrest import APIError

from tests.assessment_world import make_message, make_person, make_thread, moment, seed
from tests.conftest import FakeQuery, FakeSupabaseClient, as_client
from tests.summary_world import NOW, TODAYS_RUN, sample_client, sample_data
from tracker.domain.enums import Direction, ReviewAnswer, ReviewKind
from tracker.domain.models import Person, PersonNote, ReviewItem
from tracker.repositories import Repositories, build_repositories
from tracker.repositories import base as repository_base
from tracker.services.assessment.exporter import AssessmentExporter
from tracker.services.identity.merge import PersonMerger
from tracker.services.summary.builder import SummaryBuilder
from tracker.shared.clock import FixedClock
from tracker.shared.config import Settings
from tracker.shared.errors import DatabaseUnavailableError

NOTES_TABLE = "person_notes"
WRITTEN_AT = "2026-09-12T08:30:00+00:00"

#: What the real database does and the in-memory one must be told: a person's
#: notes are deleted with the person.
NOTES_FOLLOW_THEIR_PERSON = {"people": ((NOTES_TABLE, "person_id"),)}


def _note(person: Person, body: str, note_id: int) -> dict[str, Any]:
    """One row of ``person_notes``, as the dashboard saved it."""
    return {
        "id": str(UUID(int=note_id)),
        "person_id": str(person.id),
        "body": body,
        "created_at": WRITTEN_AT,
        "updated_at": WRITTEN_AT,
    }


def _confirmed(person: Person, other: Person) -> ReviewItem:
    """The owner's "yes, same person" about two records."""
    return ReviewItem(
        kind=ReviewKind.SAME_PERSON,
        person_id=person.id,
        other_person_id=other.id,
        question="Is this the same person?",
        answer=ReviewAnswer.YES,
        answered_at=datetime(2026, 9, 19, tzinfo=UTC),
    )


def _two_records(repositories: Repositories) -> tuple[Person, Person]:
    """A named record and its address-only twin, confirmed as one person."""
    named = make_person("Erik Lindqvist")
    by_address = make_person("erik@railfreight.example")
    repositories.people.bulk_upsert([named, by_address])
    repositories.review_items.bulk_upsert([_confirmed(by_address, named)])
    return named, by_address


def _notes(client: FakeSupabaseClient) -> list[dict[str, Any]]:
    return client.tables.get(NOTES_TABLE, [])


def test_a_merge_moves_the_absorbed_records_notes_to_the_survivor(
    repositories: Repositories, fake_client: FakeSupabaseClient
) -> None:
    fake_client.cascades = NOTES_FOLLOW_THEIR_PERSON
    named, by_address = _two_records(repositories)
    fake_client.tables[NOTES_TABLE] = [
        _note(by_address, "Met at the Lyon fair.", 1),
        _note(by_address, "Prefers calls after 4pm.", 2),
        _note(named, "Asked for the brochure in French.", 3),
    ]
    before = [dict(row) for row in _notes(fake_client)]

    report = PersonMerger(repositories).apply_answers()

    assert report.merged == 1
    assert repositories.people.get(by_address.id) is None
    after = _notes(fake_client)
    assert [row["person_id"] for row in after] == [str(named.id)] * 3
    # Nothing but the person changed: the text and both dates are as written.
    assert [{**row, "person_id": None} for row in after] == [
        {**row, "person_id": None} for row in before
    ]


def test_the_notes_move_before_the_record_they_were_on_is_removed(
    repositories: Repositories, fake_client: FakeSupabaseClient
) -> None:
    """Removing the record first would take its notes with it."""
    _, by_address = _two_records(repositories)
    fake_client.tables[NOTES_TABLE] = [_note(by_address, "Met at the Lyon fair.", 1)]
    fake_client.executed.clear()

    PersonMerger(repositories).apply_answers()

    moved = fake_client.executed.index((NOTES_TABLE, "update"))
    removed = fake_client.executed.index(("people", "delete"))
    assert moved < removed


def test_a_record_folded_in_without_a_question_keeps_its_notes_too(
    repositories: Repositories, fake_client: FakeSupabaseClient
) -> None:
    """`people link` joins a company record through the same door."""
    fake_client.cascades = NOTES_FOLLOW_THEIR_PERSON
    hanna = make_person("Hanna Berg")
    company_record = make_person("Northwind Hiring Team")
    repositories.people.bulk_upsert([hanna, company_record])
    fake_client.tables[NOTES_TABLE] = [_note(company_record, "Replies within a day.", 1)]

    PersonMerger(repositories).join(hanna, company_record)

    assert [row["person_id"] for row in _notes(fake_client)] == [str(hanna.id)]


def test_a_merge_with_no_notes_changes_nothing_in_the_notes(
    repositories: Repositories, fake_client: FakeSupabaseClient
) -> None:
    named, _ = _two_records(repositories)
    fake_client.tables[NOTES_TABLE] = [_note(named, "Asked for the brochure in French.", 1)]

    PersonMerger(repositories).apply_answers()

    assert _notes(fake_client) == [_note(named, "Asked for the brochure in French.", 1)]


def test_a_database_without_the_notes_table_still_merges(
    repositories: Repositories, fake_client: FakeSupabaseClient
) -> None:
    """An owner who has not applied migration 0016 has no notes to lose."""
    fake_client.missing_tables = {NOTES_TABLE}
    named, by_address = _two_records(repositories)

    report = PersonMerger(repositories).apply_answers()

    assert report.merged == 1
    assert repositories.people.get(named.id) is not None
    assert repositories.people.get(by_address.id) is None


def test_a_record_is_kept_when_its_notes_could_not_be_moved(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Any refusal but "no such table" stops the merge before anything is removed."""
    _, by_address = _two_records(repositories)
    fake_client.tables[NOTES_TABLE] = [_note(by_address, "Met at the Lyon fair.", 1)]
    _refuse_updates_of_notes(monkeypatch, APIError({"code": "42501", "message": "denied"}))

    with pytest.raises(DatabaseUnavailableError):
        PersonMerger(repositories).apply_answers()

    assert repositories.people.get(by_address.id) is not None
    assert [row["person_id"] for row in _notes(fake_client)] == [str(by_address.id)]


def test_a_dropped_connection_while_moving_notes_is_tried_again(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(repository_base, "_sleep", lambda _seconds: None)
    named, by_address = _two_records(repositories)
    fake_client.tables[NOTES_TABLE] = [_note(by_address, "Met at the Lyon fair.", 1)]
    _refuse_updates_of_notes(monkeypatch, httpx.ConnectError("dropped"), times=1)

    PersonMerger(repositories).apply_answers()

    assert [row["person_id"] for row in _notes(fake_client)] == [str(named.id)]


def _refuse_updates_of_notes(
    monkeypatch: pytest.MonkeyPatch, error: Exception, *, times: int | None = None
) -> None:
    """Make the in-memory database fail a change to the notes, always or a few times."""
    real_execute = FakeQuery.execute
    failures = {"left": times}

    def execute(query: FakeQuery) -> object:
        is_note_update = (query._table, query._operation) == (NOTES_TABLE, "update")  # noqa: SLF001
        if is_note_update and failures["left"] != 0:
            if failures["left"] is not None:
                failures["left"] -= 1
            raise error
        return real_execute(query)

    monkeypatch.setattr(FakeQuery, "execute", execute)


def test_moving_notes_asks_for_nothing_back(
    repositories: Repositories, fake_client: FakeSupabaseClient
) -> None:
    """The answer to the move carries no row, so no note's text reaches Python."""
    one, other = make_person("Marta Olsen"), make_person("marta@quayside.example")
    fake_client.tables[NOTES_TABLE] = [_note(other, "Met at the Lyon fair.", 1)]
    answers: list[list[dict[str, Any]]] = []
    real_execute = FakeQuery.execute

    def execute(query: FakeQuery) -> object:
        response = real_execute(query)
        answers.append(response.data)
        return response

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(FakeQuery, "execute", execute)
        repositories.person_notes.move_to_person(other.id, one.id)

    assert answers == [[]]
    assert fake_client.executed == [(NOTES_TABLE, "update")]


def test_the_model_the_jobs_use_has_no_field_for_a_notes_text() -> None:
    assert set(PersonNote.model_fields) == {"id", "person_id", "created_at", "updated_at"}


def test_the_assessment_never_reads_the_notes(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    clock: FixedClock,
    tmp_path: Path,
) -> None:
    person = make_person()
    thread = make_thread(person, last_inbound=moment(16))
    seed(
        repositories,
        people=[person],
        threads=[thread],
        messages=[
            make_message(thread, direction=Direction.INBOUND, sent_at=moment(16), body="Hello")
        ],
    )
    fake_client.tables[NOTES_TABLE] = [_note(person, "Prefers calls after 4pm.", 1)]
    fake_client.executed.clear()

    result = AssessmentExporter(repositories, clock, tmp_path).export()

    assert result.people == 1
    assert NOTES_TABLE not in {table for table, _ in fake_client.executed}
    assert "4pm" not in result.batch_paths[0].read_text(encoding="utf-8")


def test_the_summary_never_reads_the_notes(settings: Settings) -> None:
    client = sample_client()
    person_id = sample_data()["people"][0]["id"]
    client.tables[NOTES_TABLE] = [
        {
            "id": str(UUID(int=1)),
            "person_id": person_id,
            "body": "Prefers calls after 4pm.",
            "created_at": WRITTEN_AT,
            "updated_at": WRITTEN_AT,
        }
    ]
    builder = SummaryBuilder(build_repositories(as_client(client)), settings, FixedClock(NOW))

    email = builder.build(TODAYS_RUN)

    assert NOTES_TABLE not in {table for table, _ in client.executed}
    assert "4pm" not in email.text_body
    assert "4pm" not in email.html_body
