"""Walking what is stored and asking about each new likely pair."""

from __future__ import annotations

from datetime import UTC, datetime

from tests.assessment_world import make_person, make_thread
from tests.conftest import JOB_SEARCH_RULES, FakeSupabaseClient
from tracker.domain.enums import Channel, Direction, Relevance, ReviewAnswer, ReviewKind
from tracker.domain.models import Message, Organisation, Person, PersonIdentity, ReviewItem
from tracker.repositories import Repositories
from tracker.services.identity.linker import PeopleLinker
from tracker.services.identity.merge import PersonMerger

SENT = datetime(2026, 9, 18, 9, 0, tzinfo=UTC)


def _email(person: Person, address: str) -> PersonIdentity:
    return PersonIdentity(person_id=person.id, channel=Channel.EMAIL, identifier=address)


def _profile(person: Person) -> PersonIdentity:
    return PersonIdentity(
        person_id=person.id,
        channel=Channel.LINKEDIN,
        identifier=f"https://www.linkedin.com/in/{person.id}",
    )


def _from(thread_id: object, sender: str, number: int) -> Message:
    return Message(
        conversation_id=thread_id,  # type: ignore[arg-type]
        source_message_id=f"m-{number}",
        direction=Direction.INBOUND,
        sent_at=SENT,
        sender_identifier=sender,
        body="never read by the linker",
    )


def _farsight(repositories: Repositories) -> tuple[Person, Person, Person]:
    """Ivan on LinkedIn, his initials-only address, and Dana in one e-mail chain."""
    ivan = make_person("Ivan Sokolov")
    initials = make_person("is@farsight.example")
    dana = make_person("Dana Goldberg")
    repositories.people.bulk_upsert([ivan, initials, dana])
    repositories.person_identities.bulk_upsert(
        [
            _profile(ivan),
            _email(initials, "is@farsight.example"),
            _email(dana, "dana@farsight.example"),
        ]
    )
    repositories.organisations.bulk_upsert(
        [Organisation(name="Farsight", email_domain="farsight.example")]
    )
    thread = make_thread(initials, source="chain-1", channel=Channel.EMAIL)
    repositories.conversations.bulk_upsert([thread])
    repositories.messages.bulk_upsert(
        [_from(thread.id, "is@farsight.example", 1), _from(thread.id, "dana@farsight.example", 2)]
    )
    return ivan, initials, dana


def test_one_opportunity_shown_as_two_lines_becomes_one_question(
    repositories: Repositories,
) -> None:
    _, initials, dana = _farsight(repositories)

    report = PeopleLinker(repositories, JOB_SEARCH_RULES).link()

    assert report.asked == 1
    [question] = repositories.review_items.list_by_kind(ReviewKind.SAME_PERSON)
    assert (question.person_id, question.other_person_id) == (initials.id, dana.id)
    assert question.answer is None
    assert question.question == (
        "Should is@farsight.example be shown on the same line as Dana Goldberg? "
        "Both are at Farsight and wrote in the same e-mail conversation."
    )


def test_nothing_is_merged_without_an_answer(repositories: Repositories) -> None:
    ivan, initials, dana = _farsight(repositories)

    PeopleLinker(repositories, JOB_SEARCH_RULES).link()

    remaining = repositories.people.list_by_ids([ivan.id, initials.id, dana.id])
    assert len(remaining) == 3


def test_a_second_run_asks_nothing_new(repositories: Repositories) -> None:
    _farsight(repositories)
    linker = PeopleLinker(repositories, JOB_SEARCH_RULES)

    linker.link()
    second = linker.link()

    assert second.asked == 0
    assert second.already_asked == 1
    assert len(repositories.review_items.list_by_kind(ReviewKind.SAME_PERSON)) == 1


def test_a_pair_asked_the_other_way_round_is_not_asked_again(
    repositories: Repositories,
) -> None:
    _, initials, dana = _farsight(repositories)
    repositories.review_items.bulk_upsert(
        [
            ReviewItem(
                kind=ReviewKind.SAME_PERSON,
                person_id=dana.id,
                other_person_id=initials.id,
                question="asked earlier",
                answer=ReviewAnswer.NO,
                answered_at=SENT,
            )
        ]
    )

    report = PeopleLinker(repositories, JOB_SEARCH_RULES).link()

    assert report.asked == 0


def test_a_yes_is_applied_by_the_existing_merger(repositories: Repositories) -> None:
    _, initials, dana = _farsight(repositories)
    PeopleLinker(repositories, JOB_SEARCH_RULES).link()
    [question] = repositories.review_items.list_by_kind(ReviewKind.SAME_PERSON)
    repositories.review_items.bulk_upsert(
        [question.model_copy(update={"answer": ReviewAnswer.YES, "answered_at": SENT})]
    )

    PersonMerger(repositories).apply_answers()

    assert repositories.people.get(initials.id) is None
    assert repositories.people.get(dana.id) is not None
    assert PeopleLinker(repositories, JOB_SEARCH_RULES).link().asked == 0


