"""Turn the facts of a summary into a subject line and two bodies.

The wording lives in code and nowhere else: no session writes a sentence of the
morning e-mail, and no AI is asked to phrase it. The plain-text body is built
here; the formatted HTML body, with the same words, is built by
:mod:`tracker.services.summary.html_layout`.
"""

from __future__ import annotations

from typing import Final

from tracker.domain.enums import RunStatus
from tracker.schemas.summary import SummaryContent, SummaryEmail, SummaryPerson
from tracker.services.summary.html_layout import render_html
from tracker.services.summary.wording import (
    ATTENTION_HEADING,
    CHASE_HEADING,
    DO_TODAY_HEADING,
    KEY_HEADING,
    NO_QUESTIONS,
    NOBODY,
    OVERDUE_HEADING,
    REPLIED_HEADING,
    REVIEW_HEADING,
    Branding,
    count,
    format_day,
    more_on_dashboard,
    questions_waiting,
)
from tracker.shared.constants.summary import (
    DASHBOARD_REVIEW_PATH,
    DASHBOARD_RUNS_PATH,
)

__all__ = ["build_subject", "format_day", "render_email"]

_QUIET_SUBJECT: Final[str] = "nothing needs you today"
_ATTENTION_SUBJECT: Final[str] = "something needs your attention"
_SEPARATOR: Final[str] = " · "


def render_email(content: SummaryContent, recipient: str, branding: Branding) -> SummaryEmail:
    """Render the summary the owner receives.

    Args:
        content: What the summary says.
        recipient: Where it goes, as the owner configured it.
        branding: The product name and the subject prefix to use.

    Returns:
        The e-mail, ready to send as it stands.
    """
    return SummaryEmail(
        recipient=recipient,
        subject=build_subject(content, branding.subject_prefix),
        subject_prefix=branding.subject_prefix,
        text_body=_render_text(content),
        html_body=render_html(content, branding.product_name),
        content=content,
    )


def build_subject(content: SummaryContent, prefix: str) -> str:
    """Build the subject line.

    It always starts with Threadline's own prefix, which is what makes the
    mailbox collector ignore the summary on the next run.

    Args:
        content: What the summary says.
        prefix: The configured subject prefix.

    Returns:
        The subject line.
    """
    parts: list[str] = []
    if content.run_status is not RunStatus.SUCCESS:
        parts.append(_ATTENTION_SUBJECT)
    if content.do_today_total:
        parts.append(f"{count(content.do_today_total, 'action')} for you")
    if content.overdue_total:
        parts.append(f"{content.overdue_total} overdue")
    if content.chase_total:
        parts.append(f"{content.chase_total} to chase")
    if not parts:
        parts.append(_QUIET_SUBJECT)
    return f"{prefix} {_SEPARATOR.join(parts)}"


def _render_text(content: SummaryContent) -> str:
    """Render the plain-text body."""
    blocks: list[str] = []
    if content.dashboard_url is not None:
        blocks.append(f"Open the dashboard: {content.dashboard_url}")
    if content.problems:
        lines = [ATTENTION_HEADING]
        for problem in content.problems:
            lines.append(f"- {problem.what_happened}")
            lines.append(f"  {problem.what_to_do}")
        blocks.append("\n".join(lines))
    blocks.append(_text_people(DO_TODAY_HEADING, content.do_today, content.do_today_total))
    blocks.append(_text_people(OVERDUE_HEADING, content.overdue, content.overdue_total))
    blocks.append(_text_people(CHASE_HEADING, content.chase, content.chase_total))
    blocks.append(_text_people(REPLIED_HEADING, content.replied, content.replied_total))
    blocks.append(_text_review(content.open_questions, content.dashboard_url))
    if content.key_reminder is not None:
        blocks.append(f"{KEY_HEADING}\n- {content.key_reminder}")
    if content.dashboard_url is not None:
        blocks.append(f"Run page: {content.dashboard_url}{DASHBOARD_RUNS_PATH}")
    return "\n\n".join(blocks) + "\n"


def _text_people(heading: str, people: tuple[SummaryPerson, ...], total: int) -> str:
    """Render one people section as plain text."""
    if not people:
        return f"{heading}\n- {NOBODY}"
    lines = [f"{heading} ({total})"]
    lines.extend(f"- {_person_line(person)}" for person in people)
    hidden = total - len(people)
    if hidden > 0:
        lines.append(f"- {more_on_dashboard(hidden)}")
    return "\n".join(lines)


def _text_review(open_questions: int, dashboard_url: str | None) -> str:
    """Render the review section as plain text."""
    if not open_questions:
        return f"{REVIEW_HEADING}\n- {NO_QUESTIONS}"
    waiting = f"{REVIEW_HEADING}\n- {questions_waiting(open_questions)}"
    if dashboard_url is None:
        return waiting
    return f"{waiting}: {dashboard_url}{DASHBOARD_REVIEW_PATH}"


def _person_line(person: SummaryPerson) -> str:
    """Render one person as a single line: who, where, what, by when."""
    line = person.name
    if person.organisation:
        line += f" ({person.organisation})"
    if person.next_action:
        line += f" — {person.next_action}"
    if person.due_date is not None:
        line += f" — due {format_day(person.due_date)}"
    return line
