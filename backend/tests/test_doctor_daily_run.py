"""``tracker doctor`` reads the newest daily run on GitHub: the set-up does not wait for it."""

from __future__ import annotations

import pytest

from tests.setup_world import REFRESH_RUN_TITLE, FakeGitHub
from tracker.cli.doctor_wiring import DEPENDENT_CHECKS
from tracker.infrastructure.github_cli import WorkflowRun
from tracker.services.doctor.daily_run import DailyRunCheck
from tracker.services.doctor.models import CheckStatus
from tracker.services.doctor.service import DoctorService
from tracker.shared.constants.github import DAILY_RUN_TITLE

pytestmark = pytest.mark.asyncio

RUN_PAGE = "https://github.com/you/threadline/actions/runs/7"
STOPPED_NOTE = (
    "Claude did not accept the key saved on GitHub (CLAUDE_CODE_OAUTH_TOKEN): it is "
    "incomplete, expired or was cancelled."
)


def daily_run(status: str, conclusion: str = "") -> WorkflowRun:
    """The newest daily run, as GitHub lists it."""
    return WorkflowRun(7, status, conclusion, RUN_PAGE, title=DAILY_RUN_TITLE)


def github_with(*runs: WorkflowRun, notes: tuple[str, ...] = ()) -> FakeGitHub:
    """The GitHub CLI signed in on the owner's copy, its runs listed newest last."""
    return FakeGitHub(runs=list(reversed(runs)), notes=notes)


async def test_a_stopped_run_is_a_problem_with_the_reason_claude_gave() -> None:
    github = github_with(daily_run("completed", "failure"), notes=(STOPPED_NOTE,))

    result = await DailyRunCheck(github).run()

    assert result.status is CheckStatus.PROBLEM
    assert result.detail == f"the newest daily run stopped. {STOPPED_NOTE}"
    assert "uv run tracker setup github" in result.fix
    assert RUN_PAGE in result.fix


async def test_a_stopped_run_without_a_reason_names_its_page() -> None:
    result = await DailyRunCheck(github_with(daily_run("completed", "failure"))).run()

    assert result.status is CheckStatus.PROBLEM
    assert result.fix == f"open {RUN_PAGE} and click the step marked with a red cross to see why"


@pytest.mark.parametrize(
    ("run", "detail"),
    [
        (daily_run("completed", "success"), "the newest daily run finished well"),
        (daily_run("in_progress"), f"a daily run is going: {RUN_PAGE}"),
    ],
)
async def test_a_run_going_or_finished_well_is_fine(run: WorkflowRun, detail: str) -> None:
    result = await DailyRunCheck(github_with(run)).run()

    assert (result.status, result.detail) == (CheckStatus.OK, detail)


async def test_a_refresh_after_the_daily_run_is_not_taken_for_it() -> None:
    refresh = WorkflowRun(8, "completed", "failure", "r", title=REFRESH_RUN_TITLE)
    github = github_with(daily_run("completed", "success"), refresh)

    result = await DailyRunCheck(github).run()

    assert result.status is CheckStatus.OK


@pytest.mark.parametrize(
    ("github", "detail"),
    [
        (FakeGitHub(signed_in=False), "the GitHub CLI is not signed in on this computer"),
        (FakeGitHub(name=None), "this folder is not linked to your private copy on GitHub"),
        (FakeGitHub(private=False), "this folder is not linked to your private copy on GitHub"),
        (FakeGitHub(), "no daily run yet"),
    ],
)
async def test_without_a_run_to_read_the_check_is_skipped(github: FakeGitHub, detail: str) -> None:
    result = await DailyRunCheck(github).run()

    assert (result.status, result.detail) == (CheckStatus.SKIPPED, detail)


async def test_runs_github_cannot_describe_are_a_problem_with_the_page_to_look_at() -> None:
    github = github_with(daily_run("completed", "failure"))
    github.runs_readable = False

    report = await DoctorService([DailyRunCheck(github)]).run()

    result = report.results[0]
    assert result.status is CheckStatus.PROBLEM
    assert result.detail == "GitHub could not say how the run is going"
    assert "Actions" in result.fix


async def test_the_check_is_named_among_those_a_broken_configuration_skips() -> None:
    assert "Daily run on GitHub" in DEPENDENT_CHECKS