def test_an_older_address_record_is_asked_about_once_its_name_appears(
    repositories: Repositories,
) -> None:
    """The matcher only compares a *new* address; this catches the old ones."""
    by_address = make_person("erik@railfreight.example")
    erik = make_person("Erik Lindqvist")
    repositories.people.bulk_upsert([by_address, erik])
    repositories.person_identities.bulk_upsert(
        [_email(by_address, "erik@railfreight.example"), _profile(erik)]
    )

    PeopleLinker(repositories, JOB_SEARCH_RULES).link()

    [question] = repositories.review_items.list_by_kind(ReviewKind.SAME_PERSON)
    assert (question.person_id, question.other_person_id) == (by_address.id, erik.id)
    assert question.question == (
        "Is erik@railfreight.example on email the same person as Erik Lindqvist on linkedin?"
    )


def test_noise_people_and_noise_threads_raise_no_question(repositories: Repositories) -> None:
    initials = make_person("is@farsight.example")
    dana = make_person("Dana Goldberg", relevance=Relevance.NOISE)
    repositories.people.bulk_upsert([initials, dana])
    repositories.person_identities.bulk_upsert(
        [_email(initials, "is@farsight.example"), _email(dana, "dana@farsight.example")]
    )
    thread = make_thread(
        initials, source="chain-1", channel=Channel.EMAIL, relevance=Relevance.NOISE
    )
    repositories.conversations.bulk_upsert([thread])
    repositories.messages.bulk_upsert([_from(thread.id, "dana@farsight.example", 1)])

    assert PeopleLinker(repositories, JOB_SEARCH_RULES).link().asked == 0


def test_no_message_text_is_requested(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
) -> None:
    """Only who sent what is needed; the bodies stay in the database."""
    _farsight(repositories)
    selected: list[tuple[str, ...]] = []
    original = FakeSupabaseClient.table

    def spy(client: FakeSupabaseClient, name: str) -> object:
        query = original(client, name)
        if name == "messages":
            select = query.select

            def recording(*columns: str, **options: object) -> object:
                selected.append(columns)
                return select(*columns, **options)

            query.select = recording  # type: ignore[method-assign]
        return query

    fake_client.table = lambda name: spy(fake_client, name)  # type: ignore[method-assign]

    PeopleLinker(repositories, JOB_SEARCH_RULES).link()

    assert selected
    assert all("body" not in ",".join(columns) and "*" not in columns for columns in selected)


def _summit(repositories: Repositories) -> tuple[Person, Person]:
    """Bruno on LinkedIn only, and his work address with no name of its own."""
    summit = Organisation(name="Summit Capital")
    repositories.organisations.bulk_upsert([summit])
    bruno = make_person("Bruno Werner").model_copy(update={"organisation_id": summit.id})
    by_address = make_person("bwerner@summitcap.example").model_copy(
        update={"organisation_id": summit.id}
    )
    repositories.people.bulk_upsert([bruno, by_address])
    repositories.person_identities.bulk_upsert(
        [_profile(bruno), _email(by_address, "bwerner@summitcap.example")]
    )
    return bruno, by_address


def test_a_linkedin_contact_and_their_bare_work_address_become_one_question(
    repositories: Repositories,
) -> None:
    bruno, by_address = _summit(repositories)

    first = PeopleLinker(repositories, JOB_SEARCH_RULES).link()
    second = PeopleLinker(repositories, JOB_SEARCH_RULES).link()

    assert (first.asked, second.asked, second.already_asked) == (1, 0, 1)
    [question] = repositories.review_items.list_by_kind(ReviewKind.SAME_PERSON)
    assert (question.person_id, question.other_person_id) == (by_address.id, bruno.id)
    assert question.question == (
        "Is bwerner@summitcap.example on email the same person as Bruno Werner on linkedin?"
    )


def test_one_fund_spelled_three_ways_asks_about_each_fitting_name(
    repositories: Repositories,
) -> None:
    spellings = [Organisation(name=name) for name in ("Anchor VC", "ANCHOR VC", "Anchor.vc")]
    repositories.organisations.bulk_upsert(spellings)
    by_address, alexey, alex = (
        make_person(name).model_copy(update={"organisation_id": spelling.id})
        for name, spelling in zip(
            ("alex@anchor.example", "Alexey Morozov", "Alex Bronski"), spellings, strict=True
        )
    )
    repositories.people.bulk_upsert([by_address, alexey, alex])
    repositories.person_identities.bulk_upsert(
        [_email(by_address, "alex@anchor.example"), _profile(alexey), _profile(alex)]
    )

    report = PeopleLinker(repositories, JOB_SEARCH_RULES).link()

    assert report.asked == 2
    asked = repositories.review_items.list_by_kind(ReviewKind.SAME_PERSON)
    assert {item.person_id for item in asked} == {by_address.id}
    assert {item.other_person_id for item in asked} == {alex.id, alexey.id}


