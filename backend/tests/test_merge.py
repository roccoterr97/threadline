"""Answering "yes, same person" is what actually joins two records."""

from __future__ import annotations

import copy
from datetime import UTC, date, datetime

from tests.assessment_world import make_override, make_person, make_state, make_thread
from tests.conftest import FakeSupabaseClient
from tracker.domain.enums import Channel, ContactStatus, Relevance, ReviewAnswer, ReviewKind
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


def test_a_merged_person_is_judged_again_and_takes_the_stronger_relevance(
    repositories: Repositories,
) -> None:
    """LinkedIn Erik was never assessed and unsure; the address was relevant."""
    named = make_person("Erik Lindqvist", relevance=Relevance.UNSURE)
    by_address = make_person("erik@railfreight.example", relevance=Relevance.RELEVANT)
    repositories.people.bulk_upsert([named, by_address])
    repositories.person_states.bulk_upsert(
        [
            make_state(
                by_address,
                assessed_through=datetime(2026, 9, 17, tzinfo=UTC),
                status=ContactStatus.MEETING_PLANNED,
            )
        ]
    )
    repositories.review_items.bulk_upsert([_confirmed(by_address.id, named.id)])

    PersonMerger(repositories).apply_answers()

    kept = repositories.people.get(named.id)
    assert kept is not None
    assert kept.relevance is Relevance.RELEVANT
    assert repositories.person_states.list_for_people([named.id]) == []


def test_an_assessment_made_before_the_merge_is_dropped_so_the_person_is_judged_again(
    repositories: Repositories,
) -> None:
    named = make_person("Erik Lindqvist")
    by_address = make_person("erik@railfreight.example")
    repositories.people.bulk_upsert([named, by_address])
    repositories.person_states.bulk_upsert(
        [make_state(named, assessed_through=datetime(2026, 9, 17, tzinfo=UTC))]
    )
    repositories.review_items.bulk_upsert([_confirmed(by_address.id, named.id)])

    PersonMerger(repositories).apply_answers()

    assert repositories.person_states.list_for_people([named.id]) == []


def test_a_hidden_record_does_not_hide_the_person_it_is_merged_into(
    repositories: Repositories,
) -> None:
    named = make_person("Erik Lindqvist", relevance=Relevance.NOISE)
    by_address = make_person("erik@railfreight.example", relevance=Relevance.UNSURE)
    repositories.people.bulk_upsert([named, by_address])
    repositories.review_items.bulk_upsert([_confirmed(by_address.id, named.id)])

    PersonMerger(repositories).apply_answers()

    kept = repositories.people.get(named.id)
    assert kept is not None
    assert kept.relevance is Relevance.UNSURE


def test_the_survivor_keeps_its_own_category_unless_it_has_none(
    repositories: Repositories,
) -> None:
    known = make_person("Erik Lindqvist", person_type="vc")
    unknown = make_person("Nicolas Rey")
    investor_address = make_person("erik@fund.example", person_type="startup")
    startup_address = make_person("nicolas@startup.example", person_type="startup")
    repositories.people.bulk_upsert([known, unknown, investor_address, startup_address])
    repositories.review_items.bulk_upsert(
        [_confirmed(investor_address.id, known.id), _confirmed(startup_address.id, unknown.id)]
    )

    PersonMerger(repositories).apply_answers()

    assert getattr(repositories.people.get(known.id), "person_type", None) == "vc"
    assert getattr(repositories.people.get(unknown.id), "person_type", None) == "startup"


def test_both_corrections_are_kept_field_by_field_and_the_survivors_win(
    repositories: Repositories,
) -> None:
    named = make_person("Erik Lindqvist")
    by_address = make_person("erik@railfreight.example")
    repositories.people.bulk_upsert([named, by_address])
    mine = make_override(named, status=ContactStatus.IN_PROCESS)
    theirs = make_override(
        by_address,
        status=ContactStatus.CLOSED,
        due_date=date(2026, 10, 2),
        next_action="Send the portfolio",
    ).model_copy(update={"note": "Confirmed by phone"})
    repositories.person_overrides.bulk_upsert([mine, theirs])
    repositories.review_items.bulk_upsert([_confirmed(by_address.id, named.id)])

    PersonMerger(repositories).apply_answers()

    (merged,) = repositories.person_overrides.list_for_people([named.id])
    assert merged.id == mine.id
    assert merged.status is ContactStatus.IN_PROCESS
    assert merged.due_date == date(2026, 10, 2)
    assert merged.next_action == "Send the portfolio"
    assert merged.note == "Confirmed by phone"


