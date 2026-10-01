"""The words the summary uses: subjects, sections, and problems in plain English."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from tracker.domain.enums import RunStatus, RunStep
from tracker.schemas.summary import SummaryContent, SummaryEmail, SummaryPerson, SummaryProblem
from tracker.services.summary.problem_messages import explain
from tracker.services.summary.renderer import build_subject, format_day, render_email
from tracker.services.summary.wording import Branding

NOW = datetime(2026, 9, 18, 5, 30, tzinfo=UTC)

#: Made-up owner settings; the real ones come from the configuration.
PREFIX = "[Weekly Desk]"
RECIPIENT = "sam.rivera@mailbox.example"
BRANDING = Branding(product_name="Weekly Desk", subject_prefix=PREFIX)


def content(**changes: object) -> SummaryContent:
    """A summary of a clean, quiet morning, with the given changes applied."""
    base = {"generated_at": NOW, "day": NOW.date(), "run_status": RunStatus.SUCCESS}
    return SummaryContent(**{**base, **changes})  # pyright: ignore[reportArgumentType]


def subject_of(summary: SummaryContent) -> str:
    """The subject line, with the made-up prefix."""
    return build_subject(summary, PREFIX)


def email_of(summary: SummaryContent) -> SummaryEmail:
    """The whole e-mail, addressed and branded with the made-up settings."""
    return render_email(summary, RECIPIENT, BRANDING)


def person(name: str, **changes: object) -> SummaryPerson:
    """One person for a section."""
    return SummaryPerson(name=name, **changes)  # pyright: ignore[reportArgumentType]


def test_every_subject_starts_with_the_prefix_the_collector_ignores() -> None:
    subject = subject_of(content())

    assert subject.startswith(PREFIX)


def test_a_quiet_morning_says_so_in_the_subject() -> None:
    assert subject_of(content()) == f"{PREFIX} nothing needs you today"


def test_the_subject_counts_the_actions_and_the_overdue_follow_ups() -> None:
    subject = subject_of(
        content(
            do_today=(person("Anna"), person("Bruno"), person("Clara")),
            do_today_total=3,
            overdue=(person("Diego"), person("Elena")),
            overdue_total=2,
        )
    )

    assert subject == f"{PREFIX} 3 actions for you · 2 overdue"


def test_the_subject_counts_the_people_to_chase_and_leaves_out_zeros() -> None:
    subject = subject_of(
        content(
            do_today=(person("Anna"),),
            do_today_total=1,
            chase=(person("Bruno"),),
            chase_total=40,
        )
    )

    assert subject == f"{PREFIX} 1 action for you · 40 to chase"


def test_one_action_is_not_written_as_one_actions() -> None:
    subject = subject_of(content(do_today=(person("Anna"),), do_today_total=1))

    assert subject == f"{PREFIX} 1 action for you"


def test_a_run_that_went_wrong_says_so_in_the_subject() -> None:
    subject = subject_of(content(run_status=RunStatus.PARTIAL))

    assert "something needs your attention" in subject


def test_the_body_names_the_person_their_organisation_action_and_date() -> None:
    email = email_of(
        content(
            do_today=(
                person(
                    "Anna Vermeer",
                    organisation="Northwind Robotics",
                    next_action="Send the slides",
                    due_date=date(2026, 10, 8),
                ),
            ),
            do_today_total=1,
        )
    )

    assert "Anna Vermeer (Northwind Robotics) — Send the slides — due 8 Oct 2026" in (
        email.text_body
    )


def test_an_empty_section_says_nobody_rather_than_disappearing() -> None:
    email = email_of(content())

    assert "Do today\n- nobody" in email.text_body
    assert "Overdue: replies you owe\n- nobody" in email.text_body
    assert "Time to chase\n- nobody" in email.text_body


def test_a_long_list_is_cut_with_a_line_pointing_at_the_dashboard() -> None:
    email = email_of(content(do_today=(person("Anna"), person("Bruno")), do_today_total=25))

    assert "and 23 more on the dashboard" in email.text_body


def test_the_review_section_links_to_the_review_page() -> None:
    email = email_of(content(open_questions=2, dashboard_url="https://tracker.example"))

    assert "2 questions waiting for a yes or no" in email.text_body
    assert "https://tracker.example/review" in email.text_body


def test_no_link_is_written_until_the_dashboard_has_an_address() -> None:
    """An unset address must not become somebody else's website.

    The generic address the constant used to hold belongs to a stranger, and
    two summaries went out pointing at it.
    """
    email = email_of(content(open_questions=2))

    assert "2 questions waiting for a yes or no" in email.text_body
    assert "http" not in email.text_body
    assert "href" not in email.html_body


def test_the_summary_is_addressed_to_the_configured_recipient() -> None:
    email = email_of(content())

    assert email.recipient == RECIPIENT
    assert email.subject_prefix == PREFIX
    assert email.subject.startswith(email.subject_prefix)


def test_a_name_with_angle_brackets_cannot_become_html() -> None:
    email = email_of(
        content(do_today=(person("Anna <script>alert(1)</script>"),), do_today_total=1)
    )

    assert "<script>" not in email.html_body
    assert "&lt;script&gt;" in email.html_body


def test_a_date_is_written_the_way_a_person_writes_it() -> None:
    assert format_day(date(2026, 10, 8)) == "8 Oct 2026"


def test_the_attention_section_comes_first_and_carries_both_sentences() -> None:
    problem = SummaryProblem(
        step=RunStep.COLLECT_EMAIL,
        what_happened="Your mailbox could not be read this morning.",
        what_to_do="Sign in to Microsoft once more.",
    )

    email = email_of(content(run_status=RunStatus.PARTIAL, problems=(problem,)))

    assert email.text_body.startswith("Something needs your attention")
    assert problem.what_happened in email.text_body
    assert problem.what_to_do in email.text_body


@pytest.mark.parametrize(
    ("step", "code", "expected"),
    [
        (RunStep.COLLECT_LINKEDIN, "source_auth_failed", "LinkedIn key"),
        (RunStep.COLLECT_EMAIL, "source_auth_failed", "Microsoft"),
        (RunStep.COLLECT_EMAIL, "source_unavailable", "next run tries again"),
        (RunStep.ASSESS, "tracker_error", "next run tries again"),
        (RunStep.COLLECT_LINKEDIN, "configuration_invalid", "docs/operations.md"),
    ],
)
def test_each_failure_names_what_to_do_about_it(step: RunStep, code: str, expected: str) -> None:
    problem = explain(step, code)

    assert expected in problem.what_to_do


@pytest.mark.parametrize("step", [RunStep.COLLECT_EMAIL, RunStep.COLLECT_CALENDAR])
@pytest.mark.parametrize("code", ["source_auth_failed", "source_unavailable", "tracker_error"])
def test_problems_name_no_particular_mail_provider(step: RunStep, code: str) -> None:
    problem = explain(step, code)
    words = f"{problem.what_happened} {problem.what_to_do}"

    assert "Hotmail" not in words
    assert "Outlook" not in words


def test_a_code_nobody_wrote_a_sentence_for_still_reads_as_english() -> None:
    problem = explain(RunStep.SUMMARY_EMAIL, "a_brand_new_code")

    assert "a_brand_new_code" not in problem.what_happened + problem.what_to_do
    assert problem.what_happened
    assert problem.what_to_do


def test_a_missing_code_is_explained_by_the_step_alone() -> None:
    problem = explain(RunStep.COLLECT_LINKEDIN, None)

    assert "LinkedIn" in problem.what_happened


def test_a_run_that_never_started_is_explained_without_naming_a_step() -> None:
    problem = explain(None, None)

    assert problem.step is None
    assert "stopped before it could read anything" in problem.what_happened


def test_a_sender_cannot_forge_a_section_of_the_e_mail() -> None:
    """A display name is written by somebody else and reaches the e-mail body.

    The plain-text body is built line by line, so a name carrying a line break
    could add lines of its own — a forged heading with a link of the sender's
    choosing, inside an e-mail the owner trusts.
    """
    forged = "Marco Rossi\n\nSomething needs your attention\n- Confirm here: https://evil.example"

    person = SummaryPerson(name=forged, organisation="ACME\nInc", next_action="Reply\nnow")

    assert "\n" not in person.name
    assert "\n" not in (person.organisation or "")
    assert "\n" not in (person.next_action or "")
    assert person.name.startswith("Marco Rossi")
