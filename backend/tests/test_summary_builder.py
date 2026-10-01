"""What the morning summary says, built from the sample data."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest

from tests.conftest import JOB_SEARCH_RULES, as_client
from tests.summary_world import (
    NOW,
    TODAYS_RUN,
    YESTERDAYS_RUN,
    overview_rows,
    sample_client,
    sample_data,
)
from tracker.domain.enums import Relevance, RunStatus, RunStep, RunTrigger
from tracker.domain.prefilter import EmailThreadEvidence, judge_email_thread
from tracker.repositories import build_repositories
from tracker.schemas.summary import SummaryEmail, SummaryPerson
from tracker.services.summary.builder import SummaryBuilder
from tracker.shared.clock import FixedClock
from tracker.shared.config import Settings
from tracker.shared.constants.runs import RUN_INTERRUPTED_CODE
from tracker.shared.constants.summary import KEY_REMINDER_DAYS
from tracker.shared.errors import ValidationFailedError


def build(
    settings: Settings,
    run_id: UUID = TODAYS_RUN,
    clock: FixedClock | None = None,
) -> SummaryEmail:
    """Build the summary of one run against the sample data."""
    repositories = build_repositories(as_client(sample_client()))
    builder = SummaryBuilder(repositories, settings, clock or FixedClock(NOW))
    return builder.build(run_id)


def names(people: tuple[SummaryPerson, ...]) -> list[str]:
    """The names in one section, in the order the summary lists them."""
    return [person.name for person in people]


def test_the_summary_goes_to_the_first_owner_address_by_default(settings: Settings) -> None:
    assert settings.summary_recipient is None
    assert build(settings).recipient == "sam.rivera@mailbox.example"


def test_a_configured_recipient_wins_over_the_owner_addresses(settings: Settings) -> None:
    elsewhere = settings.model_copy(update={"summary_recipient": "desk@inbox.example"})

    assert build(elsewhere).recipient == "desk@inbox.example"


def test_the_subject_and_the_brand_follow_the_configuration(settings: Settings) -> None:
    branded = settings.model_copy(
        update={"summary_subject_prefix": "[Weekly Desk]", "product_name": "Weekly Desk"}
    )

    email = build(branded)

    assert email.subject.startswith("[Weekly Desk] ")
    assert email.subject_prefix == "[Weekly Desk]"
    assert "Weekly Desk" in email.html_body


def test_the_mailbox_ignores_the_summary_with_the_prefix_it_was_sent_with(
    settings: Settings,
) -> None:
    """One setting feeds both the subject and the collector: nothing to keep in step."""
    branded = settings.model_copy(update={"summary_subject_prefix": "[Weekly Desk]"})
    email = build(branded)

    evidence = EmailThreadEvidence(
        sender_addresses=("sender@mailer.example",),
        subjects=(email.subject,),
        summary_subject_prefix=branded.summary_subject_prefix,
    )

    assert judge_email_thread(evidence, JOB_SEARCH_RULES) is Relevance.NOISE


def test_the_summary_is_dated_on_the_owners_day(settings: Settings) -> None:
    late_evening = datetime(2026, 9, 18, 23, 30, tzinfo=UTC)
    tokyo = FixedClock(late_evening, ZoneInfo("Asia/Tokyo"))
    los_angeles = FixedClock(late_evening, ZoneInfo("America/Los_Angeles"))

    assert build(settings, clock=tokyo).content.day == date(2026, 9, 19)
    assert "Sat 19 Sep 2026" in build(settings, clock=tokyo).html_body
    assert build(settings, clock=los_angeles).content.day == date(2026, 9, 18)


def test_the_key_reminder_counts_days_on_the_owners_calendar(settings: Settings) -> None:
    # 23:30 UTC on the 18th is the 19th in Tokyo, so a key ending on the 25th
    # has six days left there, not seven.
    expiring = settings.model_copy(update={"linkedin_token_expires_on": date(2026, 9, 25)})
    tokyo = FixedClock(datetime(2026, 9, 18, 23, 30, tzinfo=UTC), ZoneInfo("Asia/Tokyo"))

    reminder = build(expiring, clock=tokyo).content.key_reminder

    assert reminder is not None
    assert "in 6 days" in reminder


def test_no_key_reminder_when_linkedin_was_never_set_up(settings: Settings) -> None:
    unused = settings.model_copy(
        update={
            "linkedin_access_token": None,
            "linkedin_token_expires_on": NOW.date() + timedelta(days=2),
        }
    )

    assert build(unused).content.key_reminder is None


def test_do_today_lists_exactly_the_people_waiting_on_the_owner(settings: Settings) -> None:
    email = build(settings)

    assert names(email.content.do_today) == ["Luca Moretti", "Hugo Martins", "Elena Rossi"]
    assert email.content.do_today_total == 3


def test_do_today_carries_the_organisation_and_the_next_action(settings: Settings) -> None:
    first = build(settings).content.do_today[0]

    assert first.organisation == "Tidal Logistics"
    assert first.next_action == "Send the availability slots today"
    assert first.due_date == date(2026, 9, 19)


def test_overdue_lists_only_the_late_replies_the_owner_owes(settings: Settings) -> None:
    email = build(settings)

    assert names(email.content.overdue) == ["Clara Nyman"]
    assert email.content.overdue_total == 1


def test_time_to_chase_lists_the_people_who_owe_a_reply_past_the_chase_date(
    settings: Settings,
) -> None:
    email = build(settings)

    assert names(email.content.chase) == ["Diego Ferrari"]
    assert email.content.chase_total == 1


def test_nobody_is_both_overdue_and_to_chase(settings: Settings) -> None:
    content = build(settings).content

    assert not set(names(content.overdue)) & set(names(content.chase))


def test_a_late_date_with_nothing_owed_is_neither_overdue_nor_to_chase() -> None:
    rows = overview_rows(sample_data(), today=NOW.date() + timedelta(days=365))
    nobody = [row for row in rows if row["waiting_on"] == "nobody" and row["due_date"]]

    assert nobody
    assert not any(row["is_overdue"] or row["is_chase_due"] for row in nobody)


def test_somebody_overdue_and_waiting_on_the_owner_is_listed_once(settings: Settings) -> None:
    email = build(settings)

    assert "Clara Nyman" in names(email.content.overdue)
    assert "Clara Nyman" not in names(email.content.do_today)


def test_the_summary_counts_the_questions_still_waiting_for_an_answer(
    settings: Settings,
) -> None:
    assert build(settings).content.open_questions == 2


def test_the_replied_section_lists_who_wrote_back_since_the_previous_run(
    settings: Settings,
) -> None:
    email = build(settings)

    assert names(email.content.replied) == ["Greta Lindqvist"]


def test_a_refresh_between_two_mornings_does_not_shorten_the_replied_section(
    settings: Settings,
) -> None:
    client = sample_client()
    client.tables["run_logs"].append(
        {
            "id": str(uuid4()),
            "started_at": "2026-09-17T12:00:00Z",
            "finished_at": "2026-09-17T12:04:00Z",
            "status": "success",
            "trigger": RunTrigger.REFRESH.value,
        }
    )
    builder = SummaryBuilder(build_repositories(as_client(client)), settings, FixedClock(NOW))

    email = builder.build(TODAYS_RUN)

    assert names(email.content.replied) == ["Greta Lindqvist"]


def _with_interrupted_run(settings: Settings, started_at: str) -> SummaryBuilder:
    """The sample data plus an earlier run that was closed as interrupted at ``assess``."""
    client = sample_client()
    run_id = str(uuid4())
    client.tables["run_logs"].append(
        {
            "id": run_id,
            "started_at": started_at,
            "finished_at": "2026-09-18T05:00:00Z",
            "status": "failed",
            "trigger": RunTrigger.GITHUB.value,
        }
    )
    client.tables["run_step_logs"].append(
        {
            "id": str(uuid4()),
            "run_id": run_id,
            "step": RunStep.ASSESS.value,
            "status": "failed",
            "error_code": RUN_INTERRUPTED_CODE,
            "error_detail": None,
        }
    )
    return SummaryBuilder(build_repositories(as_client(client)), settings, FixedClock(NOW))


def test_an_earlier_run_that_was_interrupted_is_explained_in_plain_english(
    settings: Settings,
) -> None:
    builder = _with_interrupted_run(settings, "2026-09-17T12:00:00Z")

    email = builder.build(TODAYS_RUN)

    [interrupted] = [p for p in email.content.problems if p.step is RunStep.ASSESS]
    assert "stopped part-way and never finished" in interrupted.what_happened
    assert RUN_INTERRUPTED_CODE not in interrupted.what_happened + interrupted.what_to_do
    assert names(email.content.replied) == ["Greta Lindqvist"]


def test_an_interruption_an_earlier_summary_already_covered_is_not_repeated(
    settings: Settings,
) -> None:
    builder = _with_interrupted_run(settings, "2026-09-16T05:00:00Z")

    email = builder.build(TODAYS_RUN)

    assert all(problem.step is not RunStep.ASSESS for problem in email.content.problems)


def test_a_failed_mailbox_step_makes_the_run_partial(settings: Settings) -> None:
    assert build(settings).content.run_status is RunStatus.PARTIAL


def test_a_failed_mailbox_step_explains_the_microsoft_sign_in_in_plain_english(
    settings: Settings,
) -> None:
    problems = build(settings).content.problems

    assert len(problems) == 1
    assert problems[0].step is RunStep.COLLECT_EMAIL
    assert "Your mailbox" in problems[0].what_happened
    assert "Microsoft" in problems[0].what_to_do
    assert "source_auth_failed" not in problems[0].what_happened + problems[0].what_to_do


def test_a_failed_step_puts_the_attention_section_at_the_top_of_the_body(
    settings: Settings,
) -> None:
    email = build(settings)

    assert email.text_body.startswith("Something needs your attention")
    assert "something needs your attention" in email.subject


def test_the_other_source_still_reports_its_people_when_one_source_fails(
    settings: Settings,
) -> None:
    email = build(settings)

    assert email.content.do_today_total == 3
    assert email.content.overdue_total == 1
    assert email.content.chase_total == 1


def test_a_clean_run_carries_no_attention_section(settings: Settings) -> None:
    email = build(settings, YESTERDAYS_RUN)

    assert email.content.run_status is RunStatus.SUCCESS
    assert email.content.problems == ()
    assert "Something needs your attention" not in email.text_body


def test_a_run_that_recorded_no_step_says_so_instead_of_staying_silent(
    settings: Settings,
) -> None:
    data = sample_data()
    client = sample_client()
    client.tables["run_step_logs"] = []
    builder = SummaryBuilder(
        build_repositories(as_client(client)),
        settings,
        FixedClock(NOW),
    )

    email = builder.build(TODAYS_RUN)

    assert data["run_step_logs"]  # the fixture does hold steps; this run has none
    assert email.content.run_status is RunStatus.FAILED
    assert email.content.problems[0].step is None
    assert "stopped before it could read anything" in email.content.problems[0].what_happened


def test_a_run_that_does_not_exist_is_refused(settings: Settings) -> None:
    with pytest.raises(ValidationFailedError):
        build(settings, uuid4())


def test_the_linkedin_key_reminder_appears_a_week_before_the_date(
    settings: Settings,
) -> None:
    """The owner asked for a week's notice, repeated daily until renewed."""
    expiring = settings.model_copy(
        update={"linkedin_token_expires_on": NOW.date() + timedelta(days=6)}
    )

    email = build(expiring)

    assert email.content.key_reminder is not None
    assert "stops working in 6 days" in email.content.key_reminder
    assert "LinkedIn key" in email.text_body


