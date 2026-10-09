"""The LinkedIn set-up step, without a terminal or a network: one click, and by hand."""

from __future__ import annotations

from datetime import date

import pytest

from tests.setup_world import (
    GOOD_CLIENT_ID,
    GOOD_CLIENT_SECRET,
    GOOD_LINKEDIN,
    World,
    configured_env,
    make_world,
)
from tracker.domain.linkedin_sign_in import SignInProblem
from tracker.services.setup import values
from tracker.services.setup.models import StepName
from tracker.services.setup.step_linkedin import LinkedInStep
from tracker.services.setup.wizard import SetupWizard, default_steps
from tracker.shared.constants.linkedin_sign_in import REDIRECT_URL
from tracker.shared.constants.setup import (
    LINKEDIN_GUIDE_SECTION,
    LINKEDIN_NEW_APP_PAGE,
    LINKEDIN_TOKEN_GENERATOR_PAGE,
)
from tracker.shared.errors import (
    LinkedInSignInError,
    SourceAuthError,
    SourceUnavailableError,
    ValidationFailedError,
)

pytestmark = pytest.mark.asyncio

_PROFILE = "https://www.linkedin.com/in/you/"
_TODAY = date(2026, 9, 29)
_CONSENT_PAGE = f"https://www.linkedin.com/oauth/v2/authorization?client_id={GOOD_CLIENT_ID}"
_TRY_LATER = "Skipped. Run 'uv run tracker setup linkedin' to try again."

#: Yes to connecting, yes to the product: the answers before stage 3.
_FIRST_TWO_STAGES: list[str | bool] = [True, True]
#: The two values from the Auth tab.
_APP: list[str | bool] = [GOOD_CLIENT_ID, GOOD_CLIENT_SECRET]


def _first_time(*after_app: str | bool) -> World:
    """A world where LinkedIn is connected for the first time, the app typed correctly."""
    return make_world([*_FIRST_TWO_STAGES, *_APP, *after_app], configured_env())


def _saved_key(*, with_app: bool) -> dict[str, str]:
    """A ``.env`` where LinkedIn was connected before, with a key about to expire."""
    env = configured_env() | {
        "LINKEDIN_ACCESS_TOKEN": "linkedin-old",
        "LINKEDIN_TOKEN_EXPIRES_ON": "2026-10-03",
        "OWNER_LINKEDIN_PROFILE_URL": _PROFILE,
    }
    return env | {"LINKEDIN_CLIENT_ID": GOOD_CLIENT_ID} if with_app else env


def _linkedin_values(world: World) -> dict[str, str]:
    """The LinkedIn settings the step wrote."""
    return {name: value for name, value in world.env.values.items() if "LINKEDIN" in name}


def _refusal(problem: SignInProblem) -> LinkedInSignInError:
    return LinkedInSignInError(f"made-up refusal: {problem}", problem)


# --- Before anything is made ---------------------------------------------------


async def test_linkedin_can_be_skipped() -> None:
    world = make_world([False])

    await LinkedInStep().run(world.context())

    assert world.env.values == {}
    assert world.linkedin.sign_ins == []
    assert world.io.opened == []


async def test_linkedin_says_what_to_expect_before_asking() -> None:
    world = make_world([False])

    await LinkedInStep().run(world.context())

    text = world.io.text()
    assert "LinkedIn is optional" in text
    assert "(the location on your profile, not your citizenship)" in text
    assert "messages reach Threadline a day or two late" in text
    assert "After that, a new key takes one command and one click." in text
    assert LINKEDIN_GUIDE_SECTION in text


async def test_linkedin_product_not_available_ends_cleanly_and_saves_nothing() -> None:
    world = make_world([True, False])
    wizard = SetupWizard(world.context(), default_steps())

    finished = await wizard.run_one(StepName.LINKEDIN)

    assert finished
    assert world.env.values == {}
    assert world.linkedin.sign_ins == []
    assert world.io.opened == [LINKEDIN_NEW_APP_PAGE]
    assert world.io.said[-1] == (
        "Skipped: LinkedIn offers this only to profiles located in the EEA or "
        "Switzerland, so Threadline carries on without LinkedIn."
    )


# --- The first connection --------------------------------------------------------


