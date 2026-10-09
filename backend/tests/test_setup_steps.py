"""Every set-up step, without a terminal or a network: happy paths and refusals."""

from __future__ import annotations

from datetime import date

import pytest

from tests.setup_world import (
    GOOD_LINKEDIN,
    GOOD_PUBLISHABLE,
    GOOD_SECRET,
    GOOD_TOKEN,
    OWNER_EMAIL,
    PROJECT_REF,
    PROJECT_URL,
    World,
    configured_env,
    make_world,
)
from tracker.domain.categories import UNKNOWN_CATEGORY_KEY, Category, ColourSlot
from tracker.services.database_structure import KNOWN_MIGRATIONS
from tracker.services.setup import values
from tracker.services.setup.context import SetupContext
from tracker.services.setup.models import StepGroup, StepName
from tracker.services.setup.step_categories import CategoriesStep
from tracker.services.setup.step_cloud import CloudStep
from tracker.services.setup.step_database import DatabaseStep
from tracker.services.setup.step_linkedin import LinkedInStep
from tracker.services.setup.step_login import LoginStep
from tracker.services.setup.step_microsoft import MicrosoftStep
from tracker.services.setup.step_supabase import EncryptionStep, SupabaseStep, is_usable_key
from tracker.services.setup.step_time_zone import TimeZoneStep
from tracker.services.setup.supabase_session import TOKEN_PROMPT
from tracker.services.setup.wizard import SetupWizard, core_steps, default_steps, extra_steps
from tracker.shared.constants.setup import (
    LINKEDIN_DEVELOPER_APPS_PAGE,
    LINKEDIN_GUIDE_SECTION,
    LINKEDIN_TOKEN_GENERATOR_PAGE,
    MIGRATION_PAUSE_SECONDS,
    MIGRATION_RETRY_WAIT_SECONDS,
)
from tracker.shared.errors import SourceAuthError, ValidationFailedError

pytestmark = pytest.mark.asyncio

# --- Supabase ------------------------------------------------------------------


async def test_supabase_by_hand_saves_the_address_and_keys_once_accepted() -> None:
    world = make_world([False, PROJECT_REF, GOOD_PUBLISHABLE, GOOD_SECRET])

    await SupabaseStep().run(world.context())

    assert world.env.values == {
        "SUPABASE_URL": PROJECT_URL,
        "SUPABASE_ANON_KEY": GOOD_PUBLISHABLE,
        "SUPABASE_SERVICE_ROLE_KEY": GOOD_SECRET,
    }
    assert GOOD_SECRET not in world.io.text()
    assert any("api-keys" in url for url in world.io.opened)


async def test_supabase_asks_again_after_a_refused_key() -> None:
    world = make_world([False, PROJECT_URL, "wrong", GOOD_PUBLISHABLE, "wrong", GOOD_SECRET])

    await SupabaseStep().run(world.context())

    assert world.env.values["SUPABASE_SERVICE_ROLE_KEY"] == GOOD_SECRET
    assert "did not accept the publishable key" in world.io.text()
    assert "refused the secret key" in world.io.text()


async def test_supabase_writes_nothing_when_the_key_is_refused_every_time() -> None:
    world = make_world([False, PROJECT_URL, "bad", "bad", "bad"])

    with pytest.raises(SourceAuthError):
        await SupabaseStep().run(world.context())

    assert world.env.values == {}


async def test_supabase_refuses_an_address_that_is_not_a_project() -> None:
    world = make_world([False, "https://example.com", "http://x.supabase.co", "nope"])

    with pytest.raises(ValidationFailedError, match="supabase.co"):
        await SupabaseStep().run(world.context())


async def test_an_existing_value_is_only_replaced_after_asking() -> None:
    env = {"SUPABASE_URL": "https://zzzzzzzzzzzz.supabase.co"}
    world = make_world([False, PROJECT_URL, GOOD_PUBLISHABLE, GOOD_SECRET, False], env)

    await SupabaseStep().run(world.context())

    assert world.env.values["SUPABASE_URL"] == "https://zzzzzzzzzzzz.supabase.co"
    assert "Kept the existing SUPABASE_URL." in world.io.said


# --- Encryption ----------------------------------------------------------------


async def test_the_encryption_key_is_generated_and_never_shown() -> None:
    world = make_world()

    await EncryptionStep().run(world.context())

    assert world.env.values["TOKEN_ENCRYPTION_KEY"] == "generated-key"
    assert "generated-key" not in world.io.text()


async def test_a_usable_encryption_key_is_kept() -> None:
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode()
    world = make_world(env={"TOKEN_ENCRYPTION_KEY": key})

    assert await EncryptionStep().is_done(world.context())
    await EncryptionStep().run(world.context())

    assert world.env.values["TOKEN_ENCRYPTION_KEY"] == key


async def test_a_malformed_key_is_not_usable() -> None:
    assert not is_usable_key("not-a-key")
    assert not is_usable_key(None)


# --- Database ------------------------------------------------------------------


async def test_database_with_everything_applied_changes_nothing() -> None:
    world = make_world(env=configured_env())

    await DatabaseStep().run(world.context())

    assert world.platform.applied == []
    assert "already applied" in world.io.text()


