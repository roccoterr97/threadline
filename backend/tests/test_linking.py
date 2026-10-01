"""The rules that decide which pairs of records are worth a question."""

from __future__ import annotations

from uuid import UUID, uuid4

from tracker.domain.identity import organisation_key
from tracker.domain.linking import (
    LinkCandidate,
    LinkReason,
    company_domains,
    company_keys,
    company_record_matches,
    match_by_address_name,
    named_colleagues,
    only_person_at,
    same_organisation,
    shared_company_domain,
    suggest_links,
)


def _person(name: str, *addresses: str) -> LinkCandidate:
    return LinkCandidate(uuid4(), name, tuple(addresses))


def _at(organisation: str, name: str, *addresses: str) -> LinkCandidate:
    return LinkCandidate(uuid4(), name, tuple(addresses), organisation_key(organisation))


def test_free_mail_and_platform_domains_name_no_company() -> None:
    domains = company_domains(["a@gmail.com", "b@hotmail.it", "c@linkedin.com", "d@acme.example"])

    assert domains == frozenset({"acme.example"})


def test_a_bare_address_meets_the_one_name_it_holds() -> None:
    erik = _person("Erik Lindqvist")
    by_address = _person("erik@railfreight.example", "erik@railfreight.example")

    assert match_by_address_name(by_address, [erik, by_address]) == erik.person_id


def test_a_record_with_a_real_name_is_never_the_address_side() -> None:
    erik = _person("Erik Lindqvist", "erik@railfreight.example")
    other = _person("Erik Lindqvist")

    assert match_by_address_name(erik, [erik, other]) is None


def test_an_address_that_fits_two_people_asks_nothing() -> None:
    alexander = _person("Alex Brown")
    alexandra = _person("Alexandra Stone")
    by_address = _person("alex@anchor.example", "alex@anchor.example")

    assert match_by_address_name(by_address, [alexander, alexandra, by_address]) is None


def test_two_addresses_at_one_company_share_it() -> None:
    first = _person("Dana Goldberg", "dana@farsight.example")
    second = _person("is@farsight.example", "is@farsight.example")

    assert shared_company_domain(first, second) == "farsight.example"


def test_two_gmail_addresses_share_nothing() -> None:
    first = _person("Anna", "anna@gmail.com")
    second = _person("Bruno", "bruno@gmail.com")

    assert shared_company_domain(first, second) is None


def test_a_bare_address_with_one_named_colleague_is_put_to_the_owner() -> None:
    dana = _person("Dana Goldberg", "dana@farsight.example")
    by_address = _person("is@farsight.example", "is@farsight.example")

    assert named_colleagues(by_address, [dana, by_address]) == [
        (dana.person_id, "farsight.example")
    ]


def test_a_bare_address_with_two_named_colleagues_stays_silent() -> None:
    dana = _person("Dana Goldberg", "dana@farsight.example")
    ivan = _person("Ivan Sokolov", "ivan@farsight.example")
    by_address = _person("is@farsight.example", "is@farsight.example")

    assert named_colleagues(by_address, [dana, ivan, by_address]) == []


def test_a_named_person_is_never_placed_by_the_colleague_rule() -> None:
    dana = _person("Dana Goldberg", "dana@farsight.example")
    ivan = _person("Ivan Sokolov", "ivan@farsight.example")

    assert named_colleagues(ivan, [dana, ivan]) == []


def test_colleagues_in_one_conversation_are_suggested_once() -> None:
    dana = _person("Dana Goldberg", "dana@farsight.example")
    by_address = _person("is@farsight.example", "is@farsight.example")
    group = frozenset({dana.person_id, by_address.person_id})

    suggestions = suggest_links([dana, by_address], [group, group])

    assert len(suggestions) == 1
    only = suggestions[0]
    assert (only.person_id, only.other_person_id) == (by_address.person_id, dana.person_id)
    # The conversation is stronger evidence than "the only named colleague".
    assert only.reason is LinkReason.SHARED_THREAD


def test_the_same_person_twice_in_one_conversation_is_no_pair() -> None:
    dana = _person("Dana Goldberg", "dana@farsight.example", "dana.g@farsight.example")

    assert suggest_links([dana], [frozenset({dana.person_id})]) == []


