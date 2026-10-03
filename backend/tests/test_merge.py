"""Answering "yes, same person" is what actually joins two records."""

from __future__ import annotations

import copy
from datetime import UTC, datetime

from tests.assessment_world import make_person, make_thread
from tests.conftest import FakeSupabaseClient
from tracker.domain.enums import Channel, ReviewAnswer, ReviewKind
from tracker.domain.models import PersonIdentity, PersonOverride, ReviewItem
from tracker.repositories import Repositories
from tracker.services.identity.merge import MergeReport, PersonMerger


def _confirmed(person_id: object, other_id: object) -> ReviewItem:
    return ReviewItem(
        kind=ReviewKind.SAME_PERSON,
        person_id=person_id,  # type: ignore[arg-type]
        other_person_id=other_id,  # type: ignore[arg-type]
        question="Is this the same person?",
        answer=ReviewAnswer.YES,
        answered_at=datetime(2026, 9, 19, tzinfo=UTC),
    )


def test_the_record_with_a_real_name_survives(repositories: Repositories) -> None:
    """That is the name the owner recognises on the dashboard."""
    named = make_person("Erik Lindqvist")
    by_address = make_person("erik@railfreight.example")
    repositories.people.bulk_upsert([named, by_address])
    repositories.person_identities.bulk_upsert(
        [
            PersonIdentity(
                person_id=by_address.id,
                channel=Channel.EMAIL,
                identifier="erik@railfreight.example",
            )
        ]
    )
    thread = make_thread(by_address, source="t-1")
    repositories.conversations.bulk_upsert([thread])
    repositories.review_items.bulk_upsert([_confirmed(by_address.id, named.id)])

    report = PersonMerger(repositories).apply_answers()

    assert report.merged == 1
    assert repositories.people.get(named.id) is not None
    assert repositories.people.get(by_address.id) is None
    moved = repositories.conversations.list_for_person(named.id)
    assert [t.id for t in moved] == [thread.id]
    assert [i.identifier for i in repositories.person_identities.list_for_person(named.id)] == [
        "erik@railfreight.example"
    ]


def test_a_correction_is_carried_over_when_the_survivor_has_none(
    repositories: Repositories,
) -> None:
    named = make_person("Nicolas Rey")
    by_address = make_person("nicolasrey75@gmail.com")
    repositories.people.bulk_upsert([named, by_address])
    repositories.person_overrides.bulk_upsert(
        [PersonOverride(person_id=by_address.id, note="met at a conference")]
    )
    repositories.review_items.bulk_upsert([_confirmed(by_address.id, named.id)])

    PersonMerger(repositories).apply_answers()

    kept = repositories.person_overrides.list_for_people([named.id])
    assert [o.note for o in kept] == ["met at a conference"]


def test_running_it_twice_changes_nothing_more(repositories: Repositories) -> None:
    named = make_person("Jean-Marc VALETTE")
    by_address = make_person("jeanmarc@acmedata.example")
    repositories.people.bulk_upsert([named, by_address])
    repositories.review_items.bulk_upsert([_confirmed(by_address.id, named.id)])
    merger = PersonMerger(repositories)

    first = merger.apply_answers()
    second = merger.apply_answers()

    assert first.merged == 1
    # The settled question names one record on both sides, so a later run finds
    # one person where it expects two and leaves it alone.
    assert second.merged == 0
    assert second.skipped == 1
    assert repositories.people.get(named.id) is not None
    assert repositories.people.get(by_address.id) is None


def test_a_question_answered_no_joins_nothing(repositories: Repositories) -> None:
    one = make_person("Marco Rossi")
    other = make_person("marco@acme.example")
    repositories.people.bulk_upsert([one, other])
    repositories.review_items.bulk_upsert(
        [
            ReviewItem(
                kind=ReviewKind.SAME_PERSON,
                person_id=other.id,
                other_person_id=one.id,
                question="Is this the same person?",
                answer=ReviewAnswer.NO,
                answered_at=datetime(2026, 9, 19, tzinfo=UTC),
            )
        ]
    )

    report = PersonMerger(repositories).apply_answers()

    assert report.merged == 0
    assert repositories.people.get(other.id) is not None


def _open(person_id: object, other_id: object) -> ReviewItem:
    return ReviewItem(
        kind=ReviewKind.SAME_PERSON,
        person_id=person_id,  # type: ignore[arg-type]
        other_person_id=other_id,  # type: ignore[arg-type]
        question="Is this the same person?",
    )


def test_an_open_question_about_two_records_now_one_is_removed(
    repositories: Repositories,
) -> None:
    """Mikael had two records and an unanswered question; another yes joined them."""
    mikael = make_person("Mikael Sandberg")
    by_address = make_person("mikael@railfreight.example")
    repositories.people.bulk_upsert([mikael, by_address])
    still_open = _open(by_address.id, mikael.id)
    repositories.review_items.bulk_upsert([_confirmed(by_address.id, mikael.id), still_open])

    report = PersonMerger(repositories).apply_answers()

    assert (report.merged, report.questions_closed) == (1, 1)
    assert repositories.review_items.get(still_open.id) is None
    [kept] = repositories.review_items.list_by_kind(ReviewKind.SAME_PERSON)
    assert kept.answer is ReviewAnswer.YES