async def test_database_applies_missing_files_automatically() -> None:
    world = make_world([True, GOOD_TOKEN], configured_env())
    world.admin.present = {"0001_schema", "0002_access_rules"}

    await DatabaseStep().run(world.context())

    expected = [name for name in KNOWN_MIGRATIONS if name > "0002_access_rules"]
    assert world.platform.applied == expected
    assert world.io.secret_prompts == [TOKEN_PROMPT]


async def test_database_skips_what_supabase_already_recorded() -> None:
    world = make_world([True, GOOD_TOKEN], configured_env())
    world.admin.present = {"0001_schema", "0002_access_rules", "0003_people_overview"}
    world.platform.recorded = {"0007_apply_relevance_answers"}

    await DatabaseStep().run(world.context())

    assert "0007_apply_relevance_answers" not in world.platform.applied


async def test_database_falls_back_to_the_sql_editor_when_a_file_fails() -> None:
    world = make_world([True, GOOD_TOKEN], configured_env())
    world.admin.present = {"0001_schema", "0002_access_rules", "0003_people_overview"}
    world.platform.fail_on = "0005_calendar"
    from_failed = [name for name in KNOWN_MIGRATIONS if name >= "0005"]
    hand_applied = {name for name in from_failed if KNOWN_MIGRATIONS[name] is not None}

    def pause_applies(prompt: str) -> None:
        world.admin.present |= hand_applied

    world.io.on_pause = pause_applies

    await DatabaseStep().run(world.context())

    assert world.platform.applied == ["0004_overdue_and_chase"]
    assert any(url.endswith(f"/project/{PROJECT_REF}/sql") for url in world.io.opened)
    assert len(world.io.copied) == len(from_failed)


async def test_database_waits_between_files_so_supabase_versions_never_collide() -> None:
    world = make_world([True, GOOD_TOKEN], configured_env())
    world.admin.present = {"0001_schema"}

    await DatabaseStep().run(world.context())

    sent = len(world.platform.applied)
    assert world.waits == [MIGRATION_PAUSE_SECONDS] * (sent - 1)


async def test_database_sends_a_refused_file_once_more_and_shows_why() -> None:
    world = make_world([True, GOOD_TOKEN], configured_env())
    world.admin.present = {"0001_schema", "0002_access_rules"}
    world.platform.rejections = {"0003_people_overview": 1}

    await DatabaseStep().run(world.context())

    assert "0003_people_overview" in world.platform.applied
    assert MIGRATION_RETRY_WAIT_SECONDS in world.waits
    assert "version already exists" in world.io.text()
    assert world.io.copied == []


async def test_database_refused_twice_goes_by_hand_from_that_file() -> None:
    world = make_world([True, GOOD_TOKEN], configured_env())
    world.admin.present = {"0001_schema", "0002_access_rules"}
    world.platform.rejections = {"0003_people_overview": 2}

    def pause_applies(prompt: str) -> None:
        world.admin.present |= set(KNOWN_MIGRATIONS)

    world.io.on_pause = pause_applies

    await DatabaseStep().run(world.context())

    assert world.platform.applied == []
    assert "Carrying on by hand from that file." in world.io.said


async def test_database_token_that_can_read_but_not_write_goes_by_hand() -> None:
    world = make_world([True, GOOD_TOKEN], configured_env())
    world.admin.present = {"0001_schema", "0002_access_rules"}
    world.platform.apply_forbidden = True
    world.io.on_pause = lambda prompt: world.admin.present.update(KNOWN_MIGRATIONS)

    await DatabaseStep().run(world.context())

    assert world.platform.applied == []
    assert "Supabase did not accept the access token" in world.io.text()
    assert "Carrying on by hand from that file." in world.io.said
    assert any(url.endswith(f"/project/{PROJECT_REF}/sql") for url in world.io.opened)
    assert "The database structure is in place." in world.io.said


async def test_database_token_refused_on_the_second_try_goes_by_hand_too() -> None:
    world = make_world([True, GOOD_TOKEN], configured_env())
    world.admin.present = {"0001_schema", "0002_access_rules"}
    world.platform.rejections = {"0003_people_overview": 1}
    world.platform.apply_forbidden = True
    world.io.on_pause = lambda prompt: world.admin.present.update(KNOWN_MIGRATIONS)

    await DatabaseStep().run(world.context())

    assert "Carrying on by hand from that file." in world.io.said
    assert "The database structure is in place." in world.io.said


async def test_database_by_hand_asks_again_for_a_file_that_was_not_run() -> None:
    world = make_world([False], configured_env())
    world.admin.present = set(KNOWN_MIGRATIONS) - {"0006_meeting_time"}
    returns: list[str] = []

    def second_return_applies(prompt: str) -> None:
        returns.append(prompt)
        if len(returns) == 2:
            world.admin.present.add("0006_meeting_time")

    world.io.on_pause = second_return_applies

    await DatabaseStep().run(world.context())

    assert world.io.text().count("does not show 0006_meeting_time yet") == 1
    assert len(world.io.copied) == 2 + len(_unconfirmed_after("0006"))
    assert "The database structure is in place." in world.io.said


async def test_database_by_hand_takes_a_file_it_cannot_check_on_trust() -> None:
    world = make_world([False], configured_env())
    world.admin.present = set(KNOWN_MIGRATIONS) - {"0010_status_in_process"}
    world.io.on_pause = lambda prompt: world.admin.present.add("0010_status_in_process")

    await DatabaseStep().run(world.context())

    assert len(world.io.copied) == 1 + len(_unconfirmed_after("0010"))
    assert "does not show" not in world.io.text()