def test_the_linkedin_key_reminder_stays_quiet_more_than_a_week_before(
    settings: Settings,
) -> None:
    expiring = settings.model_copy(
        update={"linkedin_token_expires_on": NOW.date() + timedelta(days=8)}
    )

    email = build(expiring)

    assert email.content.key_reminder is None
    assert "LinkedIn key" not in email.text_body


def test_the_reminder_window_is_the_constant_and_not_a_number_typed_twice(
    settings: Settings,
) -> None:
    on_the_edge = settings.model_copy(
        update={"linkedin_token_expires_on": NOW.date() + timedelta(days=KEY_REMINDER_DAYS)}
    )

    assert build(on_the_edge).content.key_reminder is not None


def test_an_expired_key_says_so_rather_than_counting_backwards(settings: Settings) -> None:
    expired = settings.model_copy(
        update={"linkedin_token_expires_on": NOW.date() - timedelta(days=3)}
    )

    reminder = build(expired).content.key_reminder
    assert reminder is not None
    assert reminder.startswith("The LinkedIn key expired on")


def test_no_reminder_at_all_when_no_expiry_date_is_configured(settings: Settings) -> None:
    assert build(settings).content.key_reminder is None


def test_the_summary_never_carries_message_text(settings: Settings) -> None:
    bodies = build(settings)
    stored_bodies = [
        message["body"] for message in sample_data()["messages"] if message.get("body")
    ]

    assert stored_bodies
    for body in stored_bodies:
        assert body not in bodies.text_body
        assert body not in bodies.html_body


def test_the_summary_reads_no_message_row_at_all(settings: Settings) -> None:
    client = sample_client()
    repositories = build_repositories(as_client(client))

    SummaryBuilder(repositories, settings, FixedClock(NOW)).build(TODAYS_RUN)

    assert "messages" not in {table for table, _ in client.executed}
