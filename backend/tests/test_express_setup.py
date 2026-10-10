"""The express set-up: a full ``tracker setup`` asks only what the owner must do.

Every other choice takes the usual answer and is said in one line, and the end
lists them all with the command that changes each. ``--ask-everything``, a step
run by name and the extras ask every question, as the other set-up tests show.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import SecretStr

from tests.setup_world import (
    GOOD_APP_PASSWORD,
    GOOD_CODE,
    GOOD_TOKEN,
    NEW_PROJECT_REF,
    ORGANIZATION,
    OWNER_EMAIL,
    World,
    configured_env,
    make_world,
)
from tests.test_claude_key_maker import MADE_SCREEN
from tests.test_github_setup import CLAUDE_KEY
from tracker.cli.commands import setup as setup_command
from tracker.domain.supabase import SupabaseProject
from tracker.services.setup.context import SetupContext
from tracker.services.setup.mail_provider import provider_for
from tracker.services.setup.models import StepGroup, StepName
from tracker.services.setup.ports import ClaudeCodeState
from tracker.services.setup.step_login import LoginStep
from tracker.services.setup.step_mailbox import ADDRESS_PROMPT, MailboxStep
from tracker.services.setup.step_supabase import SupabaseStep
from tracker.services.setup.wizard import SetupWizard, core_steps
from tracker.shared.constants.dashboard import HOSTED_DASHBOARD_URL
from tracker.shared.constants.github import CLAUDE_TOKEN_SECRET
from tracker.shared.constants.mailbox import ImapProvider, MailSource
from tracker.shared.constants.setup import RegionGroup
from tracker.shared.errors import SourceUnavailableError, ValidationFailedError

GMAIL_ADDRESS = "sam.rivera@gmail.com"


def express(world: World) -> SetupContext:
    """The world's context, as a full ``tracker setup`` without ``--ask-everything`` makes it."""
    ctx = world.context()
    ctx.session.express = True
    return ctx


def signed_in(world: World) -> SetupContext:
    """An express context that already holds this run's Supabase token."""
    ctx = express(world)
    ctx.session.supabase_token = SecretStr(GOOD_TOKEN)
    return ctx


def project(
    name: str, status: str = "ACTIVE_HEALTHY", ref: str = "otherprojectrefabcd"
) -> SupabaseProject:
    """A project in the account."""
    return SupabaseProject(ref, name, ORGANIZATION.slug, status)


# --- The whole run ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_first_express_run_asks_only_the_code_the_address_and_the_app_password() -> None:
    # The Supabase code, the e-mail address and the app password: nothing else.
    world = make_world([GOOD_CODE, GMAIL_ADDRESS, GOOD_APP_PASSWORD])
    world.claude.state_now = ClaudeCodeState.READY
    world.claude.screen = MADE_SCREEN

    finished = await SetupWizard(express(world), core_steps()).run_core()

    assert finished, world.io.text()
    assert not world.io.answers
    values = world.env.values
    assert values["SUPABASE_URL"] == f"https://{NEW_PROJECT_REF}.supabase.co"
    assert world.platform.created[0].name == "threadline"
    assert world.platform.created[0].region is RegionGroup.EMEA
    assert values["IMAP_PROVIDER"] == "gmail"
    assert values["IMAP_USERNAME"] == GMAIL_ADDRESS
    assert values["OWNER_EMAIL_ADDRESSES"] == GMAIL_ADDRESS
    assert values["OWNER_TIME_ZONE"] == "Europe/Paris"
    assert values["DASHBOARD_BASE_URL"] == HOSTED_DASHBOARD_URL
    assert world.admin.users[OWNER_EMAIL] in world.admin.owners
    assert world.github.secrets[CLAUDE_TOKEN_SECRET] == CLAUDE_KEY
    assert world.github.started


@pytest.mark.asyncio
async def test_an_express_run_says_each_choice_it_made_and_how_to_change_it() -> None:
    world = make_world([GOOD_CODE, GMAIL_ADDRESS, GOOD_APP_PASSWORD])
    world.claude.state_now = ClaudeCodeState.READY
    world.claude.screen = MADE_SCREEN

    await SetupWizard(express(world), core_steps()).run_core()

    text = world.io.text()
    assert f"Your dashboard login is {OWNER_EMAIL}, the address of your Supabase account," in text
    assert "Kept the usual job-search categories." in text
    assert "Your time zone: Europe/Paris." in text
    assert "uv run tracker setup timezone" in text
    assert "Outlook left out. To add it or its calendar: uv run tracker setup microsoft" in text
    assert "Your own copy instead: uv run tracker setup dashboard" in text
    assert "To change the time: uv run tracker setup schedule" in text
    assert f"Added {GMAIL_ADDRESS} to your own addresses" in text


