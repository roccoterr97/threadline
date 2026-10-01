"""Name normalisation, free-mail domains and the cautious merge rule."""

from __future__ import annotations

import pytest

from tracker.domain.identity import (
    company_name_from_domain,
    company_stem,
    could_be_the_same_person,
    email_domain,
    is_free_mail_domain,
    may_auto_merge,
    name_from_address,
    normalise_name,
    organisation_key,
    organisation_name_from_domain,
    shown_name_from_address,
)


def test_accents_spacing_and_case_do_not_change_a_name() -> None:
    assert normalise_name("Élodie  Martin") == normalise_name("elodie martin")


@pytest.mark.parametrize(
    ("spelling", "expected"),
    [
        ("Jean-Luc  Picard", "jean luc picard"),
        ("  MARCO   ROSSI  ", "marco rossi"),
        ("O'Connor, Síne", "o connor sine"),
        ("   ", ""),
    ],
)
def test_names_are_reduced_to_a_comparable_form(spelling: str, expected: str) -> None:
    assert normalise_name(spelling) == expected


@pytest.mark.parametrize(
    "address",
    ["someone@ACME.example", "someone@acme.example."],
)
def test_the_domain_is_read_in_lower_case(address: str) -> None:
    assert email_domain(address) == "acme.example"


def test_a_value_without_an_at_sign_has_no_domain() -> None:
    assert email_domain("not-an-address") is None


@pytest.mark.parametrize(
    "domain",
    [
        "gmail.com",
        "hotmail.com",
        "hotmail.it",
        "hotmail.fr",
        "hotmail.co.uk",
        "outlook.com",
        "yahoo.co.jp",
        "icloud.com",
    ],
)
def test_free_mail_domains_never_become_organisations(domain: str) -> None:
    assert is_free_mail_domain(domain) is True
    assert organisation_name_from_domain(domain) is None


@pytest.mark.parametrize(
    ("domain", "expected"),
    [
        ("acme.example", "Acme"),
        ("acme.co.uk", "Acme"),
        ("north-star.example", "North Star"),
    ],
)
def test_an_employer_domain_names_an_organisation(domain: str, expected: str) -> None:
    assert is_free_mail_domain(domain) is False
    assert organisation_name_from_domain(domain) == expected


def test_linkedins_own_domain_is_not_an_employer() -> None:
    assert organisation_name_from_domain("linkedin.com") is None


def test_a_merge_needs_exactly_one_match_on_each_side() -> None:
    assert may_auto_merge(matches_on_other_side=1, matches_on_this_side=1) is True


@pytest.mark.parametrize(
    ("other_side", "this_side"),
    [(2, 1), (1, 2), (0, 1), (0, 0), (3, 3)],
)
def test_anything_ambiguous_is_never_merged(other_side: int, this_side: int) -> None:
    assert may_auto_merge(matches_on_other_side=other_side, matches_on_this_side=this_side) is False


def test_an_address_with_no_display_name_still_suggests_a_person() -> None:
    """Senders often set no name, so the person is recorded as their address.

    The part before the "@" usually still holds the name; it is enough to ask
    the owner about, never enough to merge on.
    """
    assert name_from_address("jeanmarc@acmedata.example") == "jeanmarc"
    assert name_from_address("nicolas.rey75@acme.example") == "nicolas rey"
    assert could_be_the_same_person("jeanmarc", "jean marc valette")
    assert could_be_the_same_person("erik", "erik lindqvist")


def test_a_role_mailbox_is_never_taken_for_a_person() -> None:
    for address in (
        "recruiting@crestline.example",
        "careers@acme.example",
        "no-reply@ashbyhq.com",
        "talent@acme.example",
    ):
        assert name_from_address(address) == "", address


def test_an_address_too_short_to_identify_anyone_is_ignored() -> None:
    """"is@" or "jm@" would pair unrelated people."""
    assert name_from_address("is@farsight.example") == ""
    assert name_from_address("jm@acme.example") == ""
    assert not could_be_the_same_person("is", "ivan sokolov")


def test_two_possible_people_produce_no_suggestion() -> None:
    """Guessing between them would be worse than saying nothing."""
    assert could_be_the_same_person("martin", "martin tessier")
    assert could_be_the_same_person("martin", "martin bernard")


def test_a_first_initial_and_surname_address_reaches_the_person() -> None:
    """An address like "bwerner@" is a common work address for Bruno Werner."""
    assert could_be_the_same_person("bwerner", "bruno werner")
    assert could_be_the_same_person("bwerner", "bruno de werner")
    assert not could_be_the_same_person("bwerner", "boris smith")
    assert not could_be_the_same_person("bwerner", "anna werner")
    assert not could_be_the_same_person("bwerner", "werner")


def test_spellings_of_one_company_share_a_key() -> None:
    assert organisation_key("Anchor VC") == organisation_key("ANCHOR VC") == "anchorvc"
    assert organisation_key("Anchor.vc") == "anchorvc"
    assert organisation_key("Élan Capital") == "elancapital"
    assert organisation_key("...") == ""


@pytest.mark.parametrize(
    ("address", "shown"),
    [
        ("alessia.conti@quick-solve.example", "Alessia Conti"),
        ("luca_marinello@quick-solve.example", "Luca Marinello"),
        ("nicolas.rey75@acme.example", "Nicolas Rey"),
        ("jean-paul.dupont@acme.example", "Jean-Paul Dupont"),
        ("Anna.Maria.Rossi@acme.example", "Anna Maria Rossi"),
    ],
)
def test_an_address_that_spells_first_name_and_surname_is_shown_as_that_name(
    address: str, shown: str
) -> None:
    assert shown_name_from_address(address) == shown


@pytest.mark.parametrize(
    "address",
    [
        "jeanmarc@acmedata.example",
        "a.conti@quick-solve.example",
        "is@farsight.example",
        "careers.team@acme.example",
        "customer.service@acme.example",
        "no-reply@ashbyhq.com",
        "one.two.three.four@acme.example",
        "not-an-address",
    ],
)
def test_an_address_that_does_not_plainly_spell_a_name_is_left_alone(address: str) -> None:
    assert shown_name_from_address(address) == ""


@pytest.mark.parametrize(
    ("label", "stem"),
    [
        ("acmecareers", "acme"),
        ("acmegroup", "acme"),
        ("acme-careers", "acme"),
        ("acme", "acme"),
        ("myjobs", "myjobs"),
        ("hr", "hr"),
    ],
)
def test_a_purpose_word_is_dropped_from_a_domain_label(label: str, stem: str) -> None:
    assert company_stem(label) == stem


def test_a_careers_domain_names_the_company() -> None:
    assert company_name_from_domain("acmecareers.example") == "Acme"
    assert company_name_from_domain("gmail.com") is None
