"""The HTML version of the morning summary: a card, number tiles and tables.

Mail apps are not browsers. Many, Outlook among them, drop ``<style>`` blocks and
ignore most modern layout, so everything here is built from tables with the
styling written on each element — the one approach every mail app renders the
same way. The words are the ones the plain-text body uses
(:mod:`tracker.services.summary.wording`); only the layout differs.

Every value that came from outside — a name, an organisation, a next action —
is escaped before it is placed in the page.
"""

from __future__ import annotations

from html import escape
from typing import Final

from tracker.schemas.summary import SummaryContent, SummaryPerson, SummaryProblem
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
    format_day,
    format_weekday,
    more_on_dashboard,
    questions_waiting,
)
from tracker.shared.constants.summary import (
    DASHBOARD_REVIEW_PATH,
    DASHBOARD_RUNS_PATH,
)

_FONT: Final[str] = "-apple-system,'Segoe UI',Helvetica,Arial,sans-serif"
_PAGE: Final[str] = "#f3f4f6"
_CARD: Final[str] = "#ffffff"
_INK: Final[str] = "#111827"
_MUTED: Final[str] = "#6b7280"
_RULE: Final[str] = "#e5e7eb"
_STRIPE: Final[str] = "#f9fafb"
_ACCENT: Final[str] = "#2563eb"
_ALERT: Final[str] = "#b91c1c"
_ALERT_BACKGROUND: Final[str] = "#fef2f2"
_NOTICE: Final[str] = "#b45309"
_NOTICE_BACKGROUND: Final[str] = "#fffbeb"
_CARD_WIDTH: Final[int] = 600
_TITLE: Final[str] = "Your conversations this morning"

#: Opening of a full-width layout table, left open so a style can follow.
_TABLE: Final[str] = "<table role='presentation' width='100%' cellpadding='0' cellspacing='0'"

#: Style of one cell in a people table, kept short because it repeats per row.
_CELL: Final[str] = f"padding:8px;border-bottom:1px solid {_RULE}"


def render_html(content: SummaryContent, product_name: str) -> str:
    """Render the summary as a formatted e-mail.

    Args:
        content: What the summary says.
        product_name: What Threadline calls itself, from the configuration.

    Returns:
        A complete HTML document.
    """
    url = content.dashboard_url
    rows = [
        _header(content, product_name),
        _tiles(content),
        _button("Open the dashboard", url) if url else "",
        _attention(content.problems),
        _people(DO_TODAY_HEADING, content.do_today, content.do_today_total, url, _INK),
        _people(OVERDUE_HEADING, content.overdue, content.overdue_total, url, _ALERT),
        _people(CHASE_HEADING, content.chase, content.chase_total, url, _MUTED),
        _people(REPLIED_HEADING, content.replied, content.replied_total, url, _INK),
        _review(content.open_questions, url),
        _key_reminder(content.key_reminder),
        _footer(url, product_name),
    ]
    body = "".join(f"<tr><td style='padding:0 28px'>{row}</td></tr>" for row in rows if row)
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width'></head>"
        f"<body style='margin:0;padding:0;background:{_PAGE}'>"
        f"{_TABLE} style='background:{_PAGE};font-family:{_FONT};color:{_INK}'><tr>"
        f"<td align='center' style='padding:24px 12px'>"
        f"{_TABLE} style='max-width:{_CARD_WIDTH}px;background:{_CARD};border-radius:12px;"
        f"border:1px solid {_RULE}'>{body}</table>"
        "</td></tr></table></body></html>"
    )


def _header(content: SummaryContent, product_name: str) -> str:
    """The brand line, the title and the owner's day."""
    return (
        f"<p style='margin:28px 0 4px;font-size:12px;letter-spacing:.08em;"
        f"text-transform:uppercase;color:{_MUTED}'>{escape(product_name)}</p>"
        f"<h1 style='margin:0;font-size:22px;line-height:1.3'>{_TITLE}</h1>"
        f"<p style='margin:4px 0 20px;font-size:14px;color:{_MUTED}'>"
        f"{format_weekday(content.day)}</p>"
    )


def _tiles(content: SummaryContent) -> str:
    """Four numbers side by side: what the morning holds at a glance."""
    tiles = (
        (content.do_today_total, "do today", _ACCENT),
        (content.overdue_total, "overdue", _ALERT if content.overdue_total else _MUTED),
        (content.chase_total, "to chase", _INK if content.chase_total else _MUTED),
        (content.open_questions, "to review", _NOTICE if content.open_questions else _MUTED),
    )
    cells = "".join(
        f"<td width='25%' align='center' style='padding:12px 4px;background:{_STRIPE};"
        f"border:4px solid {_CARD};border-radius:10px'>"
        f"<div style='font-size:26px;font-weight:700;color:{colour}'>{number}</div>"
        f"<div style='font-size:12px;color:{_MUTED}'>{label}</div></td>"
        for number, label, colour in tiles
    )
    return f"{_TABLE}><tr>{cells}</tr></table>"