# --- The mailbox: one question --------------------------------------------------------


@pytest.mark.parametrize(
    ("address", "provider"),
    [
        ("sam@gmail.com", ImapProvider.GMAIL),
        ("sam@googlemail.com", ImapProvider.GMAIL),
        ("Sam@GMAIL.COM", ImapProvider.GMAIL),
        ("sam@outlook.com", MailSource.OUTLOOK),
        ("sam@outlook.fr", MailSource.OUTLOOK),
        ("sam@hotmail.co.uk", MailSource.OUTLOOK),
        ("sam@live.it", MailSource.OUTLOOK),
        ("sam@msn.com", MailSource.OUTLOOK),
        ("sam@icloud.com", ImapProvider.ICLOUD),
        ("sam@me.com", ImapProvider.ICLOUD),
        ("sam@mac.com", ImapProvider.ICLOUD),
        ("sam@yahoo.com", ImapProvider.YAHOO),
        ("sam@yahoo.co.uk", ImapProvider.YAHOO),
        ("sam@fastmail.com", ImapProvider.FASTMAIL),
        ("sam@fastmail.fm", ImapProvider.FASTMAIL),
    ],
)
def test_the_provider_is_told_from_the_address(
    address: str, provider: MailSource | ImapProvider
) -> None:
    assert provider_for(address) is provider


@pytest.mark.parametrize(
    "address",
    ["sam@example.com", "sam@company.io", "sam@live.example.org", "sam@gmail.example.com"],
)
def test_an_address_of_any_other_domain_names_no_provider(address: str) -> None:
    assert provider_for(address) is None


@pytest.mark.asyncio
async def test_express_asks_only_the_address_for_a_known_provider() -> None:
    world = make_world([GMAIL_ADDRESS, GOOD_APP_PASSWORD], configured_env())

    await MailboxStep().run(express(world))

    assert ADDRESS_PROMPT in world.io.defaults
    assert not any("Which mailbox" in prompt for prompt in world.io.defaults)
    assert "Your Gmail address" not in world.io.defaults
    assert "From the address, your mailbox is Gmail." in world.io.said
    assert world.env.values["IMAP_USERNAME"] == GMAIL_ADDRESS
    assert world.env.values["OWNER_EMAIL_ADDRESSES"] == GMAIL_ADDRESS


@pytest.mark.asyncio
async def test_an_unknown_domain_falls_back_to_the_provider_question() -> None:
    address = "sam@company.example"
    world = make_world([address, "gmail", GOOD_APP_PASSWORD], configured_env())

    await MailboxStep().run(express(world))

    assert any("Which mailbox" in prompt for prompt in world.io.defaults)
    assert "Your Gmail address" not in world.io.defaults
    assert world.env.values["IMAP_PROVIDER"] == "gmail"
    assert world.env.values["IMAP_USERNAME"] == address


@pytest.mark.asyncio
async def test_an_outlook_address_hands_on_to_the_microsoft_sign_in() -> None:
    world = make_world(["sam@hotmail.com"], configured_env())

    await MailboxStep().run(express(world))

    assert world.env.values["MAIL_SOURCES"] == "outlook"
    assert "Outlook is read through a Microsoft sign-in: it comes next." in world.io.said


@pytest.mark.asyncio
async def test_a_step_run_by_name_still_asks_which_mailbox() -> None:
    world = make_world(["gmail", GMAIL_ADDRESS, GOOD_APP_PASSWORD, True], configured_env())

    await MailboxStep().run(world.context())

    assert any("Which mailbox" in prompt for prompt in world.io.defaults)
    assert "Your Gmail address" in world.io.defaults


# --- The Supabase project: threadline, or nothing taken unasked ------------------------


