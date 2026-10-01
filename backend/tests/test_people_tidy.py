"""``people tidy``: the merge and the link as one command, each printed, neither stopping the other.

The promise checked here: tidying in one step prints the lines and leaves the
rows that ``people merge`` followed by ``people link`` do.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from typer.testing import CliRunner

from tests.assessment_world import make_person, make_thread
from tests.conftest import JOB_SEARCH_RULES, FakeSupabaseClient, as_client, printed_lines
from tracker.cli.main import build_cli
from tracker.domain.enums import Channel, Direction, ReviewAnswer, ReviewKind
from tracker.domain.models import Message, Organisation, PersonIdentity, ReviewItem
from tracker.repositories import build_repositories
from tracker.shared.config import Settings
from tracker.shared.errors import DatabaseUnavailableError

MOMENT = datetime(2026, 9, 18, 9, 0, tzinfo=UTC)

MERGE_FAILED = "people merge failed · code=database_unavailable"
LINK_FAILED = "people link failed · code=database_unavailable"


def world() -> FakeSupabaseClient:
    """A people list with one confirmed pair to merge and one likely pair to ask about."""
    client = FakeSupabaseClient()
    repositories = build_repositories(as_client(client))
    named, by_address = make_person("Erik Lindqvist"), make_person("erik@railfreight.example")
    ivan, initials = make_person("Ivan Sokolov"), make_person("is@farsight.example")
    dana = make_person("Dana Goldberg")
    repositories.people.bulk_upsert([named, by_address, ivan, initials, dana])
    repositories.person_identities.bulk_upsert(
        [
            _email(by_address.id, "erik@railfreight.example"),
            PersonIdentity(
                person_id=ivan.id,
                channel=Channel.LINKEDIN,
                identifier="https://www.linkedin.com/in/ivan-sokolov",
            ),
            _email(initials.id, "is@farsight.example"),
            _email(dana.id, "dana@farsight.example"),
        ]
    )
    repositories.organisations.bulk_upsert(
        [Organisation(name="Farsight", email_domain="farsight.example")]
    )
    chain = make_thread(initials, source="chain-1", channel=Channel.EMAIL)
    repositories.conversations.bulk_upsert([make_thread(by_address, source="t-1"), chain])
    repositories.messages.bulk_upsert(
        [
            _message(chain.id, "is@farsight.example", 1),
            _message(chain.id, "dana@farsight.example", 2),
        ]
    )
    repositories.review_items.bulk_upsert(
        [
            ReviewItem(
                kind=ReviewKind.SAME_PERSON,
                person_id=by_address.id,
                other_person_id=named.id,
                question="Is this the same person?",
                answer=ReviewAnswer.YES,
                answered_at=MOMENT,
            )
        ]
    )
    return client


def _email(person_id: object, address: str) -> PersonIdentity:
    return PersonIdentity(
        person_id=person_id,  # type: ignore[arg-type]
        channel=Channel.EMAIL,
        identifier=address,
    )


def _message(thread_id: object, sender: str, number: int) -> Message:
    return Message(
        conversation_id=thread_id,  # type: ignore[arg-type]
        source_message_id=f"m-{number}",
        direction=Direction.INBOUND,
        sent_at=MOMENT,
        sender_identifier=sender,
        body="never read by the people commands",
    )


Wire = Callable[[FakeSupabaseClient], None]


@pytest.fixture
def wire(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> Wire:
    """Point the ``people`` commands at an in-memory database."""
    monkeypatch.setattr("tracker.cli.commands.collect._rules", lambda _repos: JOB_SEARCH_RULES)

    def onto(client: FakeSupabaseClient) -> None:
        monkeypatch.setattr(
            "tracker.cli.commands.collect._wiring",
            lambda: (settings, build_repositories(as_client(client))),
        )

    return onto


def run(*command: str) -> tuple[int, list[str]]:
    """Run one ``tracker people`` command; return how it ended and what it printed."""
    result = CliRunner().invoke(build_cli(), ["people", *command])
    return result.exit_code, printed_lines(result)


def left_behind(client: FakeSupabaseClient) -> dict[str, list[str]]:
    """What the people list looks like afterwards, without the made-up identifiers."""
    return {
        "people": sorted(str(row["full_name"]) for row in client.tables["people"]),
        "questions": sorted(
            f"{row['kind']} · {row['answer']}" for row in client.tables["review_items"]
        ),
    }


def breaking(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Make one of the two services fail the way a database that does not answer does."""

    def refuse(*_arguments: object, **_options: object) -> None:
        message = "the database did not answer"
        raise DatabaseUnavailableError(message)

    monkeypatch.setattr(f"tracker.cli.commands.collect.{name}", refuse)


def test_tidy_prints_and_leaves_what_merge_then_link_do(wire: Wire) -> None:
    in_turn, together = world(), world()
    wire(in_turn)
    _, merged = run("merge")
    _, linked = run("link")
    wire(together)

    exit_code, lines = run("tidy")

    assert exit_code == 0
    assert merged == ["people merged: 1 (1 addresses and profiles, 1 conversations moved)"]
    assert "questions added to the review list: 1" in linked
    assert lines == [*merged, *linked]
    assert left_behind(together) == left_behind(in_turn)


def test_a_merge_that_fails_is_printed_and_the_link_still_runs(
    wire: Wire, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = world()
    wire(client)
    breaking("PersonMerger", monkeypatch)

    exit_code, lines = run("tidy")

    assert exit_code == 0
    assert lines[0] == MERGE_FAILED
    assert "questions added to the review list: 1" in lines[1:]
    assert len(client.tables["people"]) == 5


def test_a_link_that_fails_is_printed_after_the_merge_was_done(
    wire: Wire, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = world()
    wire(client)
    breaking("PeopleLinker", monkeypatch)

    exit_code, lines = run("tidy")

    assert exit_code == 0
    assert lines == [
        "people merged: 1 (1 addresses and profiles, 1 conversations moved)",
        LINK_FAILED,
    ]
    assert len(client.tables["people"]) == 4


def test_both_failing_prints_both_and_still_ends_normally(
    wire: Wire, monkeypatch: pytest.MonkeyPatch
) -> None:
    wire(world())
    breaking("PersonMerger", monkeypatch)
    breaking("PeopleLinker", monkeypatch)

    exit_code, lines = run("tidy")

    assert exit_code == 0
    assert lines == [MERGE_FAILED, LINK_FAILED]


@pytest.mark.parametrize(
    ("command", "service"), [("merge", "PersonMerger"), ("link", "PeopleLinker")]
)
def test_by_hand_a_failing_merge_or_link_still_ends_as_a_failure(
    wire: Wire, monkeypatch: pytest.MonkeyPatch, command: str, service: str
) -> None:
    wire(world())
    breaking(service, monkeypatch)

    exit_code, lines = run(command)

    assert exit_code != 0
    assert lines == []