async def test_first_connection_makes_the_key_with_one_allow_and_saves_everything() -> None:
    world = _first_time(_PROFILE, False)

    await LinkedInStep().run(world.context())

    assert world.io.opened == [LINKEDIN_NEW_APP_PAGE, _CONSENT_PAGE]
    assert world.io.copied == [REDIRECT_URL]
    assert _linkedin_values(world) == {
        "LINKEDIN_CLIENT_ID": GOOD_CLIENT_ID,
        "LINKEDIN_ACCESS_TOKEN": GOOD_LINKEDIN,
        "LINKEDIN_TOKEN_EXPIRES_ON": "2027-09-24",
        "OWNER_LINKEDIN_PROFILE_URL": _PROFILE,
    }
    assert world.linkedin.saved_secret == GOOD_CLIENT_SECRET
    assert world.linkedin_calls == [GOOD_LINKEDIN]
    assert "LinkedIn made a new key. It works until 24 Sep 2027." in world.io.said
    assert not world.io.answers


async def test_first_connection_never_shows_or_writes_the_secret_or_the_key() -> None:
    world = _first_time(_PROFILE, False)

    await LinkedInStep().run(world.context())

    text = world.io.text()
    assert GOOD_CLIENT_SECRET not in text
    assert GOOD_LINKEDIN not in text
    assert GOOD_CLIENT_SECRET not in world.env.values.values()
    assert world.io.secret_prompts == ["Client Secret (it stays hidden)"]


async def test_first_connection_names_each_stage_in_order_with_exact_clicks() -> None:
    world = _first_time(_PROFILE, False)

    await LinkedInStep().run(world.context())

    said = world.io.said
    order = [
        said.index("Stage 1 of 3 - create a developer application (guide, part 8a, stage 1)."),
        said.index("[paused] Once your application's own page is open"),
        said.index("Stage 2 of 3 - add the product (guide, part 8a, stage 2)."),
        said.index(
            "Stage 3 of 3 - connect the application to Threadline (guide, part 8a, stage 3)."
        ),
        said.index(f"  {REDIRECT_URL}"),
        said.index("[paused] Once the address is saved"),
        said.index("LinkedIn accepted the key."),
    ]
    assert order == sorted(order)
    text = world.io.text()
    assert "'Member Data Portability (Member) Default Company'" in text
    assert "do not create a new page" in text
    assert "'Member Data Portability API (Member)'" in text
    assert "'Authorized redirect URLs for your app'" in text
    assert "'Primary Client Secret'" in text
    assert "click 'Allow'" in text
    assert "(It is already on your clipboard.)" in text


async def test_without_a_clipboard_the_address_is_shown_to_copy_by_hand() -> None:
    world = make_world(
        [*_FIRST_TWO_STAGES, *_APP, _PROFILE, False], configured_env(), clipboard=False
    )

    await LinkedInStep().run(world.context())

    assert f"  {REDIRECT_URL}" in world.io.said
    assert "(It is already on your clipboard.)" not in world.io.text()


async def test_a_client_id_that_is_not_one_is_asked_again() -> None:
    world = make_world(
        [*_FIRST_TWO_STAGES, "https://linkedin.com/x", *_APP, _PROFILE, False], configured_env()
    )

    await LinkedInStep().run(world.context())

    assert "the Client ID is a short run of letters and numbers" in world.io.text()
    assert world.env.values["LINKEDIN_CLIENT_ID"] == GOOD_CLIENT_ID


async def test_a_slow_allow_asks_whether_to_keep_waiting() -> None:
    world = _first_time(True, _PROFILE, False)
    world.linkedin.slow_answers = 1

    await LinkedInStep().run(world.context())

    assert world.env.values["LINKEDIN_ACCESS_TOKEN"] == GOOD_LINKEDIN
    assert len(world.linkedin.sign_ins) == 1


async def test_a_new_key_linkedin_will_not_read_is_never_saved() -> None:
    world = _first_time()
    world.linkedin.key = "linkedin-unreadable"

    with pytest.raises(SourceAuthError, match="did not accept the key"):
        await LinkedInStep().run(world.context())

    assert "LINKEDIN_ACCESS_TOKEN" not in world.env.values
    assert world.linkedin.saved_secret is None


# --- When the one-click way stumbles ------------------------------------------------


async def test_a_cancelled_allow_can_be_tried_again() -> None:
    world = _first_time(True, _PROFILE, False)
    world.linkedin.errors = [_refusal(SignInProblem.CANCELLED)]

    await LinkedInStep().run(world.context())

    assert "  made-up refusal: cancelled." in world.io.said
    assert len(world.linkedin.sign_ins) == 2
    assert world.env.values["LINKEDIN_ACCESS_TOKEN"] == GOOD_LINKEDIN


