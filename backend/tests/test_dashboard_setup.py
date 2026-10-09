"""``tracker setup dashboard``: publishing on Netlify, another host, and every refusal."""

from __future__ import annotations

import io
import zipfile

import pytest
from pydantic import SecretStr

from tests.setup_world import (
    ARCHIVE_URL,
    BUILT_SITE,
    CHECKSUM_URL,
    GOOD_NETLIFY_TOKEN,
    GOOD_PUBLISHABLE,
    GOOD_SECRET,
    GOOD_TOKEN,
    PROJECT_REF,
    PROJECT_URL,
    World,
    configured_env,
    make_world,
    release_downloads,
)
from tracker.domain.supabase import AuthSettings
from tracker.infrastructure.web_probe import WebPage
from tracker.services.setup.context import SetupContext
from tracker.services.setup.step_dashboard import DashboardStep
from tracker.shared.constants.dashboard import (
    CONFIG_FILE,
    DEPLOY_POLL_ATTEMPTS,
    NETLIFY_SIGNUP_PAGE,
    NETLIFY_TOKENS_PAGE,
    SITE_NAME_ATTEMPTS,
)
from tracker.shared.errors import (
    DashboardDeployError,
    DashboardPackageError,
    SourceAuthError,
    SourceRequestRejectedError,
    ValidationFailedError,
)

pytestmark = pytest.mark.asyncio

SITE = "https://threadline-abc123.netlify.app"
LIVE = [WebPage(status=200, is_html=True)]

#: The answers of a first publish: publish on Netlify, has an account, the token.
FIRST_PUBLISH: list[str | bool] = [True, True, GOOD_NETLIFY_TOKEN]


def _world(answers: list[str | bool], env: dict[str, str] | None = None) -> World:
    world = make_world(answers, configured_env() if env is None else env)
    world.pages[SITE] = list(LIVE)
    return world


def _context(world: World) -> SetupContext:
    """A context in a full set-up, where the Supabase step already took the run's token."""
    ctx = world.context()
    ctx.session.supabase_token = SecretStr(GOOD_TOKEN)
    return ctx


def _pointed_at(address: str) -> list[tuple[str, AuthSettings]]:
    """The one change Supabase should receive for a dashboard at ``address``."""
    return [(PROJECT_REF, AuthSettings(site_url=address, redirect_urls=(f"{address}/**",)))]


def _published_files(world: World) -> dict[str, bytes]:
    [(_, archive)] = world.netlify.deployed
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        return {name: bundle.read(name) for name in bundle.namelist()}


# --- Netlify -------------------------------------------------------------------


async def test_a_first_publish_creates_the_site_deploys_and_saves_both_values() -> None:
    world = _world(FIRST_PUBLISH)

    await DashboardStep().run(_context(world))

    assert world.env.values["DASHBOARD_BASE_URL"] == SITE
    assert world.env.values["NETLIFY_SITE_ID"] == "site-1"
    assert world.netlify.created == ["threadline-abc123"]
    assert NETLIFY_TOKENS_PAGE in world.io.opened
    assert NETLIFY_SIGNUP_PAGE not in world.io.opened
    assert world.platform.auth_changes == _pointed_at(SITE)
    assert "Supabase's sign-in links now open your dashboard." in world.io.said
    assert f"Check: {SITE} opens the dashboard." in world.io.said


async def test_the_token_is_asked_hidden_and_never_shown_or_saved() -> None:
    world = _world(FIRST_PUBLISH)

    await DashboardStep().run(_context(world))

    assert world.io.secret_prompts == ["Paste the Netlify token (it stays hidden)"]
    assert GOOD_NETLIFY_TOKEN not in world.io.text()
    assert GOOD_NETLIFY_TOKEN not in world.env.values.values()


async def test_the_published_files_are_the_release_plus_a_config_with_public_values() -> None:
    world = _world(FIRST_PUBLISH)

    await DashboardStep().run(_context(world))

    files = _published_files(world)
    config = files.pop(CONFIG_FILE).decode()
    assert files == BUILT_SITE
    assert PROJECT_URL in config
    assert GOOD_PUBLISHABLE in config
    assert GOOD_SECRET not in config
    assert config.startswith("window.__THREADLINE_CONFIG__ = Object.freeze(")


async def test_without_an_account_the_sign_up_page_opens_first() -> None:
    world = _world([True, False, GOOD_NETLIFY_TOKEN])

    await DashboardStep().run(_context(world))

    assert world.io.opened.index(NETLIFY_SIGNUP_PAGE) < world.io.opened.index(NETLIFY_TOKENS_PAGE)
    assert "[paused] Once you are signed in to Netlify" in world.io.said


async def test_a_refused_token_is_asked_again() -> None:
    world = _world([True, True, "nfp_wrong", GOOD_NETLIFY_TOKEN])

    await DashboardStep().run(_context(world))

    assert "did not accept the token" in world.io.text()
    assert world.env.values["DASHBOARD_BASE_URL"] == SITE


