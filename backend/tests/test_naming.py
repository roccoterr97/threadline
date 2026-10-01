"""Naming stored people whose address plainly spells a name."""

from __future__ import annotations

from tests.assessment_world import make_person
from tests.conftest import JOB_SEARCH_RULES
from tracker.repositories import Repositories
from tracker.services.identity.naming import AddressNamer


def _names(repositories: Repositories) -> set[str]:
    return {person.full_name for person in repositories.people.list()}


def test_a_stored_address_that_spells_a_name_is_shown_by_that_name(
    repositories: Repositories,
) -> None:
    alessia = make_person("alessia.conti@quick-solve.example")
    repositories.people.bulk_upsert([alessia])

    assert AddressNamer(repositories, JOB_SEARCH_RULES).name_all() == 1
    [stored] = repositories.people.list()
    assert (stored.id, stored.full_name) == (alessia.id, "Alessia Conti")


def test_names_and_addresses_that_spell_no_name_are_left_alone(
    repositories: Repositories,
) -> None:
    repositories.people.bulk_upsert(
        [
            make_person("Erik Lindqvist"),
            make_person("jeanmarc@acmedata.example"),
            make_person("no-reply@ashbyhq.com"),
        ]
    )

    assert AddressNamer(repositories, JOB_SEARCH_RULES).name_all() == 0
    assert _names(repositories) == {
        "Erik Lindqvist",
        "jeanmarc@acmedata.example",
        "no-reply@ashbyhq.com",
    }


def test_a_second_pass_changes_nothing(repositories: Repositories) -> None:
    repositories.people.bulk_upsert([make_person("luca.marinello@quick-solve.example")])
    AddressNamer(repositories, JOB_SEARCH_RULES).name_all()

    assert AddressNamer(repositories, JOB_SEARCH_RULES).name_all() == 0
    assert _names(repositories) == {"Luca Marinello"}