def test_people_from_different_companies_in_one_thread_are_left_alone() -> None:
    dana = _person("Dana Goldberg", "dana@farsight.example")
    bruno = _person("Bruno Rossi", "bruno@acme.example")

    assert suggest_links([dana, bruno], [frozenset({dana.person_id, bruno.person_id})]) == []


def test_an_unknown_person_in_a_thread_group_is_ignored() -> None:
    dana = _person("Dana Goldberg", "dana@farsight.example")
    stranger: UUID = uuid4()

    assert suggest_links([dana], [frozenset({dana.person_id, stranger})]) == []


def test_a_linkedin_colleague_known_only_by_company_name_is_asked_about() -> None:
    """Bruno has no Summit address; the company name is all they share."""
    bruno = _at("Summit Capital", "Bruno Werner")
    by_address = _at("Summit Capital", "bwerner@summitcap.example", "bwerner@summitcap.example")

    assert named_colleagues(by_address, [bruno, by_address]) == [(bruno.person_id, None)]


def test_spellings_of_one_company_name_are_one_company() -> None:
    first = _at("Anchor VC", "Alex Bronski")
    second = _at("ANCHOR VC", "Alexey Morozov")
    third = _at("Anchor.vc", "alex@anchor.example", "alex@anchor.example")

    assert same_organisation(first, second)
    assert same_organisation(second, third)


def test_people_with_no_company_are_not_one_company() -> None:
    assert not same_organisation(_person("Anna Rossi"), _person("Bruno Bianchi"))


def test_an_address_that_fits_two_colleagues_asks_about_each() -> None:
    """At one fund, "alex" could be Alex or Alexey: ask, never guess."""
    alex = _at("Anchor.vc", "Alex Bronski")
    alexey = _at("ANCHOR VC", "Alexey Morozov")
    by_address = _at("Anchor VC", "alex@anchor.example", "alex@anchor.example")

    found = named_colleagues(by_address, [alex, alexey, by_address])

    assert {colleague for colleague, _ in found} == {alex.person_id, alexey.person_id}


def test_colleagues_the_address_name_does_not_fit_are_left_out() -> None:
    alex = _at("Anchor.vc", "Alex Bronski")
    maria = _at("Anchor.vc", "Maria Lopez")
    by_address = _at("Anchor.vc", "alex@anchor.example", "alex@anchor.example")

    assert named_colleagues(by_address, [alex, maria, by_address]) == [(alex.person_id, None)]


def test_an_address_that_fits_too_many_colleagues_asks_nothing() -> None:
    team = [_at("Acme", f"Alex Number{index}") for index in range(4)]
    by_address = _at("Acme", "alex@acme.example", "alex@acme.example")

    assert named_colleagues(by_address, [*team, by_address]) == []


def test_the_same_first_name_at_another_company_is_not_a_colleague() -> None:
    alex = _at("Swiftinvest", "Alex Bronski")
    by_address = _at("Anchor VC", "alex@anchor.example", "alex@anchor.example")

    assert named_colleagues(by_address, [alex, by_address]) == []


def test_a_careers_domain_a_group_domain_and_the_name_share_one_key() -> None:
    acme = organisation_key("Acme")

    assert acme in company_keys(["notification@acmecareers.example"])
    assert acme in company_keys(["chloe.garner@acmegroup.example"])


def test_the_acme_company_record_meets_chloe_at_acmegroup() -> None:
    record = LinkCandidate(
        uuid4(), "Acme Hiring Team", (), organisation_key("Acme"), is_company_record=True
    )
    chloe = _at("Acmegroup", "Chloe Garner", "chloe.garner@acmegroup.example")

    assert company_record_matches([record, chloe]) == [(record, (chloe,))]


def test_the_one_person_at_a_company_is_preferred_to_its_company_record() -> None:
    record = LinkCandidate(
        uuid4(), "Acme Hiring Team", (), organisation_key("Acme"), is_company_record=True
    )
    chloe = _person("Chloe Garner", "chloe.garner@acmegroup.example")

    assert only_person_at("acme", [record, chloe]) == chloe
    assert only_person_at("acme", [record]) == record
    assert only_person_at("bluebird", [record, chloe]) is None


def test_two_people_at_a_company_name_nobody_on_their_own() -> None:
    first = _person("Chloe Garner", "chloe.garner@acmegroup.example")
    second = _person("Sam Lee", "sam.lee@acme.example")

    assert only_person_at("acme", [first, second]) is None