async def test_a_token_refused_every_time_stops_before_anything_is_made() -> None:
    world = _world([True, True, "nfp_wrong", "nfp_wrong", "nfp_wrong"])

    with pytest.raises(SourceAuthError, match="did not accept the token"):
        await DashboardStep().run(_context(world))

    assert world.netlify.created == []
    assert "NETLIFY_SITE_ID" not in world.env.values


async def test_a_taken_name_is_replaced_by_another() -> None:
    world = _world(FIRST_PUBLISH)
    world.netlify.taken = {"threadline-abc123"}
    world.pages["https://threadline-def456.netlify.app"] = list(LIVE)

    await DashboardStep().run(_context(world))

    assert world.netlify.created == ["threadline-abc123", "threadline-def456"]
    assert world.env.values["DASHBOARD_BASE_URL"] == "https://threadline-def456.netlify.app"


async def test_names_taken_every_time_stop_the_step() -> None:
    world = _world(FIRST_PUBLISH)
    world.suffixes = [f"taken{number}" for number in range(SITE_NAME_ATTEMPTS)]
    world.netlify.taken = {f"threadline-{suffix}" for suffix in world.suffixes}

    with pytest.raises(DashboardDeployError, match="taken"):
        await DashboardStep().run(_context(world))

    assert len(world.netlify.created) == SITE_NAME_ATTEMPTS


async def test_a_deploy_is_waited_for_until_it_is_ready() -> None:
    world = _world(FIRST_PUBLISH)
    world.netlify.states = ["uploaded", "processing", "ready"]

    await DashboardStep().run(_context(world))

    assert world.netlify.polls == 2
    assert world.env.values["DASHBOARD_BASE_URL"] == SITE


async def test_a_failed_deploy_says_why_and_keeps_the_site_for_the_next_try() -> None:
    world = _world(FIRST_PUBLISH)
    world.netlify.states = ["processing", "error"]
    world.netlify.error = "Failed to extract the files"

    with pytest.raises(DashboardDeployError, match="Failed to extract the files"):
        await DashboardStep().run(_context(world))

    assert world.env.values["NETLIFY_SITE_ID"] == "site-1"
    assert "DASHBOARD_BASE_URL" not in world.env.values


async def test_a_deploy_that_never_gets_ready_stops_after_the_last_look() -> None:
    world = _world(FIRST_PUBLISH)
    world.netlify.states = ["processing"]

    with pytest.raises(DashboardDeployError, match="had not finished publishing"):
        await DashboardStep().run(_context(world))

    assert world.netlify.polls == DEPLOY_POLL_ATTEMPTS - 1
    assert "DASHBOARD_BASE_URL" not in world.env.values


async def test_a_site_that_does_not_answer_with_the_dashboard_is_not_saved() -> None:
    world = _world(FIRST_PUBLISH)
    world.pages[SITE] = [WebPage(status=404, is_html=True)]

    with pytest.raises(DashboardDeployError, match="answered status 404"):
        await DashboardStep().run(_context(world))

    assert "DASHBOARD_BASE_URL" not in world.env.values


async def test_a_site_answering_something_other_than_a_page_is_not_saved() -> None:
    world = _world(FIRST_PUBLISH)
    world.pages[SITE] = [WebPage(status=200, is_html=False)]

    with pytest.raises(DashboardDeployError, match=SITE):
        await DashboardStep().run(_context(world))


async def test_a_site_that_takes_a_moment_to_answer_is_opened_again() -> None:
    world = _world(FIRST_PUBLISH)
    world.pages[SITE] = [WebPage(status=404, is_html=False), *LIVE]

    await DashboardStep().run(_context(world))

    assert world.env.values["DASHBOARD_BASE_URL"] == SITE


async def test_running_it_again_redeploys_to_the_saved_site_without_asking_supabase_again() -> None:
    world = _world(FIRST_PUBLISH)
    await DashboardStep().run(_context(world))
    world.io.answers.extend(FIRST_PUBLISH)
    world.io.said.clear()

    await DashboardStep().run(_context(world))

    assert world.netlify.created == ["threadline-abc123"]
    assert [site for site, _ in world.netlify.deployed] == ["site-1", "site-1"]
    assert f"Publishing the newest dashboard to your site, {SITE}." in world.io.said
    assert "Supabase needs nothing new" in world.io.text()
    assert world.platform.auth_changes == _pointed_at(SITE)


async def test_a_saved_site_that_is_gone_is_made_again() -> None:
    env = configured_env() | {"NETLIFY_SITE_ID": "site-deleted"}
    world = _world(FIRST_PUBLISH, env)

    await DashboardStep().run(_context(world))

    assert "no longer exists" in world.io.text()
    assert world.env.values["NETLIFY_SITE_ID"] == "site-1"


