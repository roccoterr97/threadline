"""The sample data, shaped the way the summary tests need it.

``people_overview`` is a database view, and the in-memory client in
``conftest.py`` is a dictionary of tables, so the view's rule — the owner's
corrections laid over the assessment — is applied here once, from the same
`fixtures/sample_data.json` the real ``tracker sample load`` writes. Everything
else (conversations, questions, runs and their steps) is used exactly as the
fixture holds it.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from tests.conftest import FIXTURES, FakeSupabaseClient

#: The moment every summary test runs at.
NOW = datetime(2026, 9, 18, 7, 0, tzinfo=UTC)

#: The day the sample data's follow-up dates are measured against.
TODAY = NOW.date()

#: The run the sample data shows as today's: LinkedIn read, mailbox refused.
TODAYS_RUN = UUID("30000000-0000-4000-8000-000000000002")

#: Yesterday's run, which finished cleanly.
YESTERDAYS_RUN = UUID("30000000-0000-4000-8000-000000000001")


def sample_data() -> dict[str, list[dict[str, Any]]]:
    """Read the sample data file Threadline ships with."""
    return json.loads((FIXTURES / "sample_data.json").read_text(encoding="utf-8"))


def sample_client(*, today: date = TODAY) -> FakeSupabaseClient:
    """Build an in-memory database holding the sample data.

    Args:
        today: The day the follow-up dates are measured against, as the view
            measures them against the database's own date.

    Returns:
        The fake client, with ``people_overview`` already computed.
    """
    data = sample_data()
    return FakeSupabaseClient(
        {
            "people_overview": overview_rows(data, today=today),
            "conversations": data["conversations"],
            "messages": data["messages"],
            "review_items": data["review_items"],
            "run_logs": data["run_logs"],
            "run_step_logs": data["run_step_logs"],
        }
    )


def overview_rows(
    data: dict[str, list[dict[str, Any]]],
    *,
    today: date,
) -> list[dict[str, Any]]:
    """Apply the ``people_overview`` rule to the sample tables.

    Args:
        data: The sample data.
        today: The day a follow-up date is compared with.

    Returns:
        One row per relevant person, corrections already applied.
    """
    organisations = {row["id"]: row for row in data["organisations"]}
    states = {row["person_id"]: row for row in data["person_states"]}
    overrides = {row["person_id"]: row for row in data["person_overrides"]}
    rows: list[dict[str, Any]] = []
    for person in data["people"]:
        if person["relevance"] != "relevant":
            continue
        state = states.get(person["id"], {})
        override = overrides.get(person["id"], {})
        rows.append(_overview_row(person, state, override, organisations, today))
    return rows


def _overview_row(
    person: dict[str, Any],
    state: dict[str, Any],
    override: dict[str, Any],
    organisations: dict[str, dict[str, Any]],
    today: date,
) -> dict[str, Any]:
    """Build one row of the read model."""
    waiting_on = override.get("waiting_on") or state.get("waiting_on")
    due_date = override.get("due_date") or state.get("due_date")
    organisation = organisations.get(person.get("organisation_id") or "")
    return {
        "person_id": person["id"],
        "full_name": person["full_name"],
        "organisation_name": organisation["name"] if organisation else None,
        "person_type": override.get("person_type") or person["person_type"],
        "role_title": person.get("role_title"),
        "status": override.get("status") or state.get("status"),
        "waiting_on": waiting_on,
        "next_action": override.get("next_action") or state.get("next_action"),
        "due_date": due_date,
        "summary": state.get("summary"),
        "signal": state.get("signal"),
        "confidence": state.get("confidence"),
        "assessed_at": state.get("assessed_at"),
        "last_contact_at": None,
        "channels": [],
        "message_count": 0,
        "is_overdue": _is_late(due_date, waiting_on, "me", today),
        "has_override": bool(override),
        "is_chase_due": _is_late(due_date, waiting_on, "them", today),
    }


def _is_late(due_date: str | None, waiting_on: str | None, owed_by: str, today: date) -> bool:
    """Whether a follow-up date has passed while ``owed_by`` owes the next move."""
    if due_date is None or waiting_on != owed_by:
        return False
    return date.fromisoformat(due_date) < today
