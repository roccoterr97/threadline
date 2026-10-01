"""Looking behind shared senders, with the cases seen in the real mailbox."""

from __future__ import annotations

import pytest

from tests.conftest import JOB_SEARCH_RULES
from tracker.domain.enums import Relevance
from tracker.domain.prefilter import (
    EmailThreadEvidence,
    is_relay_sender,
    is_work_system_sender,
    judge_email_thread,
)
from tracker.domain.relay import (
    RelayedSender,
    company_from_subject,
    is_relay_identity,
    real_sender,
)

OWNER = "owner@example.com"
ASHBY = "no-reply@ashbyhq.com"


def _is_owner(address: str) -> bool:
    return address == OWNER


def _sender(
    address: str,
    name: str,
    *,
    reply_to: tuple[tuple[str, str], ...] = (),
    subject: str = "",
) -> RelayedSender:
    return real_sender(address, name, reply_to, subject, _is_owner, JOB_SEARCH_RULES)


def test_a_calendar_invitation_is_filed_under_the_organiser_in_reply_to() -> None:
    sender = _sender(
        "c_0000example@group.calendar.google.com",
        "Interviews",
        reply_to=(("hanna.keller@northwind.example", "Hanna Keller"),),
        subject="Invitation: Operations Associate - Intro Call",
    )

    assert sender == RelayedSender("hanna.keller@northwind.example", "Hanna Keller")


def test_a_google_calendar_reminder_is_filed_under_the_address_in_its_name() -> None:
    sender = _sender(
        "calendar-notification@google.com",
        "erik@railfreight.example (Google Calendar)",
        reply_to=(("erik@railfreight.example", "erik@railfreight.example"),),
    )

    assert sender.identifier == "erik@railfreight.example"
    assert sender.organisation_name is None


def test_an_ashby_mail_is_filed_under_the_company_in_its_name() -> None:
    sender = _sender(
        ASHBY, "Northwind AI Hiring Team", subject="Northwind AI Interview Confirmation"
    )

    assert sender == RelayedSender(
        f"{ASHBY}#northwind ai", "Northwind AI Hiring Team", "Northwind AI"
    )


@pytest.mark.parametrize(
    ("name", "company"),
    [
        ("Cluster Talent Team", "Cluster"),
        ("tello team", "tello"),
        ("Slope Labs Hiring", "Slope Labs"),
        ("Parlo.ai Hiring Team", "Parlo.ai"),
    ],
)
def test_the_team_words_are_removed_from_a_company_name(name: str, company: str) -> None:
    assert _sender(ASHBY, name).organisation_name == company


def test_two_companies_behind_one_address_are_two_identities() -> None:
    first = _sender(ASHBY, "Northwind AI Hiring Team")
    second = _sender(ASHBY, "Bluebird Hiring Team")

    assert first.identifier != second.identifier


def test_a_system_that_names_itself_is_read_from_the_subject() -> None:
    sender = _sender(
        "noreply@candidates.workablemail.com",
        "Workable",
        subject="Thanks for applying to Green Things",
    )

    assert sender.organisation_name == "Green Things"
    assert sender.display_name == "Green Things Hiring Team"
    assert sender.identifier == "noreply@candidates.workablemail.com#green things"


def test_a_name_that_is_just_the_address_is_read_from_the_subject() -> None:
    address = "no-reply@eu.greenhouse-mail.io"
    sender = _sender(address, address, subject="Thank you for applying to Tasko")

    assert sender.organisation_name == "Tasko"


@pytest.mark.parametrize(
    ("subject", "company"),
    [
        ("Sam - Thank you for your application to ZYX!", "ZYX"),
        ("Thanks for applying to tello ☎️", "tello"),
        ("Update on your application at EthosAI", "EthosAI"),
        ("Thank you for your interest in Orbita, Sam", "Orbita"),
        ("Welcome to Bluebird's recruitment process!", "Bluebird"),
        ("Your weekly digest", None),
    ],
)
def test_the_company_is_read_from_common_subjects(subject: str, company: str | None) -> None:
    assert company_from_subject(subject, JOB_SEARCH_RULES) == company


def test_an_e_signature_request_is_filed_under_the_requester() -> None:
    sender = _sender(
        "dse_na4@docusign.net",
        "Aarav Varma via Docusign",
        reply_to=(("aarav@oris.example", ""),),
    )

    assert sender == RelayedSender("aarav@oris.example", "Aarav Varma")


def test_a_reply_to_that_is_the_owner_or_a_machine_is_skipped() -> None:
    sender = _sender(
        ASHBY,
        "Bluebird Hiring Team",
        reply_to=((OWNER, "Sam"), ("no-reply@bluebird.example", "Bluebird")),
    )

    assert sender.organisation_name == "Bluebird"