def _unconfirmed_after(first: str) -> list[str]:
    """The files after ``first`` that the database cannot confirm, so are re-run."""
    return [name for name in KNOWN_MIGRATIONS if name > first and KNOWN_MIGRATIONS[name] is None]


async def test_database_by_hand_that_is_not_done_is_reported() -> None:
    world = make_world([False], configured_env(), clipboard=False)
    world.admin.present = {"0001_schema"}

    with pytest.raises(ValidationFailedError, match="0002_access_rules"):
        await DatabaseStep().run(world.context())

    assert "Open that file in a text editor" in world.io.text()


async def test_database_needs_the_supabase_step_first() -> None:
    world = make_world()

    with pytest.raises(ValidationFailedError, match="tracker setup supabase"):
        await DatabaseStep().run(world.context())


# --- Login ---------------------------------------------------------------------


async def test_login_creates_the_user_and_records_the_owner() -> None:
    world = make_world([OWNER_EMAIL], configured_env())

    await LoginStep().run(world.context())

    assert world.admin.owners == ["user-1"]
    assert "Sign-ups are switched off" in world.io.text()


async def test_login_is_idempotent_for_an_existing_user() -> None:
    world = make_world([OWNER_EMAIL], configured_env())
    world.admin.users = {OWNER_EMAIL: "existing"}
    world.admin.owners = ["existing"]

    await LoginStep().run(world.context())

    assert world.admin.owners == ["existing"]


async def test_login_without_a_token_guides_switching_off_open_signups() -> None:
    world = make_world([OWNER_EMAIL, False], configured_env())
    world.platform.signups_off = [False, True]

    await LoginStep().run(world.context())

    assert any(url.endswith("/auth/providers") for url in world.io.opened)
    assert "Sign-ups are now switched off." in world.io.said


async def test_login_fails_when_signups_stay_open() -> None:
    world = make_world([OWNER_EMAIL, False], configured_env())
    world.platform.signups_off = [False]

    with pytest.raises(ValidationFailedError, match="sign-ups are still open"):
        await LoginStep().run(world.context())


# --- Categories ----------------------------------------------------------------

#: The presets are listed by name, so number 3 is job_search and 5 is sales_outreach.
_JOB_SEARCH = "3"
_SALES_OUTREACH = "5"


async def test_categories_keeps_some_suggestions_and_adds_one_of_your_own() -> None:
    answers: list[str | bool] = [
        True,  # choose now
        _SALES_OUTREACH,
        False,  # not all of them, I will pick
        True,  # keep Prospect
        False,  # drop Customer
        True,  # keep Partner
        False,  # drop Referrer
        True,  # add one of my own
        "Supplier",
        "",  # accept "Suppliers"
        "Companies that sell to us.",
        "",  # accept the offered colour
        False,  # no more
        True,  # save
    ]
    world = make_world(answers, configured_env())

    await CategoriesStep().run(world.context())

    [choice] = world.choices.saved
    assert choice.preset == "sales_outreach"
    assert [category.key for category in choice.categories] == [
        "prospect",
        "partner",
        "supplier",
        UNKNOWN_CATEGORY_KEY,
    ]
    supplier = choice.categories[2]
    assert supplier.group_label == "Suppliers"
    assert supplier.sort_order > choice.categories[1].sort_order
    text = world.io.text()
    assert "  supplier: Supplier (Suppliers)" in text
    assert "Saved 4 categories, 'Not known' included." in text


async def test_categories_use_all_suggestions_on_one_yes() -> None:
    answers: list[str | bool] = [
        True,  # choose now
        _JOB_SEARCH,
        True,  # use all of them
        False,  # nothing of my own
        True,  # save
    ]
    world = make_world(answers, configured_env())

    await CategoriesStep().run(world.context())

    [choice] = world.choices.saved
    assert [category.key for category in choice.categories] == [
        "startup",
        "vc",
        "network",
        UNKNOWN_CATEGORY_KEY,
    ]
    assert not world.io.answers
    assert "Keep the ones you use:" not in world.io.text()


async def test_categories_asks_again_after_an_empty_or_repeated_name() -> None:
    answers: list[str | bool] = [
        True,
        _JOB_SEARCH,
        False,  # not all of them, I will pick
        True,  # keep Startup
        True,  # keep Investor
        False,  # drop Network
        True,  # add one of my own
        "",  # no name
        "",
        "Hires people.",
        "",
        "investor",  # already kept
        "",
        "Hires people.",
        "",
        "Recruiter",
        "",
        "Hires people.",
        "",
        False,
        True,
    ]
    world = make_world(answers, configured_env())

    await CategoriesStep().run(world.context())

    [choice] = world.choices.saved
    assert [category.key for category in choice.categories] == [
        "startup",
        "vc",
        "recruiter",
        UNKNOWN_CATEGORY_KEY,
    ]
    text = world.io.text()
    assert text.count("That did not work") == 2
    assert 'you already have a category called "investor"' in text


async def test_categories_can_be_skipped_and_saves_nothing() -> None:
    world = make_world([False], configured_env())

    await CategoriesStep().run(world.context())

    assert world.choices.saved == []
    assert "Settings page, or run 'uv run tracker setup categories'" in world.io.text()
    assert not await CategoriesStep().is_done(world.context())