async def test_a_refused_secret_is_asked_again_and_enter_keeps_the_client_id() -> None:
    answers: list[str | bool] = [
        *_FIRST_TWO_STAGES,
        GOOD_CLIENT_ID,
        "wrong-secret",
        True,
        "",
        GOOD_CLIENT_SECRET,
        _PROFILE,
        False,
    ]
    world = make_world(answers, configured_env())

    await LinkedInStep().run(world.context())

    assert "LinkedIn did not accept the Client ID or the Client Secret" in world.io.text()
    assert world.io.defaults["Client ID"] == GOOD_CLIENT_ID
    assert [app.client_id for app in world.linkedin.sign_ins] == [GOOD_CLIENT_ID] * 2
    assert world.linkedin.saved_secret == GOOD_CLIENT_SECRET


async def test_enter_on_the_second_secret_keeps_the_one_typed_first() -> None:
    world = _first_time(True, "", "", _PROFILE, False)
    world.linkedin.errors = [_refusal(SignInProblem.NO_ANSWER)]

    await LinkedInStep().run(world.context())

    assert world.linkedin.saved_secret == GOOD_CLIENT_SECRET
    assert world.io.secret_prompts[-1] == (
        "Client Secret (it stays hidden; Enter keeps the one you typed)"
    )


async def test_a_problem_that_is_not_the_app_does_not_ask_for_it_again() -> None:
    world = _first_time(True, _PROFILE, False)
    world.linkedin.errors = [_refusal(SignInProblem.PRODUCT_MISSING)]

    await LinkedInStep().run(world.context())

    assert world.io.secret_prompts == ["Client Secret (it stays hidden)"]
    assert len(world.linkedin.sign_ins) == 2


async def test_linkedin_out_of_reach_is_said_plainly_and_can_be_tried_again() -> None:
    world = _first_time(True, _PROFILE, False)
    world.linkedin.errors = [SourceUnavailableError("LinkedIn could not be reached")]

    await LinkedInStep().run(world.context())

    assert "  LinkedIn could not be reached." in world.io.said
    assert world.io.secret_prompts == ["Client Secret (it stays hidden)"]
    assert world.env.values["LINKEDIN_ACCESS_TOKEN"] == GOOD_LINKEDIN


async def test_giving_up_offers_the_key_by_hand_with_the_expiry_read_from_linkedin() -> None:
    world = _first_time(False, True, GOOD_LINKEDIN, _PROFILE, False)
    world.linkedin.errors = [_refusal(SignInProblem.PRODUCT_MISSING)]

    await LinkedInStep().run(world.context())

    assert world.io.opened[-1] == LINKEDIN_TOKEN_GENERATOR_PAGE
    assert world.linkedin.introspections == [GOOD_LINKEDIN]
    assert "LinkedIn says this key works until 24 Sep 2027." in world.io.said
    assert "Token Inspector" not in world.io.text()
    assert world.env.values["LINKEDIN_TOKEN_EXPIRES_ON"] == "2027-09-24"
    assert "LINKEDIN_CLIENT_ID" not in world.env.values
    assert world.linkedin.saved_secret is None


async def test_three_failed_tries_end_with_the_offer_of_the_key_by_hand() -> None:
    world = _first_time(True, True, False)
    world.linkedin.errors = [_refusal(SignInProblem.OTHER) for _ in range(3)]

    await LinkedInStep().run(world.context())

    assert len(world.linkedin.sign_ins) == 3
    assert world.io.said[-1] == _TRY_LATER
    assert _linkedin_values(world) == {}


async def test_the_expiry_is_read_from_linkedin_when_the_exchange_does_not_say() -> None:
    world = _first_time(_PROFILE, False)
    world.linkedin.tells_expiry = False

    await LinkedInStep().run(world.context())

    assert world.linkedin.introspections == [GOOD_LINKEDIN]
    assert world.env.values["LINKEDIN_TOKEN_EXPIRES_ON"] == "2027-09-24"


async def test_the_expiry_is_asked_only_when_linkedin_never_says() -> None:
    world = _first_time("24 Sep 2027", _PROFILE, False)
    world.linkedin.tells_expiry = False
    world.linkedin.introspected = None

    await LinkedInStep().run(world.context())

    assert "LinkedIn made a new key but did not say when it expires." in world.io.said
    assert world.env.values["LINKEDIN_TOKEN_EXPIRES_ON"] == "2027-09-24"


async def test_the_new_key_is_saved_when_linkedin_cannot_say_its_expiry() -> None:
    world = _first_time("24 Sep 2027", _PROFILE, False)
    world.linkedin.tells_expiry = False
    world.linkedin.introspection_fails = True

    await LinkedInStep().run(world.context())

    assert "LinkedIn made a new key but did not say when it expires." in world.io.said
    assert world.env.values["LINKEDIN_ACCESS_TOKEN"] == GOOD_LINKEDIN
    assert world.env.values["LINKEDIN_TOKEN_EXPIRES_ON"] == "2027-09-24"
    assert world.linkedin.saved_secret == GOOD_CLIENT_SECRET