def test_a_recruiters_own_name_is_shown_but_the_subject_company_is_the_key() -> None:
    sender = _sender("no-reply@greenhouse.io", "Jane Doe", subject="Thank you for applying to Acme")

    assert sender == RelayedSender("no-reply@greenhouse.io#acme", "Jane Doe", "Acme")


def test_a_company_named_without_team_words_is_still_a_company() -> None:
    sender = _sender(
        "no-reply@hire.lever.co",
        "Calm Educate",
        subject="Thank you for your application to Calm Educate",
    )

    assert sender == RelayedSender(
        "no-reply@hire.lever.co#calm educate", "Calm Educate", "Calm Educate"
    )


def test_a_recruiter_address_of_their_own_is_not_a_shared_sender() -> None:
    sender = _sender("katrin.ethosai@recruitee-mail.com", "Katrin Holm")

    assert sender == RelayedSender("katrin.ethosai@recruitee-mail.com", "Katrin Holm")


def test_nothing_to_go_on_keeps_the_shared_address() -> None:
    assert _sender(ASHBY, "", subject="Hello").identifier == ASHBY


def test_an_ordinary_sender_is_left_alone() -> None:
    sender = _sender("anna@acme.example", "Anna Lee", reply_to=(("other@acme.example", "Other"),))

    assert sender == RelayedSender("anna@acme.example", "Anna Lee")


def test_shared_addresses_and_the_keys_built_on_them_are_recognised() -> None:
    assert is_relay_sender("dse_NA4@docusign.net", JOB_SEARCH_RULES)
    assert is_relay_sender("c_0001example@group.calendar.google.com", JOB_SEARCH_RULES)
    assert is_relay_sender("calendar-notification@google.com", JOB_SEARCH_RULES)
    assert not is_relay_sender("no-reply@accounts.google.com", JOB_SEARCH_RULES)
    assert not is_relay_sender("max.reuter@examplegmbh.teamtailor-mail.com", JOB_SEARCH_RULES)
    assert is_work_system_sender("max.reuter@examplegmbh.teamtailor-mail.com", JOB_SEARCH_RULES)
    assert is_relay_identity(f"{ASHBY}#northwind ai", JOB_SEARCH_RULES)
    assert not is_relay_identity("anna@acme.example", JOB_SEARCH_RULES)


@pytest.mark.parametrize(
    "address", ["dse_na4@docusign.net", "c_0001example@group.calendar.google.com", ASHBY]
)
def test_a_shared_system_is_never_obvious_noise(address: str) -> None:
    evidence = EmailThreadEvidence(
        sender_addresses=(address,),
        subjects=("Invitation",),
        has_list_unsubscribe=True,
        has_owner_message=False,
    )

    assert judge_email_thread(evidence, JOB_SEARCH_RULES) is Relevance.UNSURE


# --- a hiring system writing under the company's own domain (Acme) ---------

ACME_KEY = "no-reply@acmecareers.example#acme"


def test_both_acme_machine_addresses_become_one_company_record() -> None:
    applied = _sender(
        "notification@acmecareers.example",
        "Acme",
        subject="Thank you for applying to Acme",
    )
    invited = _sender(
        "notifications@acmecareers.example",
        "notifications",
        subject="Video interview - Sam Rivera and Acme",
    )

    assert applied == RelayedSender(ACME_KEY, "Acme Hiring Team", "Acme")
    assert invited == RelayedSender(ACME_KEY, "Acme Hiring Team", "Acme")
    assert is_relay_identity(ACME_KEY, JOB_SEARCH_RULES)


def test_with_nothing_else_to_go_on_the_company_is_read_from_the_domain() -> None:
    sender = _sender("no-reply@acmecareers.example", "", subject="Your interview is confirmed")

    assert sender == RelayedSender(ACME_KEY, "Acme Hiring Team", "Acme")


def test_a_companys_machine_mail_that_is_not_about_an_application_is_left_alone() -> None:
    sender = _sender("notifications@acmecareers.example", "Acme", subject="New jobs for you")

    assert sender == RelayedSender("notifications@acmecareers.example", "Acme")
    assert not is_relay_identity(sender.identifier, JOB_SEARCH_RULES)


def test_a_person_at_the_company_is_never_a_company_record() -> None:
    sender = _sender("chloe.garner@acmegroup.example", "Chloe Garner", subject="Acme")

    assert sender == RelayedSender("chloe.garner@acmegroup.example", "Chloe Garner")


@pytest.mark.parametrize(
    ("subject", "company"),
    [
        ("Video interview - Sam Rivera and Acme", "Acme"),
        ("Interview with Acme - next steps", "Acme"),
    ],
)
def test_the_company_is_read_from_an_interview_title(subject: str, company: str) -> None:
    assert company_from_subject(subject, JOB_SEARCH_RULES) == company