async def test_categories_saves_nothing_when_the_list_is_not_confirmed() -> None:
    world = make_world([True, _JOB_SEARCH, False, True, True, True, False, False], configured_env())

    await CategoriesStep().run(world.context())

    assert world.choices.saved == []
    assert "Nothing saved" in world.io.text()


async def test_categories_are_done_once_a_preset_is_saved() -> None:
    world = make_world([], configured_env())
    world.choices.preset = "fundraising"

    assert await CategoriesStep().is_done(world.context())


async def test_categories_mention_hidden_ones_and_a_profile_file() -> None:
    world = make_world([True, _JOB_SEARCH, False, True, True, True, False, True], configured_env())
    world.choices.archived = ("recruiter",)
    world.choices.profile_file_wins = True

    await CategoriesStep().run(world.context())

    text = world.io.text()
    assert "Hidden, because people still have them: recruiter." in text
    assert "profile/profile.toml file exists" in text


async def test_categories_name_a_hidden_one_that_was_renamed() -> None:
    world = make_world([True, _JOB_SEARCH, True, False, True], configured_env())
    world.choices.archived = ("vc",)
    world.choices.renamed = (
        Category(
            key="vc",
            label="Investor (2)",
            group_label="Investors (2)",
            colour=ColourSlot.CYAN,
            sort_order=20,
        ),
    )

    await CategoriesStep().run(world.context())

    text = world.io.text()
    assert "Renamed while hidden, so no two categories share a name: 'Investor (2)'." in text


# --- Microsoft -----------------------------------------------------------------


async def test_microsoft_signs_in_and_records_the_address() -> None:
    world = make_world([True], configured_env())

    await MicrosoftStep().run(world.context())

    assert "Signed in as you@example.com." in world.io.said
    assert "Your code: CODE-123" in world.io.said
    assert world.env.values["OWNER_EMAIL_ADDRESSES"] == OWNER_EMAIL
    assert world.microsoft.accesses[0].tenant == "consumers"


async def test_microsoft_uses_the_configured_application() -> None:
    env = configured_env() | {"MICROSOFT_CLIENT_ID": "own-app", "MICROSOFT_TENANT": "common"}
    env["OWNER_EMAIL_ADDRESSES"] = OWNER_EMAIL
    world = make_world([], env)

    await MicrosoftStep().run(world.context())

    access = world.microsoft.accesses[0]
    assert (access.client_id, access.tenant) == ("own-app", "common")


async def test_microsoft_asks_for_an_address_when_the_offer_is_declined() -> None:
    world = make_world([False, "other@example.com"], configured_env())

    await MicrosoftStep().run(world.context())

    assert world.env.values["OWNER_EMAIL_ADDRESSES"] == "other@example.com"


async def test_microsoft_refusal_stops_the_step() -> None:
    world = make_world([], configured_env())
    world.microsoft.refuse = True

    with pytest.raises(SourceAuthError):
        await MicrosoftStep().run(world.context())


# --- LinkedIn ------------------------------------------------------------------

_LINKEDIN_PROFILE = "https://www.linkedin.com/in/you/"
_TODAY = date(2026, 9, 29)


def _saved_linkedin() -> dict[str, str]:
    """A ``.env`` where LinkedIn was connected before, with a key about to expire."""
    return {
        "LINKEDIN_ACCESS_TOKEN": "linkedin-old",
        "LINKEDIN_TOKEN_EXPIRES_ON": "2026-10-03",
        "OWNER_LINKEDIN_PROFILE_URL": _LINKEDIN_PROFILE,
    }


async def test_linkedin_can_be_skipped() -> None:
    world = make_world([False])

    await LinkedInStep().run(world.context())

    assert world.env.values == {}
    assert world.linkedin_calls == []
    assert world.io.opened == []


async def test_linkedin_says_what_to_expect_before_asking() -> None:
    world = make_world([False])

    await LinkedInStep().run(world.context())

    text = world.io.text()
    assert "LinkedIn is optional, and the least friendly step" in text
    assert "(the location on your profile, not your citizenship)" in text
    assert "messages reach Threadline a day or two late" in text
    assert LINKEDIN_GUIDE_SECTION in text


async def test_linkedin_first_connection_opens_each_page_once_in_order() -> None:
    answers: list[str | bool] = [
        True,
        True,
        GOOD_LINKEDIN,
        "2027-09-01",
        "https://www.linkedin.com/in/you",
        False,
    ]
    world = make_world(answers)

    await LinkedInStep().run(world.context())

    assert world.io.opened == [LINKEDIN_DEVELOPER_APPS_PAGE, LINKEDIN_TOKEN_GENERATOR_PAGE]
    assert world.env.values == {
        "LINKEDIN_ACCESS_TOKEN": GOOD_LINKEDIN,
        "LINKEDIN_TOKEN_EXPIRES_ON": "2027-09-01",
        "OWNER_LINKEDIN_PROFILE_URL": _LINKEDIN_PROFILE,
    }
    assert GOOD_LINKEDIN not in world.io.text()
    assert not world.io.answers


