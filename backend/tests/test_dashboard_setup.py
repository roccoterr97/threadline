"""``tracker setup dashboard``: publishing on Netlify, another host, and every refusal."""

from __future__ import annotations

import base64
import io
import json
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
    NARROW_TOKEN,
    PROJECT_REF,
    PROJECT_URL,
    World,
    configured_env,
    make_world,
    release_downloads,
)
from tracker.domain.supabase import AuthSettings
from tracker.infrastructure.netlify_api import NetlifySite
from tracker.infrastructure.web_probe import WebPage
from tracker.services.database_structure import KNOWN_MIGRATIONS
from tracker.services.setup.context import SetupContext
from tracker.services.setup.step_dashboard import DashboardStep
from tracker.services.setup.supabase_session import TOO_LITTLE_ACCESS
from tracker.shared.constants.dashboard import (
    CONFIG_FILE,
    DEPLOY_POLL_ATTEMPTS,
    NETLIFY_APP_URL,
    NETLIFY_SIGNUP_PAGE,
    NETLIFY_TEAM_LOGIN_PAGE,
    NETLIFY_TOKENS_PAGE,
    PROVENANCE_SOURCE_REF,
    SIGNER_WORKFLOW,
    SITE_NAME_ATTEMPTS,
    TEMPLATE_REPOSITORY,
)
from tracker.shared.constants.setup import SUPABASE_TOKENS_PAGE
from tracker.shared.errors import (
    DashboardDeployError,
    DashboardPackageError,
    DashboardPrivateError,
    DashboardProvenanceError,
    SourceAuthError,
    SourceRequestRejectedError,
    SourceUnavailableError,
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


def _building_here(world: World) -> SetupContext:
    """A context for ``tracker setup dashboard --build-here``."""
    ctx = _context(world)
    ctx.session.build_dashboard_here = True
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
    assert files.pop("_headers").startswith(b"/*\n  Content-Security-Policy: default-src 'self'")
    assert files.pop("_redirects") == b"/* /index.html 200\n"
    assert files == {name: body for name, body in BUILT_SITE.items() if not name.startswith("_")}
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


async def test_a_refusal_that_is_not_about_the_name_is_shown_and_not_retried() -> None:
    world = _world(FIRST_PUBLISH)
    world.netlify.create_refusal = SourceRequestRejectedError(
        "Netlify refused it (status 422: account_slug is not allowed)"
    )

    with pytest.raises(SourceRequestRejectedError, match="account_slug is not allowed"):
        await DashboardStep().run(_context(world))

    assert world.netlify.created == ["threadline-abc123"]
    assert "NETLIFY_SITE_ID" not in world.env.values


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


#: What a private Netlify project answers: its team login, at the end of a redirect.
TEAM_LOGIN = f"{NETLIFY_TEAM_LOGIN_PAGE}?domain=threadline-abc123.netlify.app&site_id=site-1"


@pytest.mark.parametrize(
    "private",
    [
        WebPage(status=401, is_html=True, address=TEAM_LOGIN),
        WebPage(status=401, is_html=True, address=SITE),
        WebPage(status=403, is_html=False, address=SITE),
        WebPage(status=200, is_html=True, address=TEAM_LOGIN),
    ],
)
async def test_a_private_netlify_site_stops_at_once_with_the_clicks_that_make_it_public(
    private: WebPage,
) -> None:
    world = _world(FIRST_PUBLISH)
    world.pages[SITE] = [private]

    with pytest.raises(DashboardPrivateError, match="keeps .* private") as raised:
        await DashboardStep().run(_context(world))

    assert raised.value.code == "dashboard_private"
    said = world.io.text()
    assert "'Project configuration', then 'General', then 'Visitor access'" in said
    assert "click 'Edit visibility'" in said
    assert "Set 'Production' to 'Public'" in said
    assert "the dashboard has its own sign-in" in said
    assert "Run 'uv run tracker setup dashboard' again." in said
    assert world.io.opened[-1] == NETLIFY_APP_URL
    assert world.waits == []
    assert "DASHBOARD_BASE_URL" not in world.env.values
    assert world.env.values["NETLIFY_SITE_ID"] == "site-1"


async def test_the_private_site_s_own_netlify_page_opens_when_netlify_names_it() -> None:
    admin = f"{NETLIFY_APP_URL}/projects/threadline-abc123"
    site = NetlifySite(id="site-9", name="threadline-abc123", address=SITE, admin_address=admin)
    world = _world(FIRST_PUBLISH, {**configured_env(), "NETLIFY_SITE_ID": site.id})
    world.netlify.sites[site.id] = site
    world.pages[SITE] = [WebPage(status=401, is_html=True, address=TEAM_LOGIN)]

    with pytest.raises(DashboardPrivateError):
        await DashboardStep().run(_context(world))

    assert world.io.opened[-1] == admin
    assert "Open your project, threadline-abc123" in world.io.text()


async def test_once_made_public_running_it_again_saves_the_address() -> None:
    world = _world(FIRST_PUBLISH)
    world.pages[SITE] = [WebPage(status=401, is_html=True, address=TEAM_LOGIN), *LIVE]
    with pytest.raises(DashboardPrivateError):
        await DashboardStep().run(_context(world))
    world.io.answers.extend(FIRST_PUBLISH)

    await DashboardStep().run(_context(world))

    assert world.env.values["DASHBOARD_BASE_URL"] == SITE
    assert world.netlify.created == ["threadline-abc123"]


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


async def test_the_download_must_carry_the_template_workflow_s_signed_provenance() -> None:
    world = _world(FIRST_PUBLISH)

    await DashboardStep().run(_context(world))

    assert world.github.attested == [
        (
            world.downloads[ARCHIVE_URL],
            TEMPLATE_REPOSITORY,
            SIGNER_WORKFLOW,
            PROVENANCE_SOURCE_REF,
        )
    ]
    assert "Checked who built it" in world.io.text()


async def test_a_download_whose_provenance_is_not_confirmed_publishes_nothing() -> None:
    world = _world(FIRST_PUBLISH)
    world.github.attestation_ok = False

    with pytest.raises(DashboardProvenanceError, match="Node.js"):
        await DashboardStep().run(_context(world))

    assert world.io.secret_prompts == []
    assert world.netlify.deployed == []
    assert "DASHBOARD_BASE_URL" not in world.env.values


async def test_gh_that_is_not_signed_in_cannot_confirm_it_and_says_so() -> None:
    world = _world(FIRST_PUBLISH)
    world.github.signed_in = False

    with pytest.raises(DashboardProvenanceError, match="gh auth login"):
        await DashboardStep().run(_context(world))

    assert world.github.attested == []
    assert world.netlify.deployed == []


async def test_gh_that_is_not_installed_is_told_apart_from_one_not_signed_in() -> None:
    world = _world(FIRST_PUBLISH)
    world.github.is_installed = False

    with pytest.raises(DashboardProvenanceError) as raised:
        await DashboardStep().run(_context(world))

    assert raised.value.message == (
        "The ready-made dashboard is checked with the GitHub CLI, which is not installed. "
        "Install it from https://cli.github.com, sign in with 'gh auth login', and run this "
        "step again."
    )
    assert world.github.attested == []
    assert world.netlify.deployed == []


async def test_a_dashboard_check_that_cannot_run_still_offers_the_local_build() -> None:
    world = _world([True, True, True, GOOD_NETLIFY_TOKEN])
    world.github.is_installed = False
    world.local_build.present = True

    await DashboardStep().run(_context(world))

    assert "which is not installed" in world.io.text()
    assert world.local_build.builds == 1


async def test_a_bad_checksum_is_found_before_the_provenance_is_asked_for() -> None:
    world = _world(FIRST_PUBLISH)
    world.downloads[CHECKSUM_URL] = b"0" * 64 + b"  dashboard.zip\n"

    with pytest.raises(DashboardPackageError, match="does not match its checksum"):
        await DashboardStep().run(_context(world))

    assert world.github.attested == []


async def test_an_unconfirmed_download_can_be_replaced_by_a_local_build() -> None:
    world = _world([True, True, True, GOOD_NETLIFY_TOKEN])
    world.github.attestation_ok = False
    world.local_build.present = True
    world.local_build.files = {**BUILT_SITE, "index.html": b"<!doctype html>local"}

    await DashboardStep().run(_context(world))

    assert world.local_build.builds == 1
    assert _published_files(world)["index.html"] == b"<!doctype html>local"
    assert "could not confirm" in world.io.text()


async def test_an_unconfirmed_download_is_not_replaced_when_the_owner_declines() -> None:
    world = _world([True, False])
    world.github.attestation_ok = False
    world.local_build.present = True

    with pytest.raises(DashboardProvenanceError):
        await DashboardStep().run(_context(world))

    assert world.local_build.builds == 0
    assert world.netlify.deployed == []


async def test_a_local_build_needs_no_provenance() -> None:
    world = _world([True, True, GOOD_NETLIFY_TOKEN])
    world.local_build.present = True
    world.github.attestation_ok = False

    await DashboardStep().run(_building_here(world))

    assert world.github.attested == []


def _release_built_for(migration: str | None) -> dict[str, bytes]:
    """The release downloads, with the build info the workflow writes."""
    info = {"commit": "b" * 40, "latestMigration": migration}
    return release_downloads({**BUILT_SITE, "build-info.json": json.dumps(info).encode()})


async def test_a_dashboard_built_for_a_newer_database_warns_before_it_is_published() -> None:
    world = _world(FIRST_PUBLISH)
    world.downloads = _release_built_for("9999_from_the_future")

    await DashboardStep().run(_context(world))

    text = world.io.text()
    assert "expects a newer database" in text
    assert "9999_from_the_future" in text
    assert "update your copy of Threadline first" in text
    assert "DASHBOARD_BASE_URL" in world.env.values
    assert "build-info.json" not in _published_files(world)


async def test_a_dashboard_built_for_the_database_you_have_says_nothing_about_it() -> None:
    world = _world(FIRST_PUBLISH)
    world.downloads = _release_built_for(max(KNOWN_MIGRATIONS))

    await DashboardStep().run(_context(world))

    assert "newer database" not in world.io.text()


async def test_a_release_with_no_build_info_is_published_without_a_database_warning() -> None:
    world = _world(FIRST_PUBLISH)

    await DashboardStep().run(_context(world))

    assert "newer database" not in world.io.text()


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


async def test_a_legacy_service_role_key_typed_as_the_public_one_never_reaches_the_page() -> None:
    claims = base64.urlsafe_b64encode(b'{"role":"service_role"}').rstrip(b"=").decode()
    legacy_service_key = f"eyJhbGciOiJIUzI1NiJ9.{claims}.signature"
    env = configured_env() | {"SUPABASE_ANON_KEY": legacy_service_key}
    world = _world(FIRST_PUBLISH, env)

    with pytest.raises(ValidationFailedError, match="secret key"):
        await DashboardStep().run(_context(world))

    assert world.netlify.deployed == []
    assert world.io.secret_prompts == []


async def test_build_here_publishes_a_local_build_without_downloading() -> None:
    world = _world([True, True, GOOD_NETLIFY_TOKEN])
    world.local_build.present = True
    world.local_build.files = {**BUILT_SITE, "index.html": b"<!doctype html>local"}
    world.downloads = {}

    await DashboardStep().run(_building_here(world))

    assert world.local_build.builds == 1
    assert _published_files(world)["index.html"] == b"<!doctype html>local"


async def test_build_here_without_node_stops_before_anything_is_published() -> None:
    world = _world([True])

    with pytest.raises(ValidationFailedError, match="needs Node.js 22 or newer"):
        await DashboardStep().run(_building_here(world))

    assert world.local_build.builds == 0
    assert world.netlify.deployed == []


async def test_having_node_alone_never_asks_to_build_here() -> None:
    world = _world([True, True, GOOD_NETLIFY_TOKEN])
    world.local_build.present = True

    await DashboardStep().run(_context(world))

    assert world.local_build.builds == 0
    assert "Build it here" not in world.io.text()
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


async def test_the_redirect_addresses_already_on_the_list_are_kept_and_the_new_one_added() -> None:
    world = _world(FIRST_PUBLISH)
    world.platform.redirect_list = ["http://localhost:5173/**", "https://old.vercel.app/**"]

    await DashboardStep().run(_context(world))

    assert world.platform.auth_changes == [
        (
            PROJECT_REF,
            AuthSettings(
                site_url=SITE,
                redirect_urls=(
                    "http://localhost:5173/**",
                    "https://old.vercel.app/**",
                    f"{SITE}/**",
                ),
            ),
        )
    ]
    assert f"Added {SITE}/** to Supabase's redirect addresses." in world.io.said
    assert "The ones you already had were left as they were." in world.io.said


async def test_an_address_that_is_already_on_the_list_is_not_added_twice() -> None:
    world = _world(FIRST_PUBLISH)
    world.platform.redirect_list = [f"{SITE}/**", "http://localhost:5173/**"]

    await DashboardStep().run(_context(world))

    [(_, settings)] = world.platform.auth_changes
    assert settings.redirect_urls == (f"{SITE}/**", "http://localhost:5173/**")
    assert f"Supabase's redirect addresses already hold {SITE}/**." in world.io.said


async def test_a_list_that_cannot_be_read_is_not_overwritten() -> None:
    world = _world(FIRST_PUBLISH)
    world.platform.redirect_list = ["http://localhost:5173/**"]
    world.platform.auth_refusal = SourceUnavailableError

    await DashboardStep().run(_context(world))

    assert world.platform.auth_changes == []
    assert world.platform.redirect_list == ["http://localhost:5173/**"]
    assert f"  Redirect URLs: add {SITE}/**" in world.io.said


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


async def test_an_unreachable_supabase_also_falls_back_to_typing_the_two_values() -> None:
    world = _world(FIRST_PUBLISH)
    world.platform.auth_refusal = SourceUnavailableError

    await DashboardStep().run(_context(world))

    assert "Supabase would not change the sign-in addresses" in world.io.text()
    assert f"  Redirect URLs: add {SITE}/**" in world.io.said
    assert world.env.values["DASHBOARD_BASE_URL"] == SITE


async def test_a_scoped_token_falls_back_to_typing_the_two_values_with_the_fix() -> None:
    world = _world([*FIRST_PUBLISH, True, NARROW_TOKEN])
    ctx = world.context()

    await DashboardStep().run(ctx)

    assert world.io.opened.count(SUPABASE_TOKENS_PAGE) == 1
    assert "click the small link 'Create legacy token'" in world.io.text()
    said = f"Supabase would not change the sign-in addresses: {TOO_LITTLE_ACCESS}."
    assert said in world.io.said
    assert f"  Redirect URLs: add {SITE}/**" in world.io.said
    assert ctx.session.supabase_token is None


async def test_a_refused_token_also_falls_back_to_typing_the_two_values() -> None:
    world = _world(FIRST_PUBLISH)
    world.platform.auth_refusal = SourceAuthError

    await DashboardStep().run(_context(world))

    assert f"  Site URL: {SITE}" in world.io.said