def _button(label: str, href: str) -> str:
    """A large link that looks like a button in every mail app."""
    return (
        f"<table role='presentation' cellpadding='0' cellspacing='0' style='margin:20px 0 4px'>"
        f"<tr><td style='background:{_ACCENT};border-radius:8px'>"
        f"<a href='{escape(href, quote=True)}' style='display:inline-block;padding:12px 22px;"
        f"font-size:15px;font-weight:600;color:#ffffff;text-decoration:none'>{label}</a>"
        "</td></tr></table>"
    )


def _attention(problems: tuple[SummaryProblem, ...]) -> str:
    """A red box listing what went wrong, if anything did."""
    if not problems:
        return ""
    items = "".join(
        f"<p style='margin:8px 0 0;font-size:14px'><strong>{escape(problem.what_happened)}"
        f"</strong><br><span style='color:{_INK}'>{escape(problem.what_to_do)}</span></p>"
        for problem in problems
    )
    return (
        f"<div style='margin:20px 0 0;padding:14px 16px;background:{_ALERT_BACKGROUND};"
        f"border-left:4px solid {_ALERT};border-radius:6px'>"
        f"<p style='margin:0;font-size:15px;font-weight:700;color:{_ALERT}'>"
        f"{ATTENTION_HEADING}</p>{items}</div>"
    )


def _people(
    heading: str,
    people: tuple[SummaryPerson, ...],
    total: int,
    url: str | None,
    due_colour: str,
) -> str:
    """One section as a table: who, what next, by when."""
    title = f"{heading} ({total})" if people else heading
    head = _section_heading(title)
    if not people:
        return f"{head}<p style='margin:0;font-size:14px;color:{_MUTED}'>{NOBODY}</p>"
    header = "".join(
        f"<th align='left' style='padding:8px 10px;font-size:11px;font-weight:600;"
        f"text-transform:uppercase;letter-spacing:.05em;color:{_MUTED};"
        f"border-bottom:1px solid {_RULE}'>{label}</th>"
        for label in ("Person", "Next step", "Due")
    )
    rows = "".join(_person_row(person, due_colour) for person in people)
    rows += _more_row(total - len(people), url)
    table = f"{_TABLE} style='font-size:14px;border-collapse:collapse'>"
    return f"{head}{table}<tr>{header}</tr>{rows}</table>"


def _person_row(person: SummaryPerson, due_colour: str) -> str:
    """One person as one table row.

    Names are deliberately not links, and each row carries as little styling as
    it can: the session that sends the e-mail types the whole body out, and a
    long page address or a long repeated style is exactly what gets copied
    wrong — one name once pointed at somebody else's page.
    """
    organisation = (
        f"<br><small style='color:{_MUTED}'>{escape(person.organisation)}</small>"
        if person.organisation
        else ""
    )
    due = format_day(person.due_date) if person.due_date is not None else "—"
    return (
        f"<tr valign='top'><td style='{_CELL}'><b>{escape(person.name)}</b>{organisation}</td>"
        f"<td style='{_CELL}'>{escape(person.next_action or '—')}</td>"
        f"<td style='{_CELL};white-space:nowrap;color:{due_colour}'>{due}</td></tr>"
    )


def _more_row(hidden: int, url: str | None) -> str:
    """The closing row when a section had more people than fit."""
    if hidden <= 0:
        return ""
    words = more_on_dashboard(hidden)
    if url:
        words = f"<a href='{escape(url, quote=True)}' style='color:{_ACCENT}'>{words}</a>"
    return (
        f"<tr><td colspan='3' style='padding:10px;font-size:13px;color:{_MUTED}'>{words}</td></tr>"
    )


def _review(open_questions: int, url: str | None) -> str:
    """The yes-or-no questions waiting, with a button to answer them."""
    head = _section_heading(REVIEW_HEADING)
    if not open_questions:
        return f"{head}<p style='margin:0;font-size:14px;color:{_MUTED}'>{NO_QUESTIONS}</p>"
    text = f"<p style='margin:0;font-size:14px'>{questions_waiting(open_questions)}</p>"
    if not url:
        return f"{head}{text}"
    return f"{head}{text}{_button('Answer them', f'{url}{DASHBOARD_REVIEW_PATH}')}"


def _key_reminder(reminder: str | None) -> str:
    """An amber box when the LinkedIn key is about to run out."""
    if reminder is None:
        return ""
    return (
        f"<div style='margin:24px 0 0;padding:14px 16px;background:{_NOTICE_BACKGROUND};"
        f"border-left:4px solid {_NOTICE};border-radius:6px;font-size:14px'>"
        f"<strong style='color:{_NOTICE}'>{KEY_HEADING}</strong><br>{escape(reminder)}</div>"
    )


def _footer(url: str | None, product_name: str) -> str:
    """The closing line, with the run history when the dashboard has an address."""
    runs = ""
    if url:
        href = escape(f"{url}{DASHBOARD_RUNS_PATH}", quote=True)
        runs = f" · <a href='{href}' style='color:{_MUTED}'>See every run</a>"
    return (
        f"<p style='margin:28px 0 24px;padding-top:16px;border-top:1px solid {_RULE};"
        f"font-size:12px;color:{_MUTED}'>Sent by {escape(product_name)} every morning{runs}</p>"
    )


def _section_heading(title: str) -> str:
    """A section title with room above it."""
    return f"<h2 style='margin:28px 0 8px;font-size:16px'>{escape(title)}</h2>"
