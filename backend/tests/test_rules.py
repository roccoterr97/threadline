"""Rule packs: job-search rules keep their behaviour; other presets rescue no hiring mail."""

from __future__ import annotations

from typing import Final

import pytest

from tests.conftest import JOB_SEARCH_RULES
from tracker.domain.enums import Relevance
from tracker.domain.own_meetings import company_in_title, is_own_meeting
from tracker.domain.prefilter import (
    EmailThreadEvidence,
    is_relay_sender,
    is_work_system_sender,
    judge_email_thread,
)
from tracker.domain.relay import real_sender
from tracker.domain.rules import DEFAULT_TEAM_LABEL, RulePack
from tracker.services.profile.loader import preset_names, preset_path, read_profile

SALES_RULES: Final[RulePack] = read_profile(preset_path("sales_outreach")).rules
NO_RULES: Final[RulePack] = RulePack()

ASHBY_MAIL = EmailThreadEvidence(
    sender_addresses=("no-reply@ashbyhq.com",),
    subjects=("Your interview with Northwind AI",),
    has_list_unsubscribe=True,
)

COMPANY_APPLICATION_MAIL = EmailThreadEvidence(
    sender_addresses=("notification@acmecareers.example",),
    subjects=("Thank you for applying to Acme",),
    has_list_unsubscribe=True,
)

BOOKING_MAIL = EmailThreadEvidence(
    sender_addresses=("no-reply@calendly.com",),
    subjects=("New event: Demo with Northwind",),
    has_list_unsubscribe=True,
)


def _not_owner(_address: str) -> bool:
    return False


@pytest.mark.parametrize("name", preset_names())
def test_every_preset_carries_a_valid_rule_pack(name: str) -> None:
    rules = read_profile(preset_path(name)).rules

    assert all(pattern.groupindex.get("company") for pattern in rules.company_subjects)
    assert "calendly.com" in rules.system_sender_domains


def test_the_job_search_pack_holds_the_hiring_lists() -> None:
    assert len(JOB_SEARCH_RULES.system_sender_domains) == 17
    assert "ashbyhq.com" in JOB_SEARCH_RULES.system_sender_domains
    assert "greenhouse" in JOB_SEARCH_RULES.platform_names
    assert JOB_SEARCH_RULES.team_suffixes[0] == "recruiting team"
    assert JOB_SEARCH_RULES.team_label == "Hiring Team"
    assert len(JOB_SEARCH_RULES.company_subjects) == 4
    assert len(JOB_SEARCH_RULES.work_subjects) == 10
    assert "interview" in JOB_SEARCH_RULES.own_meeting_words


def test_hiring_system_mail_is_rescued_for_a_job_search_only() -> None:
    assert judge_email_thread(ASHBY_MAIL, JOB_SEARCH_RULES) is Relevance.UNSURE
    assert judge_email_thread(ASHBY_MAIL, SALES_RULES) is Relevance.NOISE


def test_a_companys_application_mail_is_rescued_for_a_job_search_only() -> None:
    assert judge_email_thread(COMPANY_APPLICATION_MAIL, JOB_SEARCH_RULES) is Relevance.UNSURE
    assert judge_email_thread(COMPANY_APPLICATION_MAIL, SALES_RULES) is Relevance.NOISE


def test_booking_tools_stay_useful_for_sales() -> None:
    assert judge_email_thread(BOOKING_MAIL, SALES_RULES) is Relevance.UNSURE
    assert is_work_system_sender("no-reply@calendly.com", SALES_RULES)


def test_with_no_pack_only_the_general_rules_apply() -> None:
    assert judge_email_thread(BOOKING_MAIL, NO_RULES) is Relevance.NOISE
    assert is_relay_sender("dse_NA4@docusign.net", NO_RULES)
    assert not is_relay_sender("no-reply@ashbyhq.com", NO_RULES)


def test_a_hiring_system_is_only_a_shared_sender_for_a_job_search() -> None:
    assert is_relay_sender("no-reply@ashbyhq.com", JOB_SEARCH_RULES)
    assert not is_relay_sender("no-reply@ashbyhq.com", SALES_RULES)


def test_a_company_behind_a_shared_sender_is_shown_with_the_packs_team_label() -> None:
    hiring = real_sender(
        "no-reply@ashbyhq.com",
        "",
        (),
        "Thank you for applying to Tasko",
        _not_owner,
        JOB_SEARCH_RULES,
    )

    assert hiring.display_name == "Tasko Hiring Team"
    assert hiring.organisation_name == "Tasko"
    assert NO_RULES.team_label == DEFAULT_TEAM_LABEL


def test_own_calendar_entries_follow_the_packs_meeting_words() -> None:
    assert is_own_meeting("Video interview - Acme", JOB_SEARCH_RULES)
    assert not is_own_meeting("Video interview - Acme", SALES_RULES)
    assert is_own_meeting("Demo - Northwind", SALES_RULES)
    assert company_in_title("Demo - Northwind", ["Sam Rivera"], SALES_RULES) == "Northwind"
    assert not is_own_meeting("Flight to Lisbon", NO_RULES)


def test_a_broken_pattern_is_refused() -> None:
    with pytest.raises(ValueError, match="not a valid pattern"):
        RulePack(work_subject_patterns=("(unclosed",))


def test_a_company_pattern_must_name_the_company() -> None:
    with pytest.raises(ValueError, match="company"):
        RulePack(company_subject_patterns=(r"\bapplying to (\w+)",))