async def test_the_new_key_is_saved_before_its_expiry_is_asked() -> None:
    world = _first_time("soon", "later", "one day")
    world.linkedin.tells_expiry = False
    world.linkedin.introspected = None

    with pytest.raises(ValidationFailedError):
        await LinkedInStep().run(world.context())

    assert world.env.values["LINKEDIN_ACCESS_TOKEN"] == GOOD_LINKEDIN


async def test_a_client_secret_the_database_cannot_keep_leaves_the_key_saved() -> None:
    world = _first_time(_PROFILE, False)
    world.linkedin.secret_save_fails = True

    await LinkedInStep().run(world.context())

    assert _linkedin_values(world) == {
        "LINKEDIN_CLIENT_ID": GOOD_CLIENT_ID,
        "LINKEDIN_ACCESS_TOKEN": GOOD_LINKEDIN,
        "LINKEDIN_TOKEN_EXPIRES_ON": "2027-09-24",
        "OWNER_LINKEDIN_PROFILE_URL": _PROFILE,
    }
    assert world.linkedin.saved_secret is None
    text = world.io.text()
    assert "so one-click renewal is not set up" in text
    assert "run 'uv run tracker setup linkedin'" in text
    assert "Saved the Client Secret" not in text
    assert not world.io.answers


# --- Renewal ---------------------------------------------------------------------


async def test_renewal_with_a_saved_application_is_one_click() -> None:
    world = make_world([False], _saved_key(with_app=True))
    world.linkedin.saved_secret = GOOD_CLIENT_SECRET

    await LinkedInStep().run(world.context())

    assert world.io.opened == [_CONSENT_PAGE]
    assert world.env.values["LINKEDIN_ACCESS_TOKEN"] == GOOD_LINKEDIN
    assert world.env.values["LINKEDIN_TOKEN_EXPIRES_ON"] == "2027-09-24"
    text = world.io.text()
    assert "A LinkedIn key is already saved, so this makes a new one" in text
    assert "Stage 1 of 3" not in text
    assert "[paused]" not in text
    assert not world.io.answers


async def test_renewal_sends_only_the_new_key_and_date_to_github() -> None:
    world = make_world([True], _saved_key(with_app=True))
    world.linkedin.saved_secret = GOOD_CLIENT_SECRET

    await LinkedInStep().run(world.context())

    assert world.github.secrets == {"LINKEDIN_ACCESS_TOKEN": GOOD_LINKEDIN}
    assert world.github.variables == {"LINKEDIN_TOKEN_EXPIRES_ON": "2027-09-24"}


async def test_renewal_without_a_saved_application_offers_one_click_once() -> None:
    world = make_world([True, *_APP, False], _saved_key(with_app=False))

    await LinkedInStep().run(world.context())

    assert "Connect the application to Threadline (guide, part 8a, stage 3)." in world.io.said
    assert world.io.opened == [_CONSENT_PAGE]
    assert world.env.values["LINKEDIN_CLIENT_ID"] == GOOD_CLIENT_ID
    assert world.linkedin.saved_secret == GOOD_CLIENT_SECRET


async def test_renewal_by_hand_stays_available_as_before() -> None:
    world = make_world([False, GOOD_LINKEDIN, "2027-09-24", False], _saved_key(with_app=False))

    await LinkedInStep().run(world.context())

    assert world.io.opened == [LINKEDIN_TOKEN_GENERATOR_PAGE]
    assert "'Docs and tools' > 'OAuth Token Tools'" in world.io.text()
    assert world.env.values["LINKEDIN_ACCESS_TOKEN"] == GOOD_LINKEDIN
    assert world.env.values["LINKEDIN_TOKEN_EXPIRES_ON"] == "2027-09-24"
    assert world.linkedin.sign_ins == []


async def test_a_client_id_without_a_saved_secret_counts_as_no_application() -> None:
    world = make_world([False, GOOD_LINKEDIN, "2027-09-24", False], _saved_key(with_app=True))

    await LinkedInStep().run(world.context())

    assert world.linkedin.sign_ins == []
    assert world.env.values["LINKEDIN_ACCESS_TOKEN"] == GOOD_LINKEDIN


# --- Sending to GitHub ------------------------------------------------------------


