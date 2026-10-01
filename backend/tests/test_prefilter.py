"""The obvious-noise rules: machine mail, adverts, and the owner's own replies."""

from __future__ import annotations

import pytest

from tests.conftest import JOB_SEARCH_RULES
from tracker.domain.enums import Relevance
from tracker.domain.prefilter import (
    EmailThreadEvidence,
    LinkedInThreadEvidence,
    is_linkedin_advert_folder,
    is_machine_sender,
    is_own_summary_email,
    is_work_subject,
    judge_email_thread,
    judge_linkedin_thread,
)


@pytest.mark.parametrize(
    "address",
    [
        "no-reply@news.example",
        "noreply@shop.example",
        "notifications@platform.example",
        "newsletter@weekly.example",
        "news-digest@weekly.example",
        "alerts@monitor.example",
        "invoice.2026@billing.example",
        "messages-noreply@linkedin.com",
        "someone@e.linkedin.com",
    ],
)
def test_machine_senders_are_recognised(address: str) -> None:
    assert is_machine_sender(address) is True


@pytest.mark.parametrize(
    "address",
    [
        "elodie.martin@acme.example",
        "newsom@founders.example",
        "info@startup.example",
        "hello@startup.example",
        "contact@startup.example",
        "not-an-address",
    ],
)
def test_people_are_not_mistaken_for_machines(address: str) -> None:
    assert is_machine_sender(address) is False


#: A made-up configured prefix; the real one comes from SUMMARY_SUBJECT_PREFIX.
PREFIX = "[Weekly Desk]"


def test_the_tracker_recognises_its_own_summary() -> None:
    assert is_own_summary_email(f"{PREFIX} your morning summary", PREFIX) is True
    assert is_own_summary_email(f"{PREFIX.upper()} your morning summary", PREFIX) is True
    assert is_own_summary_email("a morning summary from a friend", PREFIX) is False


@pytest.mark.parametrize("prefix", [None, "", "   "])
def test_a_missing_prefix_never_hides_real_mail(prefix: str | None) -> None:
    assert is_own_summary_email("Coffee next week?", prefix) is False


def test_a_summary_is_not_recognised_when_no_prefix_is_given() -> None:
    evidence = EmailThreadEvidence(
        sender_addresses=("sam.other@mailer.example",),
        subjects=(f"{PREFIX} 3 people are waiting",),
    )

    assert judge_email_thread(evidence, JOB_SEARCH_RULES) is Relevance.UNSURE


@pytest.mark.parametrize(
    "folder",
    ["SPONSORED_INMAIL", "sponsored inmail", "MESSAGE_ADS", "InMail/Promotions"],
)
def test_advert_folders_are_recognised(folder: str) -> None:
    assert is_linkedin_advert_folder(folder) is True


@pytest.mark.parametrize("folder", ["INBOX", "ARCHIVE", "", "Broadside"])
def test_ordinary_folders_are_not_adverts(folder: str) -> None:
    assert is_linkedin_advert_folder(folder) is False


def test_a_newsletter_is_noise() -> None:
    evidence = EmailThreadEvidence(
        sender_addresses=("weekly@startupdigest.example",),
        subjects=("This week in hiring",),
        has_list_unsubscribe=True,
    )

    assert judge_email_thread(evidence, JOB_SEARCH_RULES) is Relevance.NOISE


def test_a_thread_the_owner_wrote_in_is_never_auto_noise() -> None:
    evidence = EmailThreadEvidence(
        sender_addresses=("newsletter@weekly.example",),
        subjects=("This week in hiring",),
        has_list_unsubscribe=True,
        has_owner_message=True,
    )

    assert judge_email_thread(evidence, JOB_SEARCH_RULES) is Relevance.UNSURE


def test_the_trackers_own_summary_is_noise() -> None:
    evidence = EmailThreadEvidence(
        sender_addresses=("sam.other@mailer.example",),
        subjects=(f"{PREFIX} 3 people are waiting",),
        summary_subject_prefix=PREFIX,
    )

    assert judge_email_thread(evidence, JOB_SEARCH_RULES) is Relevance.NOISE


def test_a_human_thread_is_left_to_the_assessment() -> None:
    evidence = EmailThreadEvidence(
        sender_addresses=("elodie.martin@acme.example",),
        subjects=("Coffee next week?",),
    )

    assert judge_email_thread(evidence, JOB_SEARCH_RULES) is Relevance.UNSURE


