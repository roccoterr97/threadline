"""One Supabase access token for the whole set-up: project, keys, structure, sign-ups."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from tests.setup_world import (
    GOOD_GITHUB_TOKEN,
    GOOD_PUBLISHABLE,
    GOOD_SECRET,
    GOOD_TOKEN,
    NARROW_TOKEN,
    NEW_PROJECT_REF,
    ORGANIZATION,
    OWNER_EMAIL,
    PASTE,
    PROJECT_REF,
    PROJECT_URL,
    World,
    configured_env,
    make_world,
)
from tracker.domain.supabase import ApiKey, ApiKeyKind, AuthSettings, Organization, SupabaseProject
from tracker.services.database_structure import KNOWN_MIGRATIONS
from tracker.services.setup.context import SetupContext
from tracker.services.setup.step_database import DatabaseStep
from tracker.services.setup.step_login import LoginStep
from tracker.services.setup.step_refresh import RefreshStep
from tracker.services.setup.step_supabase import SupabaseStep
from tracker.services.setup.supabase_project import region_group_for
from tracker.services.setup.supabase_session import (
    TOKEN_PROMPT,
    TOKEN_STEPS,
    TOO_LITTLE_ACCESS,
    require_supabase_token,
)
from tracker.shared.constants.setup import (
    DATABASE_PASSWORD_BYTES,
    NEW_PROJECT_ANSWER_ATTEMPTS,
    NEW_PROJECT_ANSWER_WAIT_SECONDS,
    PROJECT_READY_ATTEMPTS,
    PROJECT_READY_WAIT_SECONDS,
    SIGNUP_CHECK_WAIT_SECONDS,
    SUPABASE_TOKENS_PAGE,
    RegionGroup,
)
from tracker.shared.errors import (
    DatabaseUnavailableError,
    SourceAuthError,
    SourcePermissionError,
    SourceRequestRejectedError,
    SourceUnavailableError,
    ValidationFailedError,
)

pytestmark = pytest.mark.asyncio

NEW_PROJECT_URL = f"https://{NEW_PROJECT_REF}.supabase.co"

#: Yes to the automatic route, the token, the offered name and the offered region.
CREATE_NEW: list[str | bool] = [True, PASTE, GOOD_TOKEN, "", ""]


def _existing(
    name: str,
    *,
    status: str = "ACTIVE_HEALTHY",
    org: str = ORGANIZATION.slug,
    ref: str = PROJECT_REF,
) -> SupabaseProject:
    return SupabaseProject(ref, name, org, status)


def _text_and_env(world: World) -> str:
    return world.io.text() + "\n".join(world.env.values.values())


# --- The project, created with the token ----------------------------------------


async def test_one_token_creates_the_project_and_saves_its_address_and_keys() -> None:
    world = make_world(list(CREATE_NEW))

    await SupabaseStep().run(world.context())

    assert world.env.values == {
        "SUPABASE_URL": NEW_PROJECT_URL,
        "SUPABASE_ANON_KEY": GOOD_PUBLISHABLE,
        "SUPABASE_SERVICE_ROLE_KEY": GOOD_SECRET,
    }
    [request] = world.platform.created
    assert (request.name, request.organization_slug) == ("threadline", ORGANIZATION.slug)
    assert request.region is RegionGroup.EMEA
    assert world.io.secret_prompts == [TOKEN_PROMPT]
    assert world.io.opened == [SUPABASE_TOKENS_PAGE]
    assert world.waits == [PROJECT_READY_WAIT_SECONDS, PROJECT_READY_WAIT_SECONDS]
    assert "Supabase accepted the address and both keys." in world.io.said


async def test_neither_the_token_nor_the_password_nor_the_secret_key_is_shown() -> None:
    world = make_world(list(CREATE_NEW))

    await SupabaseStep().run(world.context())

    password = world.platform.created[0].database_password.get_secret_value()
    assert len(password) >= DATABASE_PASSWORD_BYTES
    shown = world.io.text()
    for secret in (GOOD_TOKEN, password, GOOD_SECRET):
        assert secret not in shown
    assert GOOD_TOKEN not in _text_and_env(world)
    assert password not in _text_and_env(world)
    assert "reset it in the Supabase dashboard" in shown


async def test_a_refused_token_is_asked_for_again_and_never_kept() -> None:
    world = make_world([True, PASTE, "sbp_wrong", GOOD_TOKEN, "", ""])

    await SupabaseStep().run(world.context())

    assert "Supabase did not accept the access token" in world.io.text()
    # Two tokens checked, then the accepted one lists the organizations.
    assert world.platform.organization_reads == 3
    assert world.env.values["SUPABASE_URL"] == NEW_PROJECT_URL


async def test_the_steps_lead_to_a_legacy_token_on_supabases_page() -> None:
    world = make_world(list(CREATE_NEW))

    await SupabaseStep().run(world.context())

    for line in TOKEN_STEPS:
        assert line in world.io.said
    assert "click the small link 'Create legacy token'" in world.io.text()
    assert "whole account" not in world.io.text()


async def test_a_scoped_token_turned_away_at_once_is_asked_for_again_with_the_fix() -> None:
    world = make_world([True, PASTE, NARROW_TOKEN, GOOD_TOKEN, "", ""])
    world.platform.narrow_may_list = False

    await SupabaseStep().run(world.context())

    assert f"  {TOO_LITTLE_ACCESS}. Please try again." in world.io.said
    assert "did not accept" not in world.io.text()
    assert world.env.values["SUPABASE_URL"] == NEW_PROJECT_URL


async def test_a_scoped_token_that_may_not_read_the_keys_stops_with_the_fix() -> None:
    world = make_world([True, PASTE, NARROW_TOKEN, "", ""])
    ctx = world.context()

    with pytest.raises(SourcePermissionError) as raised:
        await SupabaseStep().run(ctx)

    assert raised.value.message == TOO_LITTLE_ACCESS
    assert "Create legacy token" in raised.value.message
    assert ctx.session.supabase_token is None
    assert world.env.values == {}


async def test_a_token_refused_every_time_creates_nothing() -> None:
    world = make_world([True, PASTE, "bad", "bad", "bad"])

    with pytest.raises(SourceAuthError):
        await SupabaseStep().run(world.context())

    assert world.platform.created == []
    assert world.env.values == {}


async def test_an_account_without_an_organization_stops_with_a_clear_message() -> None:
    world = make_world([True, PASTE, GOOD_TOKEN])
    world.platform.organization_list = []

    with pytest.raises(ValidationFailedError, match="no organization yet"):
        await SupabaseStep().run(world.context())

    assert world.platform.created == []


async def test_with_several_organizations_the_chosen_one_is_used() -> None:
    world = make_world([True, PASTE, GOOD_TOKEN, "4", "2", "", ""])
    other = Organization(slug="second-org", name="Second organization")
    world.platform.organization_list = [ORGANIZATION, other]

    await SupabaseStep().run(world.context())

    assert world.platform.created[0].organization_slug == "second-org"
    assert "type a number from 1 to 2" in world.io.text()


async def test_an_existing_project_can_be_used_instead() -> None:
    world = make_world([True, PASTE, GOOD_TOKEN, True])
    world.platform.project_list = [_existing("old-tracker")]

    await SupabaseStep().run(world.context())

    assert world.env.values["SUPABASE_URL"] == PROJECT_URL
    assert world.platform.created == []
    assert world.waits == []
    assert "  1. old-tracker (running)" in world.io.said


async def test_declining_the_existing_projects_creates_a_named_one_where_chosen() -> None:
    world = make_world([True, PASTE, GOOD_TOKEN, False, "my-tracker", "1"])
    world.platform.project_list = [_existing("old-tracker")]

    await SupabaseStep().run(world.context())

    [request] = world.platform.created
    assert (request.name, request.region) == ("my-tracker", RegionGroup.AMERICAS)


async def test_projects_of_other_organizations_are_not_offered() -> None:
    world = make_world(list(CREATE_NEW))
    world.platform.project_list = [_existing("elsewhere", org="someone-else")]

    await SupabaseStep().run(world.context())

    assert "elsewhere" not in world.io.text()
    assert len(world.platform.created) == 1


async def test_a_paused_project_is_named_with_how_to_restore_it_but_not_offered() -> None:
    world = make_world(list(CREATE_NEW))
    world.platform.project_list = [
        _existing("paused-one", status="INACTIVE"),
        _existing("elsewhere", org="someone-else", status="INACTIVE"),
    ]

    await SupabaseStep().run(world.context())

    assert "'paused-one' is paused. Restore it in Supabase" in world.io.text()
    assert "run this step again, or create a new project" in world.io.text()
    assert "elsewhere" not in world.io.text()
    assert "Projects already there" not in world.io.text()
    assert len(world.platform.created) == 1


async def test_a_paused_project_is_mentioned_beside_the_ones_that_can_be_used() -> None:
    world = make_world([True, PASTE, GOOD_TOKEN, True])
    world.platform.project_list = [
        _existing("old-tracker"),
        _existing("paused-one", status="INACTIVE", ref="pausedprojectref"),
    ]

    await SupabaseStep().run(world.context())

    assert "'paused-one' is paused." in world.io.text()
    assert "  1. old-tracker (running)" in world.io.said
    assert "paused-one (" not in world.io.text()
    assert world.env.values["SUPABASE_URL"] == PROJECT_URL


async def test_a_project_left_by_a_stopped_run_is_reused_by_just_pressing_enter() -> None:
    world = make_world([True, PASTE, GOOD_TOKEN, ""])
    world.platform.project_list = [_existing("threadline", status="COMING_UP")]

    await SupabaseStep().run(world.context())

    assert world.platform.created == []
    assert world.env.values["SUPABASE_URL"] == PROJECT_URL
    assert "  1. threadline (still being set up)" in world.io.said
    assert len(world.waits) == 2


async def test_the_project_named_threadline_is_the_default_among_several() -> None:
    world = make_world([True, PASTE, GOOD_TOKEN, "", ""])
    other_ref = "someotherprojectref"
    world.platform.project_list = [
        _existing("old-tracker", ref=other_ref),
        _existing("threadline", status="COMING_UP"),
    ]

    await SupabaseStep().run(world.context())

    assert world.platform.created == []
    assert world.env.values["SUPABASE_URL"] == PROJECT_URL
    assert "  1. old-tracker (running)" in world.io.said
    assert "  2. threadline (still being set up)" in world.io.said


async def test_a_project_with_another_name_is_not_chosen_by_just_pressing_enter() -> None:
    world = make_world([True, PASTE, GOOD_TOKEN, "", "", ""])
    world.platform.project_list = [_existing("old-tracker")]

    await SupabaseStep().run(world.context())

    assert len(world.platform.created) == 1


async def test_a_project_that_never_comes_up_stops_cleanly() -> None:
    world = make_world(list(CREATE_NEW))
    world.platform.statuses = ["COMING_UP"]

    with pytest.raises(ValidationFailedError, match="still being set up after 5 minutes"):
        await SupabaseStep().run(world.context())

    assert len(world.waits) == PROJECT_READY_ATTEMPTS
    assert world.env.values == {}


async def test_the_timeout_message_says_the_project_exists_and_must_not_be_created_again() -> None:
    world = make_world(list(CREATE_NEW))
    world.platform.statuses = ["COMING_UP"]

    with pytest.raises(ValidationFailedError, match="already created.*do not create another"):
        await SupabaseStep().run(world.context())


async def test_the_wait_says_what_a_stop_leaves_behind() -> None:
    world = make_world(list(CREATE_NEW))

    await SupabaseStep().run(world.context())

    assert "Ctrl-C" in world.io.text()
    assert "pick it from the list" in world.io.text()


async def test_a_create_request_lost_to_a_timeout_warns_that_a_project_may_exist() -> None:
    world = make_world(list(CREATE_NEW))
    world.platform.create_times_out = True

    with pytest.raises(SourceUnavailableError):
        await SupabaseStep().run(world.context())

    assert "may already have been created" in world.io.text()
    assert world.env.values == {}


async def test_a_new_project_that_does_not_answer_yet_is_asked_again() -> None:
    world = make_world(list(CREATE_NEW))
    world.platform.unanswered_settings = 2
    world.admin.unanswered_calls = 2

    await SupabaseStep().run(world.context())

    assert world.waits[2:] == [NEW_PROJECT_ANSWER_WAIT_SECONDS] * 4
    assert world.env.values["SUPABASE_SERVICE_ROLE_KEY"] == GOOD_SECRET


async def test_a_new_project_that_never_answers_stops_with_a_hint_to_run_again() -> None:
    world = make_world(list(CREATE_NEW))
    world.platform.unanswered_settings = 99

    with pytest.raises(SourceUnavailableError):
        await SupabaseStep().run(world.context())

    assert world.waits[2:] == [NEW_PROJECT_ANSWER_WAIT_SECONDS] * (NEW_PROJECT_ANSWER_ATTEMPTS - 1)
    assert "does not answer yet" in world.io.text()
    assert world.env.values == {}


async def test_a_project_supabase_gives_up_on_is_reported() -> None:
    world = make_world(list(CREATE_NEW))
    world.platform.statuses = ["COMING_UP", "INIT_FAILED"]

    with pytest.raises(SourceUnavailableError, match="INIT_FAILED"):
        await SupabaseStep().run(world.context())


async def test_too_many_requests_while_waiting_is_simply_waited_out() -> None:
    world = make_world(list(CREATE_NEW))
    world.platform.busy_looks = 2

    await SupabaseStep().run(world.context())

    assert len(world.waits) == 4
    assert world.env.values["SUPABASE_URL"] == NEW_PROJECT_URL


async def test_a_refused_project_shows_supabases_reason() -> None:
    world = make_world(list(CREATE_NEW))
    world.platform.create_refusal = "the organization has reached its free project limit"

    with pytest.raises(SourceRequestRejectedError, match="free project limit"):
        await SupabaseStep().run(world.context())

    assert world.env.values == {}


# --- Running the step again ----------------------------------------------------


async def test_running_the_step_again_keeps_the_project_before_asking_for_any_token() -> None:
    world = make_world([True], configured_env())

    await SupabaseStep().run(world.context())

    assert world.io.secret_prompts == []
    assert world.platform.organization_reads == 0
    assert world.platform.created == []
    assert world.env.values == configured_env()
    assert PROJECT_REF in world.io.text()
    assert "Kept the project" in world.io.text()


async def test_the_saved_project_is_kept_just_by_pressing_enter() -> None:
    world = make_world([""], configured_env())

    await SupabaseStep().run(world.context())

    assert world.platform.created == []
    assert world.env.values == configured_env()


async def test_choosing_another_project_replaces_the_saved_one_without_asking_twice() -> None:
    world = make_world([False, True, PASTE, GOOD_TOKEN, "", ""], configured_env())

    await SupabaseStep().run(world.context())

    assert world.env.values["SUPABASE_URL"] == NEW_PROJECT_URL
    assert "Replace it?" not in world.io.text()
    assert len(world.platform.created) == 1


async def test_a_saved_address_that_is_not_a_project_is_replaced_not_kept() -> None:
    env = configured_env() | {"SUPABASE_URL": "https://example.com"}
    world = make_world([True, PASTE, GOOD_TOKEN, "", ""], env)

    await SupabaseStep().run(world.context())

    assert "does not look like a Supabase project" in world.io.text()
    assert world.env.values["SUPABASE_URL"] == NEW_PROJECT_URL


# --- The keys ------------------------------------------------------------------


async def test_missing_keys_are_created() -> None:
    world = make_world(list(CREATE_NEW))
    world.platform.keys = []

    await SupabaseStep().run(world.context())

    assert world.platform.created_keys == [
        (ApiKeyKind.PUBLISHABLE, "threadline_dashboard"),
        (ApiKeyKind.SECRET, "threadline_backend"),
    ]
    assert world.env.values["SUPABASE_SERVICE_ROLE_KEY"] == GOOD_SECRET


async def test_a_secret_key_the_token_may_not_reveal_is_never_saved() -> None:
    world = make_world(list(CREATE_NEW))
    world.platform.keys = [
        ApiKey(ApiKeyKind.PUBLISHABLE, "default", SecretStr(GOOD_PUBLISHABLE)),
        ApiKey(ApiKeyKind.SECRET, "default", SecretStr("sb_secret_abcd····")),
    ]

    with pytest.raises(SourcePermissionError, match="Create legacy token"):
        await SupabaseStep().run(world.context())

    assert world.env.values == {}
    assert world.platform.created_keys == []


async def test_keys_that_supabase_then_refuses_are_not_saved() -> None:
    world = make_world(list(CREATE_NEW))
    world.platform.keys = [
        ApiKey(ApiKeyKind.PUBLISHABLE, "default", SecretStr("sb_publishable_other")),
        ApiKey(ApiKeyKind.SECRET, "default", SecretStr(GOOD_SECRET)),
    ]

    with pytest.raises(SourceAuthError, match="publishable key"):
        await SupabaseStep().run(world.context())

    assert world.env.values == {}


@pytest.mark.parametrize(
    ("zone", "group"),
    [
        ("Europe/Rome", RegionGroup.EMEA),
        ("Africa/Lagos", RegionGroup.EMEA),
        ("Asia/Tokyo", RegionGroup.APAC),
        ("Australia/Sydney", RegionGroup.APAC),
        ("America/New_York", RegionGroup.AMERICAS),
        ("UTC", RegionGroup.AMERICAS),
        (None, RegionGroup.AMERICAS),
    ],
)
async def test_the_region_offered_follows_the_time_zone(
    zone: str | None, group: RegionGroup
) -> None:
    assert region_group_for(zone) is group


# --- One token for the whole run -----------------------------------------------


async def test_the_token_is_asked_once_and_then_kept_for_the_run() -> None:
    world = make_world([PASTE, GOOD_TOKEN])
    ctx = world.context()

    first = await require_supabase_token(ctx)
    second = await require_supabase_token(ctx)

    assert first is second
    assert world.platform.organization_reads == 1
    assert world.io.opened == [SUPABASE_TOKENS_PAGE]


async def test_a_token_pasted_with_spaces_or_line_breaks_is_cleaned() -> None:
    world = make_world([PASTE, f" {GOOD_TOKEN}\n"])

    token = await require_supabase_token(world.context())

    assert token.get_secret_value() == GOOD_TOKEN


async def test_project_structure_and_signups_share_one_token() -> None:
    world = make_world([*CREATE_NEW, OWNER_EMAIL])
    world.admin.present = {"0001_schema", "0002_access_rules"}
    world.platform.signups_off = [False]
    ctx = world.context()

    await SupabaseStep().run(ctx)
    await DatabaseStep().run(ctx)
    await LoginStep().run(ctx)

    assert world.io.secret_prompts == [TOKEN_PROMPT]
    assert world.platform.applied == [n for n in KNOWN_MIGRATIONS if n > "0002_access_rules"]
    assert world.platform.auth_changes == [(NEW_PROJECT_REF, AuthSettings(disable_signup=True))]
    assert "Apply them automatically?" not in world.io.text()


# --- The database structure ----------------------------------------------------


async def test_a_token_that_may_not_apply_the_structure_falls_back_to_the_editor() -> None:
    world = make_world([True, PASTE, GOOD_TOKEN], configured_env())
    world.admin.present = set(KNOWN_MIGRATIONS) - {"0006_meeting_time"}
    world.platform.migrations_allowed = False
    world.io.on_pause = lambda prompt: world.admin.present.add("0006_meeting_time")

    await DatabaseStep().run(world.context())

    assert "Carrying on by hand instead." in world.io.said
    assert world.platform.applied == []
    assert "The database structure is in place." in world.io.said


async def test_a_scoped_token_falls_back_to_the_editor_and_says_how_to_fix_it() -> None:
    world = make_world([True, PASTE, NARROW_TOKEN], configured_env())
    world.admin.present = set(KNOWN_MIGRATIONS) - {"0006_meeting_time"}
    world.io.on_pause = lambda prompt: world.admin.present.add("0006_meeting_time")
    ctx = world.context()

    await DatabaseStep().run(ctx)

    assert f"{TOO_LITTLE_ACCESS}." in world.io.said
    assert "Carrying on by hand instead." in world.io.said
    assert ctx.session.supabase_token is None
    assert "The database structure is in place." in world.io.said


async def test_the_structure_check_asks_again_while_a_new_project_wakes_up() -> None:
    world = make_world([], configured_env())
    world.admin.unanswered_calls = 2

    await DatabaseStep().run(world.context())

    assert world.waits == [NEW_PROJECT_ANSWER_WAIT_SECONDS] * 2
    assert "Every structure file is already applied." in world.io.said


async def test_a_database_that_never_answers_stops_the_structure_check() -> None:
    world = make_world([], configured_env())
    world.admin.unanswered_calls = 99

    with pytest.raises(DatabaseUnavailableError):
        await DatabaseStep().run(world.context())

    assert len(world.waits) == NEW_PROJECT_ANSWER_ATTEMPTS - 1
    assert "does not answer yet" in world.io.text()


# --- Sign-ups ------------------------------------------------------------------


async def test_signups_are_switched_off_through_the_api() -> None:
    world = make_world([OWNER_EMAIL, True, PASTE, GOOD_TOKEN], configured_env())
    world.platform.signups_off = [False]

    await LoginStep().run(world.context())

    assert world.platform.auth_changes == [(PROJECT_REF, AuthSettings(disable_signup=True))]
    assert world.io.opened == [SUPABASE_TOKENS_PAGE]
    assert "Sign-ups are now switched off: nobody else can create a login." in world.io.said
    assert "[paused]" not in world.io.text()


async def test_the_switch_is_read_again_until_it_shows() -> None:
    world = make_world([OWNER_EMAIL, True, PASTE, GOOD_TOKEN], configured_env())
    world.platform.signups_off = [False]
    world.platform.signups_after_change = [False, False, True]

    await LoginStep().run(world.context())

    assert world.waits == [SIGNUP_CHECK_WAIT_SECONDS, SIGNUP_CHECK_WAIT_SECONDS]


@pytest.mark.parametrize(
    "refusal", [SourceAuthError, SourceRequestRejectedError, SourceUnavailableError]
)
async def test_a_failed_switch_falls_back_to_the_settings_page(refusal: type[Exception]) -> None:
    world = make_world([OWNER_EMAIL, True, PASTE, GOOD_TOKEN], configured_env())
    world.platform.signups_off = [False]
    world.platform.auth_refusal = refusal

    def saved_by_hand(prompt: str) -> None:
        world.platform.signups_off = [True]

    world.io.on_pause = saved_by_hand

    await LoginStep().run(world.context())

    assert "Supabase would not change the setting" in world.io.text()
    assert world.io.opened[-1].endswith(f"/project/{PROJECT_REF}/auth/providers")
    assert "Sign-ups are now switched off." in world.io.said


async def test_a_scoped_token_switches_signups_off_by_hand_and_is_forgotten() -> None:
    world = make_world([OWNER_EMAIL, True, PASTE, NARROW_TOKEN], configured_env())
    world.platform.signups_off = [False]

    def saved_by_hand(prompt: str) -> None:
        world.platform.signups_off = [True]

    world.io.on_pause = saved_by_hand
    ctx = world.context()

    await LoginStep().run(ctx)

    assert f"Supabase would not change the setting: {TOO_LITTLE_ACCESS}." in world.io.said
    assert world.io.opened[-1].endswith(f"/project/{PROJECT_REF}/auth/providers")
    assert ctx.session.supabase_token is None


async def test_signups_already_off_need_no_token() -> None:
    world = make_world([OWNER_EMAIL], configured_env())

    await LoginStep().run(world.context())

    assert world.io.secret_prompts == []
    assert world.platform.auth_changes == []


# --- Refresh now ---------------------------------------------------------------


async def test_refresh_now_with_a_scoped_token_stops_with_the_fix() -> None:
    env = configured_env() | {"DASHBOARD_BASE_URL": "https://you.vercel.app"}
    world = make_world([True, GOOD_GITHUB_TOKEN], env)
    ctx: SetupContext = world.context()
    ctx.session.supabase_token = SecretStr(NARROW_TOKEN)

    with pytest.raises(SourcePermissionError, match="Create legacy token"):
        await RefreshStep().run(ctx)

    assert world.platform.secrets == {}
    assert world.platform.deployed == []
    assert ctx.session.supabase_token is None


async def test_refresh_now_reuses_the_runs_token() -> None:
    env = configured_env() | {"DASHBOARD_BASE_URL": "https://you.vercel.app"}
    world = make_world([True, GOOD_GITHUB_TOKEN], env)
    world.function_statuses = [404, 401]
    ctx: SetupContext = world.context()
    ctx.session.supabase_token = SecretStr(GOOD_TOKEN)

    await RefreshStep().run(ctx)

    assert len(world.io.secret_prompts) == 1
    assert SUPABASE_TOKENS_PAGE not in world.io.opened
    assert world.platform.deployed