async def test_a_bad_checksum_stops_before_any_token_is_asked() -> None:
    world = _world(FIRST_PUBLISH)
    world.downloads[CHECKSUM_URL] = b"0" * 64 + b"  dashboard.zip\n"

    with pytest.raises(DashboardPackageError, match="does not match its checksum"):
        await DashboardStep().run(_context(world))

    assert world.io.secret_prompts == []
    assert world.netlify.deployed == []


async def test_a_release_holding_a_path_outside_the_site_is_refused() -> None:
    world = _world(FIRST_PUBLISH)
    world.downloads = release_downloads({**BUILT_SITE, "../outside.js": b"x"})

    with pytest.raises(DashboardPackageError, match="outside the site"):
        await DashboardStep().run(_context(world))

    assert world.netlify.deployed == []


async def test_a_missing_release_stops_with_the_address_tried() -> None:
    world = _world(FIRST_PUBLISH)
    world.downloads = {}

    with pytest.raises(SourceRequestRejectedError, match=ARCHIVE_URL):
        await DashboardStep().run(_context(world))


async def test_a_secret_key_saved_as_the_public_one_never_reaches_the_page() -> None:
    env = configured_env() | {"SUPABASE_ANON_KEY": GOOD_SECRET}
    world = _world(FIRST_PUBLISH, env)

    with pytest.raises(ValidationFailedError, match="secret key"):
        await DashboardStep().run(_context(world))

    assert world.netlify.deployed == []


async def test_a_contributor_with_node_can_publish_a_local_build() -> None:
    world = _world([True, True, True, GOOD_NETLIFY_TOKEN])
    world.local_build.present = True
    world.local_build.files = {**BUILT_SITE, "index.html": b"<!doctype html>local"}
    world.downloads = {}

    await DashboardStep().run(_context(world))

    assert world.local_build.builds == 1
    assert _published_files(world)["index.html"] == b"<!doctype html>local"


async def test_a_contributor_may_still_choose_the_ready_made_dashboard() -> None:
    world = _world([True, False, True, GOOD_NETLIFY_TOKEN])
    world.local_build.present = True

    await DashboardStep().run(_context(world))

    assert world.local_build.builds == 0
    assert world.env.values["DASHBOARD_BASE_URL"] == SITE


# --- Another host --------------------------------------------------------------


async def test_another_host_is_saved_once_it_opens() -> None:
    world = make_world([False, True, "https://you.host.example/"], configured_env())
    world.statuses["https://you.host.example"] = 200

    await DashboardStep().run(_context(world))

    assert world.env.values["DASHBOARD_BASE_URL"] == "https://you.host.example"
    assert world.platform.auth_changes == _pointed_at("https://you.host.example")
    assert world.netlify.deployed == []


async def test_another_host_behind_a_login_is_refused() -> None:
    address = "https://a.vercel.example"
    world = make_world([False, True, address, address, "http://a"], configured_env())
    world.statuses[address] = 401

    with pytest.raises(ValidationFailedError, match="https://"):
        await DashboardStep().run(_context(world))

    assert "asks for a login" in world.io.text()


async def test_saying_no_to_both_stops_the_step_and_saves_nothing() -> None:
    world = make_world([False, False], configured_env())

    with pytest.raises(ValidationFailedError, match="part 5 of the guide"):
        await DashboardStep().run(_context(world))

    assert "DASHBOARD_BASE_URL" not in world.env.values
    assert world.io.opened == []


# --- Supabase's sign-in addresses ------------------------------------------------


async def test_run_alone_it_asks_for_the_supabase_token_once_and_sets_both_addresses() -> None:
    world = _world([*FIRST_PUBLISH, True, GOOD_TOKEN])

    await DashboardStep().run(world.context())

    assert world.platform.auth_changes == _pointed_at(SITE)
    assert world.io.secret_prompts[-1] == "Paste the Supabase access token (it stays hidden)"
    assert GOOD_TOKEN not in world.io.text()
    assert GOOD_TOKEN not in world.env.values.values()


async def test_run_alone_without_a_token_the_two_values_are_typed_by_hand() -> None:
    world = _world([*FIRST_PUBLISH, False])

    await DashboardStep().run(world.context())

    assert world.platform.auth_changes == []
    assert f"  Site URL: {SITE}" in world.io.said
    assert f"  Redirect URLs: add {SITE}/**" in world.io.said
    assert "[paused] Once both are saved" in world.io.said


async def test_a_refusal_from_supabase_falls_back_to_typing_the_two_values() -> None:
    world = _world(FIRST_PUBLISH)
    world.platform.auth_refusal = SourceRequestRejectedError

    await DashboardStep().run(_context(world))

    assert "Supabase would not change the sign-in addresses" in world.io.text()
    assert f"  Redirect URLs: add {SITE}/**" in world.io.said
    assert world.env.values["DASHBOARD_BASE_URL"] == SITE


async def test_a_refused_token_also_falls_back_to_typing_the_two_values() -> None:
    world = _world(FIRST_PUBLISH)
    world.platform.auth_refusal = SourceAuthError

    await DashboardStep().run(_context(world))

    assert f"  Site URL: {SITE}" in world.io.said