def test_a_question_left_naming_one_record_twice_is_cleared_on_the_next_run(
    repositories: Repositories,
) -> None:
    """What a merge before this repair left behind on the live review list."""
    yann = make_person("Yann from Mailwave")
    repositories.people.bulk_upsert([yann])
    repositories.review_items.bulk_upsert([_open(yann.id, yann.id)])

    report = PersonMerger(repositories).apply_answers()

    assert (report.merged, report.questions_closed) == (0, 1)
    assert repositories.review_items.list_by_kind(ReviewKind.SAME_PERSON) == []


def test_an_open_question_about_a_third_person_stays(repositories: Repositories) -> None:
    named = make_person("Erik Lindqvist")
    by_address = make_person("erik@railfreight.example")
    other = make_person("Erik Svensson")
    repositories.people.bulk_upsert([named, by_address, other])
    about_other = _open(by_address.id, other.id)
    repositories.review_items.bulk_upsert([_confirmed(by_address.id, named.id), about_other])

    report = PersonMerger(repositories).apply_answers()

    assert report.questions_closed == 0
    moved = repositories.review_items.get(about_other.id)
    assert moved is not None
    assert (moved.person_id, moved.other_person_id, moved.answer) == (named.id, other.id, None)


def test_a_pair_merged_on_an_earlier_run_is_not_looked_up_again(
    repositories: Repositories, fake_client: FakeSupabaseClient
) -> None:
    """Every answer ever given stays in the list; none of them costs a request."""
    pairs = [
        (make_person(f"Person {index}"), make_person(f"p{index}@acme.example"))
        for index in range(3)
    ]
    repositories.people.bulk_upsert([person for pair in pairs for person in pair])
    repositories.review_items.bulk_upsert(
        [_confirmed(by_address.id, named.id) for named, by_address in pairs]
    )
    merger = PersonMerger(repositories)
    assert merger.apply_answers().merged == 3
    stored = copy.deepcopy(fake_client.tables)
    fake_client.executed.clear()

    report = merger.apply_answers()

    assert fake_client.executed == [("review_items", "select")]
    assert (report.merged, report.skipped, report.questions_closed) == (0, 3, 0)
    assert fake_client.tables == stored


def test_with_nothing_confirmed_the_questions_are_read_once(
    repositories: Repositories, fake_client: FakeSupabaseClient
) -> None:
    one, other = make_person("Marco Rossi"), make_person("marco@acme.example")
    repositories.people.bulk_upsert([one, other])
    still_open = _open(other.id, one.id)
    repositories.review_items.bulk_upsert([still_open])
    fake_client.executed.clear()

    report = PersonMerger(repositories).apply_answers()

    assert fake_client.executed == [("review_items", "select")]
    assert report == MergeReport()
    assert repositories.review_items.get(still_open.id) is not None


def test_a_pair_whose_other_record_is_gone_is_still_looked_up_and_skipped(
    repositories: Repositories, fake_client: FakeSupabaseClient
) -> None:
    """Only a question naming one record twice is known to be done without asking."""
    kept, gone = make_person("Nicolas Rey"), make_person("nicolasrey75@gmail.com")
    repositories.people.bulk_upsert([kept])
    repositories.review_items.bulk_upsert([_confirmed(gone.id, kept.id)])
    fake_client.executed.clear()

    report = PersonMerger(repositories).apply_answers()

    assert fake_client.executed == [("review_items", "select"), ("people", "select")]
    assert (report.merged, report.skipped) == (0, 1)
    assert repositories.people.get(kept.id) is not None


def test_a_question_opened_before_a_merge_is_closed_from_what_the_merge_left(
    repositories: Repositories, fake_client: FakeSupabaseClient
) -> None:
    """After a merge the questions are read again: the first reading is out of date."""
    mikael, by_address = make_person("Mikael Sandberg"), make_person("mikael@railfreight.example")
    repositories.people.bulk_upsert([mikael, by_address])
    still_open = _open(by_address.id, mikael.id)
    repositories.review_items.bulk_upsert([_confirmed(by_address.id, mikael.id), still_open])
    fake_client.executed.clear()

    report = PersonMerger(repositories).apply_answers()

    assert (report.merged, report.questions_closed) == (1, 1)
    reads = [call for call in fake_client.executed if call == ("review_items", "select")]
    # Once to find the answers, once to move the absorbed record's questions,
    # once more because the merge changed them.
    assert len(reads) == 3
    assert repositories.review_items.get(still_open.id) is None