def test_a_note_the_survivor_already_has_is_not_overwritten(
    repositories: Repositories,
) -> None:
    named = make_person("Erik Lindqvist")
    by_address = make_person("erik@railfreight.example")
    repositories.people.bulk_upsert([named, by_address])
    repositories.person_overrides.bulk_upsert(
        [
            PersonOverride(person_id=named.id, note="Met at the Lyon fair"),
            PersonOverride(person_id=by_address.id, note="Confirmed by phone"),
        ]
    )
    repositories.review_items.bulk_upsert([_confirmed(by_address.id, named.id)])

    PersonMerger(repositories).apply_answers()

    (merged,) = repositories.person_overrides.list_for_people([named.id])
    assert merged.note == "Met at the Lyon fair"


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
    # Once to find the answers, twice to move the absorbed record's questions
    # (it may be named on either side), once more because the merge changed them.
    assert len(reads) == 4
    assert repositories.review_items.get(still_open.id) is None


def test_a_moved_correction_gets_its_own_primary_key(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
) -> None:
    """The absorbed record's row still exists when the copy is written.

    Reusing its primary key collides with it in the real database, which the
    in-memory one does not enforce, so the test checks the keys. The absorbed
    record's assessment is not copied at all: the merged person is judged again.
    """
    named = make_person("Nicolas Reese")
    by_address = make_person("nicolasreese75@gmail.com")
    repositories.people.bulk_upsert([named, by_address])
    state = make_state(by_address, assessed_through=datetime(2026, 9, 10, tzinfo=UTC))
    override = make_override(by_address, next_action="Send the portfolio")
    repositories.person_states.bulk_upsert([state])
    repositories.person_overrides.bulk_upsert([override])
    repositories.review_items.bulk_upsert([_confirmed(by_address.id, named.id)])

    PersonMerger(repositories).apply_answers()

    (moved_override,) = repositories.person_overrides.list_for_people([named.id])
    assert repositories.person_states.list_for_people([named.id]) == []
    assert moved_override.id != override.id
    assert moved_override.next_action == "Send the portfolio"
    ids = [row["id"] for row in fake_client.tables["person_overrides"]]
    assert len(ids) == len(set(ids)), "person_overrides holds two rows with one primary key"


def test_a_question_naming_the_absorbed_record_second_is_kept(
    repositories: Repositories,
) -> None:
    """The database removes a question when either record it names goes."""
    named = make_person("Erik Lindqvist")
    by_address = make_person("erik@railfreight.example")
    other = make_person("Erik Svensson")
    repositories.people.bulk_upsert([named, by_address, other])
    about_other = _confirmed(other.id, by_address.id).model_copy(update={"answer": ReviewAnswer.NO})
    repositories.review_items.bulk_upsert([_confirmed(by_address.id, named.id), about_other])

    PersonMerger(repositories).apply_answers()

    moved = repositories.review_items.get(about_other.id)
    assert moved is not None
    assert (moved.person_id, moved.other_person_id) == (other.id, named.id)


def test_a_merge_never_leaves_the_owner_the_same_question_twice(
    repositories: Repositories,
) -> None:
    """Two open questions about one person and two records that become one."""
    named = make_person("Erik Lindqvist")
    by_address = make_person("erik@railfreight.example")
    other = make_person("Erik Svensson")
    repositories.people.bulk_upsert([named, by_address, other])
    open_about = [
        _confirmed(other.id, record).model_copy(update={"answer": None, "answered_at": None})
        for record in (named.id, by_address.id)
    ]
    repositories.review_items.bulk_upsert([_confirmed(by_address.id, named.id), *open_about])

    PersonMerger(repositories).apply_answers()

    still_open = [
        (item.person_id, item.other_person_id)
        for item in repositories.review_items.list_by_kind(ReviewKind.SAME_PERSON)
        if item.answer is None
    ]
    assert still_open == [(other.id, named.id)]


def test_answers_chained_through_one_record_join_all_three(repositories: Repositories) -> None:
    """ "b is a" and "c is b": the second answer names b as the other person.

    Both answers are read before either merge, so the second must follow b to
    the record it became, or c stays on its own line.
    """
    anna = make_person("Anna Vermeer")
    work = make_person("anna@northwind.example")
    personal = make_person("anna.v@mailbox.example")
    repositories.people.bulk_upsert([anna, work, personal])
    repositories.review_items.bulk_upsert(
        [_confirmed(work.id, anna.id), _confirmed(personal.id, work.id)]
    )

    report = PersonMerger(repositories).apply_answers()

    assert report.merged == 2
    assert repositories.people.get(anna.id) is not None
    assert repositories.people.get(work.id) is None
    assert repositories.people.get(personal.id) is None
    questions = repositories.review_items.list_by_kind(ReviewKind.SAME_PERSON)
    assert len(questions) == 2
    assert all(q.person_id == q.other_person_id == anna.id for q in questions)