def test_a_shared_senders_address_is_never_mined_for_a_name(
    repositories: Repositories,
) -> None:
    """A shared calendar's address names the calendar, not the person it spells."""
    system = make_person("ivan.sokolov@group.calendar.google.com")
    ivan = make_person("Ivan Sokolov")
    repositories.people.bulk_upsert([system, ivan])
    repositories.person_identities.bulk_upsert(
        [_email(system, "ivan.sokolov@group.calendar.google.com"), _profile(ivan)]
    )

    report = PeopleLinker(repositories, JOB_SEARCH_RULES).link()

    assert report.asked == 0


def _company_record(repositories: Repositories, name: str, company: str) -> Person:
    """A record known only through a hiring system, such as "Northwind AI Hiring Team"."""
    organisation = Organisation(name=company)
    repositories.organisations.bulk_upsert([organisation])
    record = make_person(name).model_copy(update={"organisation_id": organisation.id})
    repositories.people.bulk_upsert([record])
    repositories.person_identities.bulk_upsert(
        [_email(record, f"no-reply@ashbyhq.com#{company.lower()}")]
    )
    return record


def test_a_company_record_joins_the_one_person_of_that_company_without_asking(
    repositories: Repositories,
) -> None:
    record = _company_record(repositories, "Northwind AI Hiring Team", "Northwind AI")
    hanna = make_person("Hanna Keller")
    repositories.people.bulk_upsert([hanna])
    repositories.person_identities.bulk_upsert([_email(hanna, "hanna.keller@northwind.ai")])
    thread = make_thread(record, source="t-confirmation", channel=Channel.EMAIL)
    repositories.conversations.bulk_upsert([thread])

    report = PeopleLinker(repositories, JOB_SEARCH_RULES).link()

    assert report.joined == 1
    assert report.asked == 0
    assert repositories.people.get(record.id) is None
    moved = repositories.conversations.get(thread.id)
    assert moved is not None and moved.person_id == hanna.id
    identities = {i.identifier for i in repositories.person_identities.list_for_person(hanna.id)}
    assert "no-reply@ashbyhq.com#northwind ai" in identities


def test_a_company_record_with_several_people_is_asked_about_not_guessed(
    repositories: Repositories,
) -> None:
    record = _company_record(repositories, "Orbita Hiring Team", "Orbita")
    lena = make_person("Lena Hoffman-Adler")
    anil = make_person("Anil Shah")
    repositories.people.bulk_upsert([lena, anil])
    repositories.person_identities.bulk_upsert(
        [_email(lena, "lena.h@orbita.example"), _email(anil, "anil.s@orbita.example")]
    )

    report = PeopleLinker(repositories, JOB_SEARCH_RULES).link()

    assert report.joined == 0
    assert report.asked == 2
    assert repositories.people.get(record.id) is not None
    questions = repositories.review_items.list_by_kind(ReviewKind.SAME_PERSON)
    assert all("will not choose on its own" in item.question for item in questions)


def test_a_company_record_for_another_company_is_left_alone(
    repositories: Repositories,
) -> None:
    record = _company_record(repositories, "Bluebird Hiring Team", "Bluebird")
    hanna = make_person("Hanna Keller")
    repositories.people.bulk_upsert([hanna])
    repositories.person_identities.bulk_upsert([_email(hanna, "hanna.keller@northwind.ai")])

    report = PeopleLinker(repositories, JOB_SEARCH_RULES).link()

    assert (report.joined, report.asked) == (0, 0)
    assert repositories.people.get(record.id) is not None


def test_the_acme_hiring_team_folds_into_chloe_when_her_mail_arrives(
    repositories: Repositories,
) -> None:
    """The hiring system wrote as acmecareers.example; the recruiter as acmegroup.example."""
    record = make_person("Acme Hiring Team").model_copy(
        update={"organisation_id": _organisation(repositories, "Acme").id}
    )
    chloe = make_person("Chloe Garner").model_copy(
        update={"organisation_id": _organisation(repositories, "Acmegroup").id}
    )
    repositories.people.bulk_upsert([record, chloe])
    repositories.person_identities.bulk_upsert(
        [
            _email(record, "no-reply@acmecareers.example#acme"),
            _email(chloe, "chloe.garner@acmegroup.example"),
        ]
    )
    thread = make_thread(record, source="t-video-interview", channel=Channel.EMAIL)
    repositories.conversations.bulk_upsert([thread])

    report = PeopleLinker(repositories, JOB_SEARCH_RULES).link()

    assert report.joined == 1
    assert repositories.people.get(record.id) is None
    moved = repositories.conversations.get(thread.id)
    assert moved is not None and moved.person_id == chloe.id


def _organisation(repositories: Repositories, name: str) -> Organisation:
    organisation = Organisation(name=name)
    repositories.organisations.bulk_upsert([organisation])
    return organisation
