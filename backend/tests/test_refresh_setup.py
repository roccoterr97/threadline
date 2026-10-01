"""The "Refresh now" set-up step, without a terminal or a network."""

from __future__ import annotations

from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import pytest

from tests.setup_world import (
    GOOD_GITHUB_TOKEN,
    GOOD_TOKEN,
    PROJECT_REF,
    PROJECT_URL,
    World,
    configured_env,
    make_world,
)
from tracker.services.setup.github_copy import repository_from_origin
from tracker.services.setup.models import StepName
from tracker.services.setup.step_refresh import RefreshStep, function_url, token_page
from tracker.services.setup.wizard import default_steps
from tracker.shared.constants.setup import (
    REFRESH_PROBE_ATTEMPTS,
    REFRESH_PROBE_WAIT_SECONDS,
    SUPABASE_TOKENS_PAGE,
)
from tracker.shared.errors import SourceAuthError, SourceUnavailableError, ValidationFailedError

pytestmark = pytest.mark.asyncio

FUNCTION_URL = f"{PROJECT_URL}/functions/v1/refresh-now"


def refresh_env() -> dict[str, str]:
    """A ``.env`` where every earlier step Refresh now relies on is finished."""
    return configured_env() | {"DASHBOARD_BASE_URL": "https://you.vercel.app"}


def refresh_world(answers: list[str | bool], statuses: list[int] | None = None) -> World:
    """A world with the dashboard published and the copy on GitHub."""
    world = make_world(answers, refresh_env())
    world.function_statuses = statuses or [404, 401]
    return world


async def test_refresh_now_is_switched_on_end_to_end() -> None:
    world = refresh_world([True, GOOD_GITHUB_TOKEN, GOOD_TOKEN])

    await RefreshStep().run(world.context())

    assert world.platform.secrets == {
        "REFRESH_TARGET": "github",
        "GITHUB_REPOSITORY": "you/threadline",
        "GITHUB_REF": "main",
        "DASHBOARD_ORIGIN": "https://you.vercel.app",
        "GITHUB_TOKEN_REFRESH": GOOD_GITHUB_TOKEN,
    }
    assert world.platform.deployed == [("refresh-now", ("index.ts", "refresh.ts"), False)]
    assert world.posts == [FUNCTION_URL, FUNCTION_URL]
    assert world.waits == [REFRESH_PROBE_WAIT_SECONDS]
    assert "Refreshing…" in world.io.text()


async def test_neither_token_is_shown_or_written_to_env() -> None:
    world = refresh_world([True, GOOD_GITHUB_TOKEN, GOOD_TOKEN])

    await RefreshStep().run(world.context())

    assert world.env.values == refresh_env()
    assert GOOD_GITHUB_TOKEN not in world.io.text()
    assert GOOD_TOKEN not in world.io.text()
    assert len(world.io.secret_prompts) == 2


async def test_the_filled_in_github_page_and_the_supabase_page_open() -> None:
    world = refresh_world([True, GOOD_GITHUB_TOKEN, GOOD_TOKEN])

    await RefreshStep().run(world.context())

    assert world.io.opened == [token_page("you/threadline"), SUPABASE_TOKENS_PAGE]
    text = world.io.text()
    assert "'Only select repositories' and pick you/threadline" in text
    assert "'Edge Functions' and 'Edge Function Secrets', both read and write" in text
    assert f"Limit it to this project ({PROJECT_REF})" in text


async def test_the_github_token_page_is_filled_in_with_the_one_permission() -> None:
    page = urlsplit(token_page("someone/threadline"))

    assert f"{page.scheme}://{page.netloc}{page.path}" == (
        "https://github.com/settings/personal-access-tokens/new"
    )
    assert parse_qs(page.query) == {
        "name": ["Threadline refresh now"],
        "description": ["Lets the dashboard's Refresh now button start the Threadline workflow."],
        "target_name": ["someone"],
        "expires_in": ["365"],
        "actions": ["write"],
    }


