"""The rules settle what they can before anything is sent to the assistant."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from tracker.domain.enums import Relevance, RelevanceDecidedBy, ReviewAnswer
from tracker.domain.relevance import (
    PersonEvidence,
    PreDecision,
    ThreadEvidence,
    decide_thread,
    exchange_count,
    needs_assessment,
    owner_has_replied,
)

EARLIER = datetime(2026, 9, 10, 9, 0, tzinfo=UTC)
LATER = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)


def test_a_thread_already_judged_noise_stays_noise() -> None:
    evidence = ThreadEvidence(relevance=Relevance.NOISE)

    assert decide_thread(evidence) is PreDecision.SETTLED_NOISE


def test_a_no_answer_settles_a_thread_as_noise() -> None:
    evidence = ThreadEvidence(relevance=Relevance.UNSURE, owner_answer=ReviewAnswer.NO)

    assert decide_thread(evidence) is PreDecision.SETTLED_NOISE


def test_a_yes_answer_settles_a_thread_as_relevant() -> None:
    evidence = ThreadEvidence(relevance=Relevance.UNSURE, owner_answer=ReviewAnswer.YES)

    assert decide_thread(evidence) is PreDecision.SETTLED_RELEVANT


def test_the_owners_own_decision_is_final() -> None:
    evidence = ThreadEvidence(
        relevance=Relevance.RELEVANT,
        decided_by=RelevanceDecidedBy.OWNER,
    )

    assert decide_thread(evidence) is PreDecision.SETTLED_RELEVANT


def test_anything_else_goes_to_the_assistant() -> None:
    evidence = ThreadEvidence(relevance=Relevance.UNSURE, decided_by=RelevanceDecidedBy.RULE)

    assert decide_thread(evidence) is PreDecision.NEEDS_AI


def test_the_evidence_says_whether_the_owner_ever_replied() -> None:
    assert owner_has_replied(ThreadEvidence(relevance=Relevance.UNSURE, outbound_count=1))
    assert not owner_has_replied(ThreadEvidence(relevance=Relevance.UNSURE, inbound_count=4))


def test_one_sided_messages_are_not_exchanges() -> None:
    one_sided = ThreadEvidence(relevance=Relevance.UNSURE, inbound_count=10, outbound_count=0)
    real = ThreadEvidence(relevance=Relevance.UNSURE, inbound_count=3, outbound_count=2)

    assert exchange_count(one_sided) == 0
    assert exchange_count(real) == 2


def test_a_person_the_owner_ruled_out_is_never_sent_again() -> None:
    evidence = PersonEvidence(
        relevance=Relevance.RELEVANT,
        answered_not_relevant=True,
        last_message_at=LATER,
    )

    assert not needs_assessment(evidence)


def test_a_person_with_no_previous_assessment_is_sent() -> None:
    evidence = PersonEvidence(relevance=Relevance.UNSURE, last_message_at=LATER)

    assert needs_assessment(evidence)


def test_a_person_without_new_messages_is_skipped() -> None:
    evidence = PersonEvidence(
        relevance=Relevance.RELEVANT,
        last_message_at=EARLIER,
        assessed_through=EARLIER,
    )

    assert not needs_assessment(evidence)


def test_a_person_with_new_messages_is_sent_again() -> None:
    evidence = PersonEvidence(
        relevance=Relevance.RELEVANT,
        last_message_at=LATER,
        assessed_through=EARLIER,
    )

    assert needs_assessment(evidence)


def test_a_person_marked_noise_is_skipped() -> None:
    evidence = PersonEvidence(relevance=Relevance.NOISE, last_message_at=LATER)

    assert not needs_assessment(evidence)


def test_something_other_than_a_message_after_the_verdict_sends_the_person_back() -> None:
    quiet = PersonEvidence(
        relevance=Relevance.RELEVANT,
        last_message_at=EARLIER,
        assessed_through=EARLIER,
        assessed_at=EARLIER,
    )

    assert not needs_assessment(quiet)
    assert needs_assessment(replace(quiet, last_meeting_started_at=LATER))
    assert needs_assessment(replace(quiet, last_confirmed_at=LATER))


def test_what_happened_before_the_verdict_was_made_is_already_in_it() -> None:
    evidence = PersonEvidence(
        relevance=Relevance.RELEVANT,
        last_message_at=EARLIER,
        assessed_through=EARLIER,
        assessed_at=LATER,
        last_meeting_started_at=EARLIER,
        last_confirmed_at=EARLIER,
    )

    assert not needs_assessment(evidence)


def test_a_person_ruled_out_stays_out_whatever_else_happened() -> None:
    evidence = PersonEvidence(
        relevance=Relevance.RELEVANT,
        answered_not_relevant=True,
        last_message_at=EARLIER,
        assessed_through=EARLIER,
        assessed_at=EARLIER,
        last_meeting_started_at=LATER,
        last_confirmed_at=LATER,
    )

    assert not needs_assessment(evidence)
