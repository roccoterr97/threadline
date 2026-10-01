"""Reading an interview out of an entry the owner typed in his own calendar."""

from __future__ import annotations

import pytest

from tests.conftest import JOB_SEARCH_RULES
from tracker.domain.own_meetings import company_in_title, is_own_meeting, own_meeting_identifier
from tracker.domain.relay import is_relay_identity

OWNER_NAMES = ("sam rivera",)


@pytest.mark.parametrize(
    "title",
    [
        "Video interview - Sam Rivera and Acme",
        "Entretien avec Banko",
        "Colloquio Paywave",
        "Phone screening x Nilo",
    ],
)
def test_a_title_naming_an_interview_is_one(title: str) -> None:
    assert is_own_meeting(title, JOB_SEARCH_RULES)


@pytest.mark.parametrize(
    "title",
    [
        "Prep for Farsight",
        "prep for tomorrow's interview",
        "Build",
        "Call india Max",
        "Volo AirExample 1234 per Paris (ABC1234)",
        "Rendez-vous chez Dr Martin",
    ],
)
def test_private_time_is_not_an_interview(title: str) -> None:
    assert not is_own_meeting(title, JOB_SEARCH_RULES)


@pytest.mark.parametrize(
    ("title", "company"),
    [
        ("Video interview - Sam Rivera and Acme", "Acme"),
        ("Sam <> Zephyr AI : interview", "Zephyr AI"),
        ("Entretien avec Banko", "Banko"),
        ("Interview: The Circle (first round)", "The Circle"),
    ],
)
def test_the_company_is_what_is_left_of_the_title(title: str, company: str) -> None:
    assert company_in_title(title, OWNER_NAMES, JOB_SEARCH_RULES) == company


def test_a_title_with_nothing_but_the_owner_names_no_company() -> None:
    assert company_in_title("Interview - Sam Rivera", OWNER_NAMES, JOB_SEARCH_RULES) is None


def test_a_title_that_is_a_sentence_names_no_company() -> None:
    title = "Interview about the new role they mentioned on our last long call"
    assert company_in_title(title, OWNER_NAMES, JOB_SEARCH_RULES) is None


def test_the_company_key_is_never_taken_for_an_address() -> None:
    assert is_relay_identity(own_meeting_identifier("Acme"), JOB_SEARCH_RULES)