async def test_linkedin_first_connection_names_each_stage_and_its_guide_part() -> None:
    world = make_world([True, True, GOOD_LINKEDIN, "2027-09-01", _LINKEDIN_PROFILE, False])

    await LinkedInStep().run(world.context())

    said = world.io.said
    stages = [
        said.index("Stage 1 of 3 - create a developer application (guide, part 8a, stage 1)."),
        said.index("[paused] Once your application's own page is open"),
        said.index("Stage 2 of 3 - add the product (guide, part 8a, stage 2)."),
        said.index("Stage 3 of 3 - make the key (guide, part 8a, stage 3)."),
        said.index("LinkedIn accepted the key."),
    ]
    assert stages == sorted(stages)
    text = world.io.text()
    assert "'Member Data Portability (Member) Default Company'" in text
    assert "do not create a new page" in text
    assert "'Member Data Portability API (Member)'" in text
    assert "name starts with r_dma_portability" in text
    assert "'Docs and tools' > 'OAuth Token Tools'" in text


async def test_linkedin_renewal_goes_straight_to_the_key() -> None:
    # The new key and its date, then yes to replacing each saved value.
    world = make_world([GOOD_LINKEDIN, "2027-09-24", True, True, False], _saved_linkedin())

    await LinkedInStep().run(world.context())

    assert world.io.opened == [LINKEDIN_TOKEN_GENERATOR_PAGE]
    assert world.env.values == {
        "LINKEDIN_ACCESS_TOKEN": GOOD_LINKEDIN,
        "LINKEDIN_TOKEN_EXPIRES_ON": "2027-09-24",
        "OWNER_LINKEDIN_PROFILE_URL": _LINKEDIN_PROFILE,
    }
    text = world.io.text()
    assert "A LinkedIn key is already saved, so this is a renewal" in text
    assert "Stage 1 of 3" not in text
    assert "[paused]" not in text
    assert not world.io.answers


async def test_linkedin_renewal_keeps_the_old_key_unless_you_agree() -> None:
    world = make_world([GOOD_LINKEDIN, "2027-09-24", False, False], _saved_linkedin())

    await LinkedInStep().run(world.context())

    assert world.env.values == _saved_linkedin()


async def test_new_linkedin_settings_are_sent_to_github_after_one_yes() -> None:
    world = make_world([True, True, GOOD_LINKEDIN, "2027-09-01", _LINKEDIN_PROFILE, True])

    await LinkedInStep().run(world.context())

    assert world.github.secrets == {
        "LINKEDIN_ACCESS_TOKEN": GOOD_LINKEDIN,
        "OWNER_LINKEDIN_PROFILE_URL": _LINKEDIN_PROFILE,
    }
    assert world.github.variables == {"LINKEDIN_TOKEN_EXPIRES_ON": "2027-09-01"}
    assert "  secret LINKEDIN_ACCESS_TOKEN saved" in world.io.said
    assert GOOD_LINKEDIN not in world.io.text()


async def test_declining_leaves_linkedin_off_github_and_names_the_command() -> None:
    world = make_world([True, True, GOOD_LINKEDIN, "2027-09-01", _LINKEDIN_PROFILE, False])

    await LinkedInStep().run(world.context())

    assert world.github.secrets == {}
    assert "To send them later, run: uv run tracker setup github" in world.io.said


async def test_without_the_github_cli_the_command_is_named_and_nothing_is_asked() -> None:
    world = make_world([True, True, GOOD_LINKEDIN, "2027-09-01", _LINKEDIN_PROFILE])
    world.github.signed_in = False

    await LinkedInStep().run(world.context())

    assert world.github.secrets == {}
    assert "To send them later, run: uv run tracker setup github" in world.io.said


async def test_with_no_copy_on_github_linkedin_asks_nothing_about_sending() -> None:
    world = make_world([True, True, GOOD_LINKEDIN, "2027-09-01", _LINKEDIN_PROFILE])
    world.git.origin = None

    await LinkedInStep().run(world.context())

    assert world.github.secrets == {}
    assert not world.io.answers


async def test_a_refused_send_names_the_command_and_keeps_the_saved_settings() -> None:
    world = make_world([True, True, GOOD_LINKEDIN, "2027-09-01", _LINKEDIN_PROFILE, True])
    world.github.save_refused = True

    await LinkedInStep().run(world.context())

    assert world.env.values["LINKEDIN_ACCESS_TOKEN"] == GOOD_LINKEDIN
    assert "To send them later, run: uv run tracker setup github" in " ".join(world.io.said)


async def test_linkedin_product_not_available_ends_cleanly_and_saves_nothing() -> None:
    world = make_world([True, False])
    wizard = SetupWizard(world.context(), default_steps())

    finished = await wizard.run_one(StepName.LINKEDIN)

    assert finished
    assert world.env.values == {}
    assert world.linkedin_calls == []
    assert world.io.opened == [LINKEDIN_DEVELOPER_APPS_PAGE]
    assert world.io.said[-1] == (
        "Skipped: LinkedIn offers this only to profiles located in the EEA or "
        "Switzerland, so Threadline carries on without LinkedIn."
    )
    assert "Stopped" not in world.io.text()


async def test_linkedin_stores_a_date_typed_with_a_month_name_as_iso() -> None:
    answers: list[str | bool] = [
        True,
        True,
        GOOD_LINKEDIN,
        "24 Sep 2027",
        _LINKEDIN_PROFILE,
        False,
    ]
    world = make_world(answers)

    await LinkedInStep().run(world.context())

    assert world.env.values["LINKEDIN_TOKEN_EXPIRES_ON"] == "2027-09-24"


