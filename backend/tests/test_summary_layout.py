"""The formatted e-mail: links to the dashboard, tables, and nothing unsafe."""

from __future__ import annotations

from datetime import UTC, date, datetime

from tracker.domain.enums import RunStatus, RunStep
from tracker.schemas.summary import SummaryContent, SummaryPerson, SummaryProblem
from tracker.services.summary.html_layout import render_html

NOW = datetime(2026, 9, 21, 5, 3, tzinfo=UTC)
URL = "https://tracker.example"


PRODUCT = "Weekly Desk"


def _content(**changes: object) -> SummaryContent:
    base = {"generated_at": NOW, "day": NOW.date(), "run_status": RunStatus.SUCCESS}
    return SummaryContent(**{**base, **changes})  # pyright: ignore[reportArgumentType]


def _html(summary: SummaryContent) -> str:
    return render_html(summary, PRODUCT)


def _anna(**changes: object) -> SummaryPerson:
    base = {"name": "Anna Vermeer", "organisation": "Acme"}
    return SummaryPerson(**{**base, **changes})  # pyright: ignore[reportArgumentType]


def test_the_top_of_the_email_has_a_button_to_the_dashboard() -> None:
    html = _html(_content(dashboard_url=URL))

    assert f"href='{URL}'" in html
    assert "Open the dashboard" in html


def test_names_are_not_links_so_they_cannot_point_at_the_wrong_person() -> None:
    """The sender types the body out; a long identifier in a link got copied wrong."""
    html = _html(_content(do_today=(_anna(),), do_today_total=1, dashboard_url=URL))

    assert "/people/" not in html


def test_a_section_is_a_table_with_person_next_step_and_due() -> None:
    html = _html(
        _content(
            overdue=(_anna(next_action="Send the deck", due_date=date(2026, 9, 9)),),
            overdue_total=1,
        )
    )

    for column in ("Person", "Next step", "Due"):
        assert f">{column}</th>" in html
    assert "Send the deck" in html
    assert "9 Sep 2026" in html
    assert "Acme" in html


def test_the_tiles_show_the_four_counts() -> None:
    html = _html(_content(do_today_total=1, overdue_total=2, chase_total=40, open_questions=3))

    for label in ("do today", "overdue", "to chase", "to review"):
        assert f">{label}</div>" in html
    assert ">40</div>" in html


def test_chase_dates_are_calm_while_overdue_dates_are_red() -> None:
    late = _anna(due_date=date(2026, 9, 9))
    chase_only = _html(_content(chase=(late,), chase_total=1))
    overdue_only = _html(_content(overdue=(late,), overdue_total=1))

    assert "Time to chase (1)" in chase_only
    assert "#b91c1c'>9 Sep 2026" not in chase_only
    assert "#b91c1c'>9 Sep 2026" in overdue_only


def test_a_long_section_ends_with_a_link_to_the_rest() -> None:
    html = _html(_content(overdue=(_anna(),), overdue_total=24, dashboard_url=URL))

    assert "and 23 more on the dashboard" in html


def test_waiting_questions_get_a_button_to_the_review_page() -> None:
    html = _html(_content(open_questions=2, dashboard_url=URL))

    assert "2 questions waiting for a yes or no" in html
    assert f"href='{URL}/review'" in html


def test_a_problem_is_shown_in_the_attention_box() -> None:
    problem = SummaryProblem(
        step=RunStep.COLLECT_EMAIL,
        what_happened="The mailbox was not read.",
        what_to_do="Sign in again.",
    )
    html = _html(_content(run_status=RunStatus.PARTIAL, problems=(problem,)))

    assert "Something needs your attention" in html
    assert "The mailbox was not read." in html


def test_without_a_dashboard_address_there_is_no_link_at_all() -> None:
    html = _html(_content(do_today=(_anna(),), do_today_total=1, open_questions=2))

    assert "href" not in html


def test_text_from_outside_cannot_become_html() -> None:
    html = _html(
        _content(
            do_today=(_anna(name="<b>x</b>", organisation="<i>", next_action="'><script>"),),
            do_today_total=1,
            dashboard_url=URL,
        )
    )

    assert "<script>" not in html
    assert "<b>x</b>" not in html
    assert "&lt;b&gt;x&lt;/b&gt;" in html


def test_the_day_is_written_with_its_weekday() -> None:
    assert "Mon 21 Sep 2026" in _html(_content())
