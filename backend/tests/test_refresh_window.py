"""Where a refresh starts reading: the last successful read of that source."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from tests.conftest import FakeSupabaseClient, as_client
from tracker.cli.main import build_cli
from tracker.domain.enums import RunStatus, RunStep, RunTrigger
from tracker.repositories import build_repositories
from tracker.services.collection.window import refresh_since
from tracker.shared.constants.collection import REFRESH_OVERLAP_HOURS

MORNING = datetime(2026, 9, 29, 7, 0, tzinfo=UTC)
YESTERDAY = MORNING - timedelta(days=1)


def _run(run_id: str, started_at: datetime, status: RunStatus) -> dict[str, Any]:
    return {
        "id": run_id,
        "started_at": started_at.isoformat(),
        "finished_at": (started_at + timedelta(minutes=5)).isoformat(),
        "status": status.value,
        "trigger": RunTrigger.GITHUB.value,
    }


def _step(run_id: str, step: RunStep, status: RunStatus, created_at: datetime) -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "run_id": run_id,
        "step": step.value,
        "status": status.value,
        "created_at": created_at.isoformat(),
    }


YESTERDAY_RUN = "40000000-0000-4000-8000-000000000001"
TODAY_RUN = "40000000-0000-4000-8000-000000000002"


def _client(today_email: RunStatus) -> FakeSupabaseClient:
    """Yesterday read everything; this morning the mailbox read ended as given."""
    return FakeSupabaseClient(
        {
            "run_logs": [
                _run(YESTERDAY_RUN, YESTERDAY, RunStatus.SUCCESS),
                _run(TODAY_RUN, MORNING, RunStatus.PARTIAL),
            ],
            "run_step_logs": [
                _step(YESTERDAY_RUN, RunStep.COLLECT_EMAIL, RunStatus.SUCCESS, YESTERDAY),
                _step(TODAY_RUN, RunStep.COLLECT_LINKEDIN, RunStatus.FAILED, MORNING),
                _step(TODAY_RUN, RunStep.COLLECT_EMAIL, today_email, MORNING),
            ],
        }
    )


def test_a_refresh_starts_from_this_mornings_read_even_when_the_run_was_partial() -> None:
    repositories = build_repositories(as_client(_client(RunStatus.SUCCESS)))

    since = refresh_since(repositories, RunStep.COLLECT_EMAIL)

    assert since == MORNING - timedelta(hours=REFRESH_OVERLAP_HOURS)


def test_a_failed_read_this_morning_sends_the_refresh_back_to_yesterday() -> None:
    repositories = build_repositories(as_client(_client(RunStatus.FAILED)))

    since = refresh_since(repositories, RunStep.COLLECT_EMAIL)

    assert since == YESTERDAY - timedelta(hours=REFRESH_OVERLAP_HOURS)


def test_a_source_never_read_leaves_the_usual_window_in_charge() -> None:
    repositories = build_repositories(as_client(_client(RunStatus.SUCCESS)))

    assert refresh_since(repositories, RunStep.COLLECT_CALENDAR) is None


def test_an_empty_history_leaves_the_usual_window_in_charge() -> None:
    repositories = build_repositories(as_client(FakeSupabaseClient()))

    assert refresh_since(repositories, RunStep.COLLECT_EMAIL) is None


def test_refresh_and_since_together_are_refused(settings: object) -> None:
    result = CliRunner().invoke(
        build_cli(), ["collect", "email", "--refresh", "--since", "2026-09-01"]
    )

    assert result.exit_code != 0
    assert isinstance(result.exception, Exception)
    assert "cannot be used together" in str(result.exception)


#: The codes a terminal reads as "switch to this colour".
_COLOUR_CODES = re.compile(r"\x1b\[[0-9;]*m")


@pytest.mark.parametrize("command", [["collect", "email", "--help"], ["collect", "all", "--help"]])
def test_the_mailbox_command_offers_a_refresh(command: list[str]) -> None:
    result = CliRunner().invoke(build_cli(), command)

    assert result.exit_code == 0
    # On GitHub Actions the help is printed in colour, and the colour codes sit
    # between the two dashes and the option's name.
    assert "--refresh" in _COLOUR_CODES.sub("", result.output)