async def test_refused_tokens_are_asked_for_again() -> None:
    world = refresh_world([True, "github_pat_wrong", GOOD_GITHUB_TOKEN, "sbp_wrong", GOOD_TOKEN])

    await RefreshStep().run(world.context())

    text = world.io.text()
    assert "GitHub did not accept the token" in text
    assert "Supabase did not accept the access token" in text
    assert world.platform.deployed


async def test_nothing_is_saved_when_the_github_token_is_refused_every_time() -> None:
    world = refresh_world([True, "bad", "bad", "bad"])

    with pytest.raises(SourceAuthError):
        await RefreshStep().run(world.context())

    assert world.platform.secrets == {}
    assert world.platform.deployed == []


async def test_a_switched_off_workflow_is_pointed_out() -> None:
    world = refresh_world([True, GOOD_GITHUB_TOKEN, GOOD_TOKEN])
    world.github_api.state = "disabled_manually"

    await RefreshStep().run(world.context())

    assert "Enable workflow" in world.io.text()
    assert world.platform.deployed


async def test_without_a_published_dashboard_the_step_is_skipped() -> None:
    world = make_world([], configured_env())

    await RefreshStep().run(world.context())

    assert "tracker setup dashboard" in world.io.text()
    assert world.platform.deployed == []


async def test_without_a_copy_on_github_the_step_is_skipped() -> None:
    world = make_world([], refresh_env())
    world.git.origin = None

    await RefreshStep().run(world.context())

    assert "tracker setup github" in world.io.text()
    assert world.io.opened == []


async def test_saying_no_changes_nothing() -> None:
    world = refresh_world([False])

    await RefreshStep().run(world.context())

    assert "To switch it on later: uv run tracker setup refresh" in world.io.text()
    assert world.platform.secrets == {}
    assert world.github_api.reads == []


async def test_a_function_that_never_guards_stops_the_step() -> None:
    world = refresh_world([True, GOOD_GITHUB_TOKEN, GOOD_TOKEN], statuses=[404])

    with pytest.raises(ValidationFailedError, match="status 404"):
        await RefreshStep().run(world.context())

    assert len(world.posts) == REFRESH_PROBE_ATTEMPTS
    assert len(world.waits) == REFRESH_PROBE_ATTEMPTS - 1


@pytest.mark.parametrize(("status", "done"), [(401, True), (403, True), (404, False)])
async def test_the_step_is_done_when_the_function_guards(status: int, *, done: bool) -> None:
    world = refresh_world([], statuses=[status])

    assert await RefreshStep().is_done(world.context()) is done


async def test_the_step_is_not_done_without_a_project_or_a_connection() -> None:
    assert not await RefreshStep().is_done(make_world().context())

    async def unreachable(url: str) -> int:
        raise SourceUnavailableError(url)

    context = refresh_world([]).context()
    offline = replace(context, gateways=replace(context.gateways, status_of_post=unreachable))
    assert not await RefreshStep().is_done(offline)


async def test_refresh_comes_after_github_and_before_the_cloud_alternative() -> None:
    names = [step.name for step in default_steps()]

    assert names.index(StepName.REFRESH) == names.index(StepName.GITHUB) + 1
    assert names.index(StepName.CLOUD) == names.index(StepName.REFRESH) + 1


async def test_the_function_address_is_below_the_project() -> None:
    assert function_url(f"{PROJECT_URL}/") == FUNCTION_URL


@pytest.mark.parametrize(
    ("origin", "repository"),
    [
        ("https://github.com/you/threadline.git", "you/threadline"),
        ("git@github.com:you/thread.line.git", "you/thread.line"),
        ("https://github.com/you/threadline/", "you/threadline"),
        ("https://gitlab.com/you/threadline.git", None),
        (None, None),
    ],
)
async def test_the_copy_is_read_from_the_origin_link(
    origin: str | None, repository: str | None
) -> None:
    assert repository_from_origin(origin) == repository