@pytest.mark.asyncio
async def test_express_reuses_the_project_named_threadline_without_asking() -> None:
    world = make_world([GOOD_CODE])
    ours = project("threadline", ref=NEW_PROJECT_REF)
    world.platform.project_list = [project("my-shop"), ours]

    await SupabaseStep().run(express(world))

    assert world.platform.created == []
    assert world.env.values["SUPABASE_URL"] == f"https://{NEW_PROJECT_REF}.supabase.co"
    assert f"Using your Supabase project 'threadline' ({NEW_PROJECT_REF})." in world.io.said


@pytest.mark.asyncio
async def test_express_reuses_a_threadline_project_that_is_still_starting() -> None:
    world = make_world([GOOD_CODE])
    world.platform.project_list = [project("threadline", "COMING_UP", ref=NEW_PROJECT_REF)]

    await SupabaseStep().run(express(world))

    assert world.platform.created == []
    assert "The project is up." in world.io.said


@pytest.mark.asyncio
async def test_express_creates_threadline_beside_a_project_of_another_name() -> None:
    world = make_world([GOOD_CODE])
    world.platform.project_list = [project("my-shop")]

    await SupabaseStep().run(express(world))

    assert [request.name for request in world.platform.created] == ["threadline"]
    assert world.env.values["SUPABASE_URL"] == f"https://{NEW_PROJECT_REF}.supabase.co"


@pytest.mark.asyncio
async def test_a_full_free_plan_lists_the_projects_and_takes_none_unasked() -> None:
    # The code, then "no" to using one of the projects listed.
    world = make_world([GOOD_CODE, False])
    world.platform.project_list = [project("my-shop"), project("blog", ref="blogprojectrefabcde")]
    world.platform.create_refusal = "the organization has reached its free project limit"

    with pytest.raises(ValidationFailedError, match="no project to use yet"):
        await SupabaseStep().run(express(world))

    text = world.io.text()
    assert "On the free plan an account has at most two active projects. Yours:" in text
    assert "  1. my-shop (running)" in world.io.said
    assert "SUPABASE_URL" not in world.env.values


@pytest.mark.asyncio
async def test_a_project_of_another_name_is_used_only_after_a_yes_and_a_number() -> None:
    world = make_world([GOOD_CODE, True, "2"])
    world.platform.project_list = [
        project("my-shop"),
        project("blog", ref=NEW_PROJECT_REF),
    ]
    world.platform.create_refusal = "the organization has reached its free project limit"

    await SupabaseStep().run(express(world))

    assert world.io.defaults["Which one? (number)"] is None
    assert world.env.values["SUPABASE_URL"] == f"https://{NEW_PROJECT_REF}.supabase.co"


@pytest.mark.asyncio
async def test_a_refusal_with_no_other_project_stops_the_step() -> None:
    world = make_world([GOOD_CODE])
    world.platform.create_refusal = "something else"

    with pytest.raises(SourceUnavailableError, match="something else"):
        await SupabaseStep().run(express(world))


@pytest.mark.asyncio
async def test_a_paused_threadline_project_stops_express_instead_of_making_another() -> None:
    world = make_world([GOOD_CODE, ""])
    world.platform.project_list = [project("threadline", "INACTIVE")]

    with pytest.raises(ValidationFailedError, match="is paused - restore it"):
        await SupabaseStep().run(express(world))

    assert world.platform.created == []


@pytest.mark.asyncio
async def test_several_threadline_projects_are_asked_about() -> None:
    world = make_world([GOOD_CODE, "2"])
    world.platform.project_list = [
        project("threadline", ref="firstprojectrefabcd"),
        project("threadline", ref=NEW_PROJECT_REF),
    ]

    await SupabaseStep().run(express(world))

    assert world.env.values["SUPABASE_URL"] == f"https://{NEW_PROJECT_REF}.supabase.co"


# --- The dashboard login -------------------------------------------------------------


@pytest.mark.asyncio
async def test_express_makes_the_login_for_the_supabase_account_address_without_asking() -> None:
    world = make_world([], configured_env())

    await LoginStep().run(signed_in(world))

    assert world.admin.users[OWNER_EMAIL] in world.admin.owners
    assert f"{OWNER_EMAIL} can now sign in to the dashboard, and nobody else can read it." in (
        world.io.said
    )


@pytest.mark.asyncio
async def test_without_the_account_address_the_login_is_asked_once_offering_the_mailbox() -> None:
    world = make_world([""], configured_env() | {"IMAP_USERNAME": GMAIL_ADDRESS})
    world.platform.profile_failure = SourceUnavailableError("Supabase could not be reached")

    await LoginStep().run(signed_in(world))

    assert world.io.defaults["E-mail address for the dashboard"] == GMAIL_ADDRESS
    assert world.admin.users[GMAIL_ADDRESS] in world.admin.owners