async def test_linkedin_asks_again_after_a_date_with_slashes() -> None:
    answers: list[str | bool] = [
        True,
        True,
        GOOD_LINKEDIN,
        "03/04/2027",
        "Sep 24, 2027",
        _LINKEDIN_PROFILE,
        False,
    ]
    world = make_world(answers)

    await LinkedInStep().run(world.context())

    assert world.env.values["LINKEDIN_TOKEN_EXPIRES_ON"] == "2027-09-24"
    assert "write the date as YYYY-MM-DD or with the month's name" in world.io.text()


async def test_linkedin_refuses_a_past_expiry_date() -> None:
    world = make_world([True, True, GOOD_LINKEDIN, "2020-01-01", "1 Jan 2020", "31/12/2027"])

    with pytest.raises(ValidationFailedError, match="YYYY-MM-DD"):
        await LinkedInStep().run(world.context())

    assert world.env.values == {}
    assert "that date has already passed" in world.io.text()


async def test_linkedin_asks_again_after_a_refused_key() -> None:
    answers: list[str | bool] = [
        True,
        True,
        "bad",
        GOOD_LINKEDIN,
        "2027-09-01",
        _LINKEDIN_PROFILE,
        False,
    ]
    world = make_world(answers)

    await LinkedInStep().run(world.context())

    assert world.linkedin_calls == ["bad", GOOD_LINKEDIN]
    assert world.env.values["LINKEDIN_ACCESS_TOKEN"] == GOOD_LINKEDIN
    assert "LinkedIn did not accept the key" in world.io.text()
    assert "bad" not in world.env.values.values()


async def test_linkedin_refused_key_is_never_saved() -> None:
    world = make_world([True, True, "bad", "bad", "bad"])

    with pytest.raises(SourceAuthError):
        await LinkedInStep().run(world.context())

    assert world.env.values == {}


@pytest.mark.parametrize(
    "typed",
    [
        "2027-09-24",
        "24 Sep 2027",
        "24 September 2027",
        "Sep 24, 2027",
        "September 24 2027",
        "  24 sept. 2027 ",
        "24 SEP 2027",
    ],
)
async def test_an_unambiguous_expiry_date_is_accepted(typed: str) -> None:
    assert values.future_date(typed, _TODAY) == date(2027, 9, 24)


@pytest.mark.parametrize(
    "typed",
    [
        "03/04/2027",
        "24/09/2027",
        "24-09-2027",
        "24.09.2027",
        "24 Sep 27",
        "Sep 2027",
        "31 Feb 2027",
        "24 Septober 2027",
        "next year",
        "",
    ],
)
async def test_an_ambiguous_or_malformed_expiry_date_is_refused(typed: str) -> None:
    with pytest.raises(ValidationFailedError, match="YYYY-MM-DD or with the month's name"):
        values.future_date(typed, _TODAY)


@pytest.mark.parametrize("typed", ["2026-09-28", "28 Sep 2026", "September 28, 2026"])
async def test_an_expiry_date_in_the_past_is_refused(typed: str) -> None:
    with pytest.raises(ValidationFailedError, match="already passed"):
        values.future_date(typed, _TODAY)


async def test_an_expiry_date_of_today_is_accepted() -> None:
    assert values.future_date("29 Sep 2026", _TODAY) == _TODAY


# --- Dashboard -----------------------------------------------------------------


async def test_dashboard_not_published_as_one_step_names_that_step() -> None:
    world = make_world([False, False], configured_env())
    wizard = SetupWizard(world.context(), default_steps())

    finished = await wizard.run_one(StepName.DASHBOARD)

    assert not finished
    assert world.io.said[-1] == (
        "Fix that, then run 'uv run tracker setup dashboard' - finished steps are kept."
    )


# --- Cloud ---------------------------------------------------------------------


async def test_cloud_lists_names_and_hosts_but_never_values() -> None:
    env = configured_env() | {"LINKEDIN_ACCESS_TOKEN": GOOD_LINKEDIN, "APP_ENV": "development"}
    world = make_world([True, True, False], env)

    await CloudStep().run(world.context())

    text = world.io.text()
    assert "  SUPABASE_ANON_KEY" in world.io.said
    assert "  APP_ENV" not in world.io.said
    assert "  api.linkedin.com" in world.io.said
    assert f"  {PROJECT_REF}.supabase.co" in world.io.said
    assert GOOD_SECRET not in text
    assert GOOD_SECRET in world.io.copied
    assert world.io.copied[-1] == ""


async def test_cloud_without_a_clipboard_says_so() -> None:
    world = make_world([True, True, False], configured_env(), clipboard=False)

    await CloudStep().run(world.context())

    assert "No clipboard is available" in world.io.text()
    assert "  api.linkedin.com" not in world.io.said


# --- The wizard ----------------------------------------------------------------


async def test_a_second_run_skips_finished_steps_and_stops_cleanly() -> None:
    env = configured_env() | {"TOKEN_ENCRYPTION_KEY": _fernet_key()}
    # The login, skip the categories, keep the offered time zone, leave the
    # workflow's new zone unpushed, no name, then choose Outlook as the mailbox.
    world = make_world([OWNER_EMAIL, False, "", False, "", "outlook"], env)
    world.microsoft.refuse = True
    wizard = SetupWizard(world.context(), default_steps())

    finished = await wizard.run_core()

    assert not finished
    text = world.io.text()
    assert "Already done. To redo it: uv run tracker setup supabase" in text
    assert "Stopped: Microsoft sign-in was not completed in time" in text
    assert "run 'uv run tracker setup' again: finished steps are kept" in text
    assert "Step 6 of 11: Your time zone" in text