async def test_new_linkedin_settings_are_sent_to_github_after_one_yes() -> None:
    world = _first_time(_PROFILE, True)

    await LinkedInStep().run(world.context())

    assert world.github.secrets == {
        "LINKEDIN_ACCESS_TOKEN": GOOD_LINKEDIN,
        "OWNER_LINKEDIN_PROFILE_URL": _PROFILE,
    }
    assert world.github.variables == {"LINKEDIN_TOKEN_EXPIRES_ON": "2027-09-24"}
    assert "  secret LINKEDIN_ACCESS_TOKEN saved" in world.io.said
    assert GOOD_LINKEDIN not in world.io.text()


async def test_declining_leaves_linkedin_off_github_and_names_the_command() -> None:
    world = _first_time(_PROFILE, False)

    await LinkedInStep().run(world.context())

    assert world.github.secrets == {}
    assert "To send them later, run: uv run tracker setup github" in world.io.said


async def test_without_the_github_cli_the_command_is_named_and_nothing_is_asked() -> None:
    world = _first_time(_PROFILE)
    world.github.signed_in = False

    await LinkedInStep().run(world.context())

    assert world.github.secrets == {}
    assert "To send them later, run: uv run tracker setup github" in world.io.said


async def test_a_refused_send_names_the_command_and_keeps_the_saved_settings() -> None:
    world = _first_time(_PROFILE, True)
    world.github.save_refused = True

    await LinkedInStep().run(world.context())

    assert world.env.values["LINKEDIN_ACCESS_TOKEN"] == GOOD_LINKEDIN
    assert "To send them later, run: uv run tracker setup github" in " ".join(world.io.said)


# --- The key by hand ---------------------------------------------------------------


def _by_hand(*answers: str | bool) -> World:
    """A renewal without a saved application, where the person keeps the by-hand way."""
    return make_world([False, *answers], _saved_key(with_app=False))


async def test_a_pasted_key_is_asked_again_after_a_refusal() -> None:
    world = _by_hand("bad", GOOD_LINKEDIN, "2027-09-01", False)

    await LinkedInStep().run(world.context())

    assert world.linkedin_calls == ["bad", GOOD_LINKEDIN]
    assert world.env.values["LINKEDIN_ACCESS_TOKEN"] == GOOD_LINKEDIN
    assert "LinkedIn did not accept the key" in world.io.text()


async def test_a_refused_pasted_key_is_never_saved() -> None:
    world = _by_hand("bad", "bad", "bad")

    with pytest.raises(SourceAuthError):
        await LinkedInStep().run(world.context())

    assert world.env.values["LINKEDIN_ACCESS_TOKEN"] == "linkedin-old"


async def test_a_date_with_slashes_is_asked_again() -> None:
    world = _by_hand(GOOD_LINKEDIN, "03/04/2027", "Sep 24, 2027", False)

    await LinkedInStep().run(world.context())

    assert world.env.values["LINKEDIN_TOKEN_EXPIRES_ON"] == "2027-09-24"
    assert "write the date as YYYY-MM-DD or with the month's name" in world.io.text()


async def test_a_past_expiry_date_is_refused() -> None:
    world = _by_hand(GOOD_LINKEDIN, "2020-01-01", "1 Jan 2020", "31/12/2027")

    with pytest.raises(ValidationFailedError, match="YYYY-MM-DD"):
        await LinkedInStep().run(world.context())

    assert world.env.values["LINKEDIN_TOKEN_EXPIRES_ON"] == "2026-10-03"
    assert "that date has already passed" in world.io.text()


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


@pytest.mark.parametrize("typed", ["78abcdefghijkl", " 86x7Yq2ZrT01 "])
async def test_a_client_id_is_accepted(typed: str) -> None:
    assert values.linkedin_client_id(typed) == typed.strip()


@pytest.mark.parametrize("typed", ["", "short", "has spaces in it", "https://www.linkedin.com"])
async def test_a_client_id_that_is_not_one_is_refused(typed: str) -> None:
    with pytest.raises(ValidationFailedError, match="Client ID"):
        values.linkedin_client_id(typed)


async def test_a_new_key_is_kept_when_linkedin_cannot_be_reached_to_try_it() -> None:
    world = _first_time(_PROFILE, False)
    world.linkedin.check_unreachable = True

    await LinkedInStep().run(world.context())

    assert world.env.values["LINKEDIN_ACCESS_TOKEN"] == GOOD_LINKEDIN
    assert world.env.values["LINKEDIN_TOKEN_EXPIRES_ON"] == "2027-09-24"
    assert any("could not be reached to try the new key" in line for line in world.io.said)
