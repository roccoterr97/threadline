"""Undoing the records that were really a shared sender."""

from __future__ import annotations

from datetime import UTC, datetime

from tests.assessment_world import make_message, make_person, make_state, make_thread
from tests.conftest import JOB_SEARCH_RULES
from tracker.domain.enums import Channel, Direction, Relevance, RelevanceDecidedBy
from tracker.domain.models import Conversation, Person, PersonIdentity
from tracker.repositories import Repositories
from tracker.services.identity.relay_repair import RelayUntangler

ASHBY = "no-reply@ashbyhq.com"
CALENDAR = "calendar-notification@google.com"
SENT = datetime(2026, 9, 16, 16, 0, tzinfo=UTC)


def _identity(person: Person, identifier: str) -> PersonIdentity:
    return PersonIdentity(person_id=person.id, channel=Channel.EMAIL, identifier=identifier)


def _thread_from(
    repositories: Repositories,
    person: Person,
    sender: str,
    source: str,
    *,
    relevance: Relevance = Relevance.UNSURE,
    decided_by: RelevanceDecidedBy | None = None,
) -> Conversation:
    thread = make_thread(
        person, source=source, channel=Channel.EMAIL, relevance=relevance, decided_by=decided_by
    )
    message = make_message(thread, direction=Direction.INBOUND, sent_at=SENT, body="Text.")
    repositories.conversations.bulk_upsert([thread])
    repositories.messages.bulk_upsert([message.model_copy(update={"sender_identifier": sender})])
    return thread


def test_a_hiring_system_record_is_emptied_and_hidden(repositories: Repositories) -> None:
    blob = make_person("Cluster Talent Team")
    repositories.people.bulk_upsert([blob])
    repositories.person_identities.bulk_upsert([_identity(blob, ASHBY)])
    northwind = _thread_from(repositories, blob, ASHBY, "t-northwind")

    report = RelayUntangler(repositories, JOB_SEARCH_RULES).untangle()

    assert (report.identities_removed, report.conversations_released) == (1, 1)
    assert report.people_hidden == 1
    stored = repositories.conversations.get(northwind.id)
    assert stored is not None and stored.person_id is None
    hidden = repositories.people.get(blob.id)
    assert hidden is not None and hidden.relevance is Relevance.NOISE
    assert repositories.person_identities.list_for_person(blob.id) == []


def test_an_ai_noise_verdict_on_a_released_thread_is_reset(repositories: Repositories) -> None:
    blob = make_person("no-reply@eu.greenhouse-mail.io", relevance=Relevance.NOISE)
    repositories.people.bulk_upsert([blob])
    address = "no-reply@eu.greenhouse-mail.io"
    repositories.person_identities.bulk_upsert([_identity(blob, address)])
    thread = _thread_from(
        repositories,
        blob,
        address,
        "t-tasko",
        relevance=Relevance.NOISE,
        decided_by=RelevanceDecidedBy.AI,
    )

    RelayUntangler(repositories, JOB_SEARCH_RULES).untangle()

    stored = repositories.conversations.get(thread.id)
    assert stored is not None
    assert stored.relevance is Relevance.UNSURE
    assert stored.relevance_decided_by is None


def test_a_real_person_keeps_their_own_threads_and_is_assessed_again(
    repositories: Repositories,
) -> None:
    erik = make_person("Erik Lindqvist via Docusign")
    repositories.people.bulk_upsert([erik])
    repositories.person_identities.bulk_upsert(
        [_identity(erik, "erik@railfreight.example"), _identity(erik, CALENDAR)]
    )
    own = _thread_from(repositories, erik, "erik@railfreight.example", "t-own")
    reminder = _thread_from(repositories, erik, CALENDAR, "t-reminder")
    repositories.person_states.bulk_upsert([make_state(erik, assessed_through=SENT)])

    report = RelayUntangler(repositories, JOB_SEARCH_RULES).untangle()

    assert report.people_to_reassess == 1
    assert report.people_hidden == 0
    kept = repositories.conversations.get(own.id)
    released = repositories.conversations.get(reminder.id)
    assert kept is not None and kept.person_id == erik.id
    assert released is not None and released.person_id is None
    assert repositories.person_states.find_for_person(erik.id) is None
    renamed = repositories.people.get(erik.id)
    assert renamed is not None and renamed.full_name == "Erik Lindqvist"


def test_running_it_twice_changes_nothing_the_second_time(repositories: Repositories) -> None:
    blob = make_person("Cluster Talent Team")
    repositories.people.bulk_upsert([blob])
    repositories.person_identities.bulk_upsert([_identity(blob, ASHBY)])
    _thread_from(repositories, blob, ASHBY, "t-northwind")
    RelayUntangler(repositories, JOB_SEARCH_RULES).untangle()

    second = RelayUntangler(repositories, JOB_SEARCH_RULES).untangle()

    assert second.identities_removed == 0
    assert second.conversations_released == 0


def test_a_company_key_built_on_a_shared_address_is_left_alone(
    repositories: Repositories,
) -> None:
    northwind = make_person("Northwind AI Hiring Team")
    repositories.people.bulk_upsert([northwind])
    repositories.person_identities.bulk_upsert([_identity(northwind, f"{ASHBY}#northwind ai")])

    report = RelayUntangler(repositories, JOB_SEARCH_RULES).untangle()

    assert report.identities_removed == 0
    assert len(repositories.person_identities.list_for_person(northwind.id)) == 1


def test_an_unfiled_hiring_system_thread_thrown_away_by_the_ai_is_given_back(
    repositories: Repositories,
) -> None:
    nobody = make_person("placeholder")
    thread = _thread_from(
        repositories,
        nobody,
        "noreply@candidates.workablemail.com",
        "t-zeno",
        relevance=Relevance.NOISE,
        decided_by=RelevanceDecidedBy.AI,
    )
    repositories.conversations.bulk_upsert([thread.model_copy(update={"person_id": None})])

    report = RelayUntangler(repositories, JOB_SEARCH_RULES).untangle()

    stored = repositories.conversations.get(thread.id)
    assert report.noise_verdicts_reset == 1
    assert stored is not None and stored.relevance is Relevance.UNSURE


def test_an_owner_noise_decision_is_never_given_back(repositories: Repositories) -> None:
    nobody = make_person("placeholder")
    thread = _thread_from(
        repositories,
        nobody,
        "noreply@candidates.workablemail.com",
        "t-zeno",
        relevance=Relevance.NOISE,
        decided_by=RelevanceDecidedBy.OWNER,
    )
    repositories.conversations.bulk_upsert([thread.model_copy(update={"person_id": None})])

    report = RelayUntangler(repositories, JOB_SEARCH_RULES).untangle()

    stored = repositories.conversations.get(thread.id)
    assert report.noise_verdicts_reset == 0
    assert stored is not None and stored.relevance is Relevance.NOISE