def _finished_up_to_the_dashboard(answers: list[str | bool]) -> World:
    """A world where every core step before the dashboard is done, Outlook as the mailbox."""
    env = configured_env() | {
        "TOKEN_ENCRYPTION_KEY": _fernet_key(),
        "OWNER_TIME_ZONE": "UTC",
        "MAIL_SOURCES": "outlook",
    }
    world = make_world(answers, env)
    world.admin.owners = ["user-1"]
    world.choices.preset = "job_search"
    world.microsoft.signed_in = True
    return world


async def test_a_full_run_stops_at_a_dashboard_that_is_not_published_yet() -> None:
    # Not on Netlify, and not anywhere else either.
    world = _finished_up_to_the_dashboard([False, False])
    wizard = SetupWizard(world.context(), default_steps())

    finished = await wizard.run_core()

    assert not finished
    text = world.io.text()
    assert "Step 9 of 11: Your dashboard" in text
    assert (
        "Stopped: the dashboard is not published yet - publish it first (part 5 of the guide)."
        in text
    )
    assert world.io.said[-1] == (
        "Fix that, then run 'uv run tracker setup' again: finished steps are kept "
        "and it carries on from here."
    )
    assert "Step 10 of 11" not in text
    assert "DASHBOARD_BASE_URL" not in world.env.values


async def test_the_next_full_run_skips_to_the_dashboard_and_carries_on() -> None:
    # Not on Netlify but elsewhere, its address, Supabase's two values typed by
    # hand, then Enter keeps the daily time already set.
    world = _finished_up_to_the_dashboard([False, True, "https://you.host.example", False, ""])
    world.statuses["https://you.host.example"] = 200
    wizard = SetupWizard(world.context(), default_steps())

    await wizard.run_core()

    text = world.io.text()
    for step in ("supabase", "login", "categories", "timezone", "mailbox", "microsoft"):
        assert f"Already done. To redo it: uv run tracker setup {step}" in text
    assert "Saved DASHBOARD_BASE_URL in .env." in text
    assert "Step 10 of 11: The daily time" in text
    assert "The daily run already starts at 07:00 (UTC). Nothing to change." in text


class _RefusingCloudStep:
    """An extra step that always stops, to see what the wizard says after it."""

    name = StepName.CLOUD
    title = "A step that stops"

    async def is_done(self, ctx: SetupContext) -> bool:
        return False

    async def run(self, ctx: SetupContext) -> None:
        message = "made-up problem"
        raise ValidationFailedError(message)


async def test_an_extra_that_stops_names_the_extras_command() -> None:
    world = make_world([], configured_env())
    wizard = SetupWizard(world.context(), (_RefusingCloudStep(),))

    finished = await wizard.run_extras()

    assert not finished
    assert world.io.said[-1] == (
        "Fix that, then run 'uv run tracker setup extras' again: finished steps are kept "
        "and it carries on from here."
    )


async def test_categories_come_right_after_the_login() -> None:
    names = [step.name for step in default_steps()]

    assert names.index(StepName.CATEGORIES) == names.index(StepName.LOGIN) + 1


async def test_the_time_zone_comes_right_after_the_categories() -> None:
    names = [step.name for step in default_steps()]

    assert names.index(StepName.TIME_ZONE) == names.index(StepName.CATEGORIES) + 1


# --- Time zone -----------------------------------------------------------------


async def test_the_computers_time_zone_is_offered_and_saved() -> None:
    world = make_world(["", False, ""], configured_env())

    await TimeZoneStep().run(world.context())

    assert world.env.values["OWNER_TIME_ZONE"] == "Europe/Paris"
    assert "OWNER_DISPLAY_NAME" not in world.env.values
    assert await TimeZoneStep().is_done(world.context())


async def test_a_typed_time_zone_is_checked_and_the_name_is_saved() -> None:
    world = make_world(["Paris", "America/New_York", False, "  Sam   Rivera "], configured_env())

    await TimeZoneStep().run(world.context())

    assert world.env.values["OWNER_TIME_ZONE"] == "America/New_York"
    assert world.env.values["OWNER_DISPLAY_NAME"] == "Sam Rivera"
    assert "time-zone name" in world.io.text()


async def test_a_typed_time_zone_is_saved_as_the_database_spells_it() -> None:
    world = make_world(["europe/rome", False, ""], configured_env())

    await TimeZoneStep().run(world.context())

    assert world.env.values["OWNER_TIME_ZONE"] == "Europe/Rome"


async def test_a_saved_time_zone_in_the_wrong_case_is_put_right() -> None:
    world = make_world(["", False, ""], configured_env() | {"OWNER_TIME_ZONE": "asia/tokyo"})

    await TimeZoneStep().run(world.context())

    assert world.env.values["OWNER_TIME_ZONE"] == "Asia/Tokyo"


async def test_a_zone_the_computer_cannot_name_is_asked_with_no_default() -> None:
    world = make_world(["Asia/Tokyo", False, ""], configured_env())
    world.local_zone = None

    await TimeZoneStep().run(world.context())

    assert world.io.defaults["Your time zone"] is None
    assert "I could not tell your time zone." in world.io.text()
    assert "Europe/Paris or America/New_York" in world.io.text()
    assert world.env.values["OWNER_TIME_ZONE"] == "Asia/Tokyo"