@pytest.mark.asyncio
async def test_a_step_run_by_name_offers_the_account_address() -> None:
    world = make_world([""], configured_env())
    ctx = world.context()
    ctx.session.supabase_token = SecretStr(GOOD_TOKEN)

    await LoginStep().run(ctx)

    assert world.io.defaults["E-mail address for the dashboard"] == OWNER_EMAIL


@pytest.mark.asyncio
async def test_a_finished_login_still_names_its_address() -> None:
    world = make_world([], configured_env())
    world.admin.users = {OWNER_EMAIL: "user-1"}
    world.admin.owners = ["user-1"]

    assert await SetupWizard(express(world), [LoginStep()]).run_core()

    said = world.io.said
    done = said.index("Already done. To redo it: uv run tracker setup login")
    assert said[done + 1] == f"Your dashboard login: {OWNER_EMAIL}"


# --- --ask-everything ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("request_", "ask_everything", "expected"),
    [
        (StepGroup.CORE, False, True),
        (StepGroup.CORE, True, False),
        (StepGroup.EXTRAS, False, False),
        (StepName.MAILBOX, False, False),
    ],
)
def test_only_a_full_run_without_ask_everything_is_express(
    request_: StepName | StepGroup, ask_everything: bool, expected: bool
) -> None:
    assert setup_command.is_express(request_, ask_everything) is expected


@pytest.mark.parametrize(("flag", "expected"), [(False, True), (True, False)])
def test_ask_everything_reaches_the_run(
    monkeypatch: pytest.MonkeyPatch, flag: bool, expected: bool
) -> None:
    asked: list[dict[str, Any]] = []

    async def wizard(step: object, io: object = None, **options: Any) -> bool:
        asked.append(options)
        return True

    monkeypatch.setattr(setup_command, "_run", wizard)
    monkeypatch.setattr(setup_command, "print_doctor_report", lambda: True)

    setup_command.setup(None, ask_everything=flag)

    assert asked == [{"build_here": False, "express": expected}]


@pytest.mark.asyncio
async def test_ask_everything_brings_back_the_old_questions() -> None:
    # Without express: the project offer, the route, its name and region come back.
    world = make_world([True, "", GOOD_CODE, "", ""])

    await SupabaseStep().run(world.context())

    prompts = list(world.io.defaults)
    assert "Your choice (number)" in prompts
    assert "Name for the new project" in prompts
    assert "Region (number)" in prompts


# --- The list at the end -------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_end_lists_every_choice_with_the_command_that_changes_it() -> None:
    env = configured_env() | {
        "MAIL_SOURCES": "imap",
        "IMAP_PROVIDER": "gmail",
        "IMAP_USERNAME": GMAIL_ADDRESS,
        "OWNER_TIME_ZONE": "Europe/Paris",
        "DASHBOARD_BASE_URL": HOSTED_DASHBOARD_URL,
    }
    world = make_world([], env)
    world.admin.users = {OWNER_EMAIL: "user-1"}
    world.admin.owners = ["user-1"]

    assert await SetupWizard(express(world), []).run_core()

    said = world.io.said
    start = said.index("What was chosen, and the command that changes each:")
    assert said[start + 1 : start + 8] == [
        f"  Mailbox: {GMAIL_ADDRESS} (Gmail). Change: uv run tracker setup mailbox",
        "  Outlook: not connected. Change: uv run tracker setup microsoft",
        "  Categories: the usual job-search list. Change: uv run tracker setup categories",
        "  Time zone: Europe/Paris. Change: uv run tracker setup timezone",
        "  Daily run: every day at 07:00 (UTC). Change: uv run tracker setup schedule",
        "  Dashboard: Threadline's shared dashboard. Change: uv run tracker setup dashboard",
        f"  Dashboard login: {OWNER_EMAIL}. Change: uv run tracker setup login",
    ]
    link = f"Your dashboard: {HOSTED_DASHBOARD_URL}/#project="
    assert any(line.startswith(link) for line in said)
    assert f"Sign in there with {OWNER_EMAIL}: a sign-in link is e-mailed to that address." in said