def test_a_thread_with_one_machine_sender_among_people_is_not_noise() -> None:
    evidence = EmailThreadEvidence(
        sender_addresses=("noreply@ats.example", "elodie.martin@acme.example"),
        subjects=("Your application",),
    )

    assert judge_email_thread(evidence, JOB_SEARCH_RULES) is Relevance.UNSURE


def test_an_advert_without_a_reply_is_noise() -> None:
    evidence = LinkedInThreadEvidence(folders=("SPONSORED_INMAIL",))

    assert judge_linkedin_thread(evidence) is Relevance.NOISE


def test_an_advert_the_owner_answered_is_kept() -> None:
    evidence = LinkedInThreadEvidence(folders=("SPONSORED_INMAIL",), has_owner_message=True)

    assert judge_linkedin_thread(evidence) is Relevance.UNSURE


def test_an_interview_invitation_is_not_thrown_away_as_machine_mail() -> None:
    """Hiring systems look exactly like newsletters, and carry the job search.

    Ashby, Lever, Greenhouse and the scheduling tools send from a no-reply
    address with an unsubscribe header. Twenty-eight such e-mails in nine days
    were discarded with no text kept, including the one naming an interview at
    13:00 on 21 September.
    """
    evidence = EmailThreadEvidence(
        sender_addresses=("no-reply@ashbyhq.com",),
        subjects=("Your interview with Railfreight",),
        has_list_unsubscribe=True,
        has_owner_message=False,
    )

    assert judge_email_thread(evidence, JOB_SEARCH_RULES) is Relevance.UNSURE


def test_a_real_newsletter_is_still_thrown_away() -> None:
    evidence = EmailThreadEvidence(
        sender_addresses=("no-reply@startupweekly.example",),
        subjects=("This week in hiring",),
        has_list_unsubscribe=True,
        has_owner_message=False,
    )

    assert judge_email_thread(evidence, JOB_SEARCH_RULES) is Relevance.NOISE


# --- a company's own hiring mail ----------------------------------------


@pytest.mark.parametrize(
    ("address", "subject"),
    [
        ("notification@acmecareers.example", "Thank you for applying to Acme"),
        ("notifications@acmecareers.example", "Video interview - Sam Rivera and Acme"),
    ],
)
def test_a_companys_own_application_mail_is_left_to_the_assessment(
    address: str, subject: str
) -> None:
    evidence = EmailThreadEvidence(
        sender_addresses=(address,),
        subjects=(subject,),
        has_list_unsubscribe=True,
    )

    assert judge_email_thread(evidence, JOB_SEARCH_RULES) is Relevance.UNSURE


@pytest.mark.parametrize(
    "subject",
    [
        "Thanks for your application",
        "Your application to Acme",
        "Application received",
        "An update on your application",
        "Entretien avec Banko",
        "Colloquio conoscitivo",
        "La tua candidatura",
        "Votre candidature chez Alan",
        "Ihre Bewerbung",
    ],
)
def test_application_phrasings_are_recognised(subject: str) -> None:
    assert is_work_subject(subject, JOB_SEARCH_RULES)


@pytest.mark.parametrize(
    "subject",
    ["New jobs for you", "This week in hiring", "10 jobs matching Product Manager"],
)
def test_job_alerts_are_not_application_mail(subject: str) -> None:
    assert not is_work_subject(subject, JOB_SEARCH_RULES)


def test_a_job_alert_from_a_company_domain_is_still_noise() -> None:
    evidence = EmailThreadEvidence(
        sender_addresses=("notifications@acmecareers.example",),
        subjects=("New jobs for you",),
        has_list_unsubscribe=True,
    )

    assert judge_email_thread(evidence, JOB_SEARCH_RULES) is Relevance.NOISE


def test_the_trackers_own_summary_mentioning_an_interview_is_still_noise() -> None:
    evidence = EmailThreadEvidence(
        sender_addresses=("no-reply@tracker.example",),
        subjects=(f"{PREFIX} Interview with Acme today",),
        summary_subject_prefix=PREFIX,
    )

    assert judge_email_thread(evidence, JOB_SEARCH_RULES) is Relevance.NOISE


def test_a_platforms_own_application_mail_is_not_rescued() -> None:
    evidence = EmailThreadEvidence(
        sender_addresses=("jobs-noreply@linkedin.com",),
        subjects=("Your application to Product Manager at Acme",),
        has_list_unsubscribe=True,
    )

    assert judge_email_thread(evidence, JOB_SEARCH_RULES) is Relevance.NOISE