async def test_an_empty_or_wrong_answer_is_asked_again_when_there_is_no_default() -> None:
    world = make_world(["", "Paris", "america/new_york", False, ""], configured_env())
    world.local_zone = None

    await TimeZoneStep().run(world.context())

    assert world.env.values["OWNER_TIME_ZONE"] == "America/New_York"
    assert world.io.text().count("that is not a time-zone name") == 2


async def test_a_known_zone_is_still_offered_as_the_default() -> None:
    world = make_world(["", False, ""], configured_env())

    await TimeZoneStep().run(world.context())

    assert world.io.defaults["Your time zone"] == "Europe/Paris"
    assert "I could not tell your time zone." not in world.io.text()


async def test_a_saved_time_zone_is_offered_before_the_computers() -> None:
    world = make_world(["", False, ""], configured_env() | {"OWNER_TIME_ZONE": "Asia/Tokyo"})

    await TimeZoneStep().run(world.context())

    assert world.env.values["OWNER_TIME_ZONE"] == "Asia/Tokyo"
    assert not any(line.startswith("Saved OWNER_TIME_ZONE") for line in world.io.said)


async def test_choosing_the_cloud_route_offers_to_switch_the_github_run_off() -> None:
    world = make_world([True, False, True], configured_env())

    await CloudStep().run(world.context())

    assert world.github.disabled == ["you/threadline"]
    assert "Switched off." in " ".join(world.io.said)


async def test_a_no_leaves_the_github_run_on_and_says_how_to_stop_it_by_hand() -> None:
    world = make_world([True, False, False], configured_env())

    await CloudStep().run(world.context())

    text = world.io.text()
    assert world.github.disabled == []
    assert "choose 'Disable workflow'" in text
    assert "github.com/you/threadline/actions/workflows/threadline-run.yml" in text


async def test_pressing_enter_leaves_the_github_run_on_until_the_routine_has_run() -> None:
    world = make_world([True, False, ""], configured_env())

    await CloudStep().run(world.context())

    text = world.io.text()
    assert world.github.disabled == []
    assert (
        "Once your Claude routine has run once and the e-mail arrived, switch the GitHub daily "
        "run off so both don't run: 'gh workflow disable threadline-run.yml' (or answer yes "
        "here if the routine already runs)."
    ) in text
    assert "Switched off." not in text


async def test_without_the_github_cli_the_github_run_is_left_to_the_owner() -> None:
    world = make_world([True, False], configured_env())
    world.github.signed_in = False

    await CloudStep().run(world.context())

    assert world.github.disabled == []
    assert "choose 'Disable workflow'" in world.io.text()


async def test_a_github_run_that_will_not_switch_off_is_named_with_its_page() -> None:
    world = make_world([True, False, True], configured_env())
    world.github.disable_refused = True

    await CloudStep().run(world.context())

    assert "GitHub would not switch the daily run off" in world.io.text()


async def test_with_no_copy_on_github_the_cloud_route_says_nothing_about_stopping_it() -> None:
    world = make_world([True, False], configured_env())
    world.git.origin = None

    await CloudStep().run(world.context())

    assert "Disable workflow" not in world.io.text()
    assert world.github.disabled == []


async def test_the_cloud_routine_is_the_alternative_and_skipped_by_default() -> None:
    world = make_world([""], configured_env())

    await CloudStep().run(world.context())

    assert "Skipped. To set it up later: uv run tracker setup cloud" in world.io.said
    assert world.io.copied == []


async def test_one_step_runs_even_when_finished() -> None:
    world = make_world([False], configured_env())
    wizard = SetupWizard(world.context(), default_steps())

    assert await wizard.run_one(StepName.CLOUD)


async def test_the_core_and_the_extras_split_every_step_between_them() -> None:
    core = [step.name for step in core_steps()]
    extras = [step.name for step in extra_steps()]

    assert extras == [StepName.LINKEDIN, StepName.REFRESH, StepName.CLOUD]
    assert core == [
        StepName.SUPABASE, StepName.ENCRYPTION, StepName.DATABASE, StepName.LOGIN,
        StepName.CATEGORIES, StepName.TIME_ZONE, StepName.MAILBOX, StepName.MICROSOFT,
        StepName.DASHBOARD, StepName.SCHEDULE, StepName.GITHUB,
    ]  # fmt: skip
    assert sorted(core + extras) == sorted(StepName)
    assert all(name.group is StepGroup.CORE for name in core)
    assert all(name.group is StepGroup.EXTRAS for name in extras)


async def test_the_extras_run_alone_in_order_and_each_can_be_skipped() -> None:
    # No LinkedIn; Refresh now has no dashboard yet so asks nothing; no cloud routine.
    world = make_world([False, False], configured_env())

    finished = await SetupWizard(world.context(), default_steps()).run_extras()

    assert finished
    steps = [line for line in world.io.said if line.startswith("Step ")]
    assert steps == [
        "Step 1 of 3: LinkedIn (optional)",
        "Step 2 of 3: The Refresh now button",
        "Step 3 of 3: The alternative: a Claude cloud routine",
    ]
    text = world.io.text()
    assert "Skipped. Run 'uv run tracker setup linkedin' whenever you want it." in text
    assert "Skipped. To set it up later: uv run tracker setup cloud" in text
    assert "Set-up done." not in text


def _fernet_key() -> str:
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode()
