"""The "Refresh now" set-up step, without a terminal or a network."""

from __future__ import annotations

from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import pytest

from tests.setup_world import (
    DAILY_START_KEY,
    GOOD_GITHUB_TOKEN,
    GOOD_TOKEN,
    PASTE,
    PROJECT_URL,
    World,
    configured_env,
    make_world,
)
from tracker.services.setup.github_copy import repository_from_origin
from tracker.services.setup.models import StepName
from tracker.services.setup.step_refresh import RefreshStep, function_url, token_page
from tracker.services.setup.wizard import extra_steps
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
    world = refresh_world([True, GOOD_GITHUB_TOKEN, PASTE, GOOD_TOKEN])

    await RefreshStep().run(world.context())

    assert world.platform.secrets == {
        "REFRESH_TARGET": "github",
        "GITHUB_REPOSITORY": "you/threadline",
        "GITHUB_REF": "main",
        "DASHBOARD_ORIGIN": "https://you.vercel.app",
        "GITHUB_TOKEN_REFRESH": GOOD_GITHUB_TOKEN,
        "DAILY_START_KEY": DAILY_START_KEY,
    }
    assert world.platform.deployed == [
        ("refresh-now", ("index.ts", "refresh.ts", "daily.ts"), False)
    ]
    assert world.posts == [FUNCTION_URL, FUNCTION_URL]
    assert world.waits == [REFRESH_PROBE_WAIT_SECONDS]
    assert "Refreshing…" in world.io.text()


async def test_a_dashboard_on_netlify_is_the_one_origin_allowed() -> None:
    world = refresh_world([True, GOOD_GITHUB_TOKEN, PASTE, GOOD_TOKEN])
    world.env.values["DASHBOARD_BASE_URL"] = "https://threadline-abc123.netlify.app"

    await RefreshStep().run(world.context())

    assert world.platform.secrets["DASHBOARD_ORIGIN"] == "https://threadline-abc123.netlify.app"


async def test_neither_token_is_shown_or_written_to_env() -> None:
    world = refresh_world([True, GOOD_GITHUB_TOKEN, PASTE, GOOD_TOKEN])

    await RefreshStep().run(world.context())

    assert world.env.values == refresh_env()
    assert GOOD_GITHUB_TOKEN not in world.io.text()
    assert GOOD_TOKEN not in world.io.text()
    assert DAILY_START_KEY not in world.io.text()
    assert len(world.io.secret_prompts) == 2


async def test_the_filled_in_github_page_and_the_supabase_page_open() -> None:
    world = refresh_world([True, GOOD_GITHUB_TOKEN, PASTE, GOOD_TOKEN])

    await RefreshStep().run(world.context())

    assert world.io.opened == [token_page("you/threadline"), SUPABASE_TOKENS_PAGE]
    text = world.io.text()
    assert "'Only select repositories' and pick you/threadline" in text
    assert "click the small link 'Create legacy token'" in text
    assert "Name it 'Threadline set-up'" in text


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
    world = refresh_world(
        [True, "github_pat_wrong", GOOD_GITHUB_TOKEN, PASTE, "sbp_wrong", GOOD_TOKEN]
    )

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
    world = refresh_world([True, GOOD_GITHUB_TOKEN, PASTE, GOOD_TOKEN])
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


@pytest.mark.parametrize(("private", "admin"), [(False, True), (True, False), (False, False)])
async def test_a_repository_that_is_not_your_private_copy_is_never_used(
    *, private: bool, admin: bool
) -> None:
    """Origin still pointing at the public template must not get the helper's settings."""
    world = refresh_world([True, GOOD_GITHUB_TOKEN, PASTE, GOOD_TOKEN])
    world.git.origin = "https://github.com/public-template/threadline.git"
    world.github.name = "public-template/threadline"
    world.github.private = private
    world.github.admin = admin

    await RefreshStep().run(world.context())

    assert "not linked to your own private copy on GitHub" in world.io.text()
    assert "tracker setup github" in world.io.text()
    assert world.io.opened == []
    assert world.github_api.reads == []
    assert world.platform.secrets == {}


async def test_without_the_github_cli_the_link_is_used_and_the_owner_told_to_check_it() -> None:
    world = refresh_world([True, GOOD_GITHUB_TOKEN, PASTE, GOOD_TOKEN])
    world.github.signed_in = False

    await RefreshStep().run(world.context())

    assert "cannot check that you/threadline is your own" in world.io.text()
    assert world.platform.secrets["GITHUB_REPOSITORY"] == "you/threadline"


async def test_without_the_github_cli_a_bare_return_switches_nothing_on() -> None:
    world = refresh_world([""])
    world.github.signed_in = False

    await RefreshStep().run(world.context())

    assert "To switch it on later: uv run tracker setup refresh" in world.io.text()
    assert world.platform.secrets == {}
    assert world.github_api.reads == []


async def test_saying_no_changes_nothing() -> None:
    world = refresh_world([False])

    await RefreshStep().run(world.context())

    assert "To switch it on later: uv run tracker setup refresh" in world.io.text()
    assert world.platform.secrets == {}
    assert world.github_api.reads == []


async def test_a_function_that_never_guards_stops_the_step() -> None:
    world = refresh_world([True, GOOD_GITHUB_TOKEN, PASTE, GOOD_TOKEN], statuses=[404])

    with pytest.raises(ValidationFailedError, match="status 404"):
        await RefreshStep().run(world.context())

    assert len(world.posts) == REFRESH_PROBE_ATTEMPTS
    assert len(world.waits) == REFRESH_PROBE_ATTEMPTS - 1


@pytest.mark.parametrize(
    ("status", "timer_on", "done"),
    [(401, True, True), (403, True, True), (404, True, False), (401, False, False)],
)
async def test_the_step_is_done_when_the_function_guards_and_the_timer_is_on(
    status: int, *, timer_on: bool, done: bool
) -> None:
    world = refresh_world([], statuses=[status])
    if timer_on:
        world.admin.daily_start = (f"{FUNCTION_URL}/daily-start", DAILY_START_KEY)
        world.admin.job_scheduled = True

    assert await RefreshStep().is_done(world.context()) is done


async def test_the_step_is_not_done_without_a_project_or_a_connection() -> None:
    assert not await RefreshStep().is_done(make_world().context())

    async def unreachable(url: str) -> int:
        raise SourceUnavailableError(url)

    context = refresh_world([]).context()
    offline = replace(context, gateways=replace(context.gateways, status_of_post=unreachable))
    assert not await RefreshStep().is_done(offline)


async def test_refresh_is_an_extra_between_linkedin_and_the_cloud_alternative() -> None:
    names = [step.name for step in extra_steps()]

    assert names == [StepName.LINKEDIN, StepName.REFRESH, StepName.CLOUD]


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
