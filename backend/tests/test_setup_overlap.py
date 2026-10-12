"""Asking for the mailbox, then the Claude key, while Supabase starts a new project.

Supabase takes one to three minutes to start a project. A full run gives that
time to the mailbox: the address, and the app password checked live, held in
memory until the database is ready, then stored by the mailbox step without
asking again. If the project is still not up after that, the Claude key is
made too, and held for the GitHub step. A project that is already up changes
nothing.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from tests.setup_world import (
    GOOD_APP_PASSWORD,
    GOOD_CODE,
    NEW_PROJECT_REF,
    ORGANIZATION,
    World,
    configured_env,
    make_world,
)
from tests.test_claude_key_maker import MADE_SCREEN
from tests.test_github_setup import CLAUDE_KEY, github_env
from tracker.domain.supabase import SupabaseProject
from tracker.services.setup import step_mailbox
from tracker.services.setup.claude_key_maker import MEANWHILE_KEY, make_while_project_starts
from tracker.services.setup.context import SetupContext
from tracker.services.setup.mailbox_answers import CheckedImapMailbox
from tracker.services.setup.models import StepName
from tracker.services.setup.ports import ClaudeCodeState
from tracker.services.setup.step_github import GitHubStep
from tracker.services.setup.step_mailbox import (
    ADDRESS_PROMPT,
    MEANWHILE,
    MailboxStep,
    ask_while_project_starts,
)
from tracker.services.setup.step_supabase import SupabaseStep
from tracker.services.setup.wizard import SetupWizard, core_steps
from tracker.shared.constants.github import CLAUDE_TOKEN_SECRET
from tracker.shared.constants.mailbox import ImapProvider, MailSource
from tracker.shared.constants.setup import PROJECT_READY_WAIT_SECONDS
from tracker.shared.errors import SetupStoppedError

pytestmark = pytest.mark.asyncio

GMAIL_ADDRESS = "sam.rivera@gmail.com"
PROJECT_UP = "The Supabase project is up."


def express(world: World) -> SetupContext:
    """The context of a full ``tracker setup`` run."""
    ctx = world.context()
    ctx.session.express = True
    return ctx


def overlapping_step() -> SupabaseStep:
    """The Supabase step with the mailbox asked while the project starts."""
    return SupabaseStep(meanwhile=(ask_while_project_starts,))


def full_run_world(statuses: list[str]) -> World:
    """A first run where Claude Code can make the key and the project starts as given."""
    world = make_world([GOOD_CODE, GMAIL_ADDRESS, GOOD_APP_PASSWORD])
    world.platform.statuses = statuses
    world.claude.state_now = ClaudeCodeState.READY
    world.claude.screen = MADE_SCREEN
    return world


async def test_a_full_run_asks_the_mailbox_while_the_new_project_starts() -> None:
    world = make_world([GOOD_CODE, GMAIL_ADDRESS, GOOD_APP_PASSWORD])
    world.claude.state_now = ClaudeCodeState.READY
    world.claude.screen = MADE_SCREEN

    assert await SetupWizard(express(world), core_steps()).run_core()

    said = world.io.said
    starting = said.index("Supabase is starting the project; this takes one to three minutes.")
    checked = said.index("Connected. Your inbox has 42 messages from the last 30 days.")
    assert starting < said.index(MEANWHILE) < checked < said.index(PROJECT_UP)
    assert world.io.asked.count(ADDRESS_PROMPT) == 1
    assert world.mailbox.saved == {GMAIL_ADDRESS: GOOD_APP_PASSWORD}
    assert GOOD_APP_PASSWORD not in world.env.values.values()


async def test_the_checked_password_is_held_in_memory_until_the_mailbox_step() -> None:
    world = make_world([GOOD_CODE, GMAIL_ADDRESS, GOOD_APP_PASSWORD])
    ctx = express(world)

    await overlapping_step().run(ctx)

    held = ctx.session.held_mailbox
    assert isinstance(held, CheckedImapMailbox)
    assert held.provider is ImapProvider.GMAIL
    assert held.password.get_secret_value() == GOOD_APP_PASSWORD
    assert world.mailbox.saved == {}
    assert "IMAP_USERNAME" not in world.env.values
    assert GOOD_APP_PASSWORD not in world.env.values.values()

    ctx.env.set("TOKEN_ENCRYPTION_KEY", "saved-key")
    await MailboxStep().run(ctx)

    assert not world.io.answers
    assert world.mailbox.saved == {GMAIL_ADDRESS: GOOD_APP_PASSWORD}
    assert world.mailbox.checked == [(held.account, GOOD_APP_PASSWORD)]
    assert ctx.session.held_mailbox is None


async def test_a_project_already_up_leaves_the_mailbox_to_its_own_step() -> None:
    world = make_world([GOOD_CODE])
    world.platform.project_list = [
        SupabaseProject(NEW_PROJECT_REF, "threadline", ORGANIZATION.slug, "ACTIVE_HEALTHY")
    ]
    ctx = express(world)

    await overlapping_step().run(ctx)

    assert MEANWHILE not in world.io.said
    assert ADDRESS_PROMPT not in world.io.asked
    assert ctx.session.held_mailbox is None
    assert world.waits == []


async def test_a_mailbox_problem_while_the_project_starts_leaves_it_to_be_asked_again() -> None:
    world = make_world([GOOD_CODE, GMAIL_ADDRESS, "wrong1", "wrong2", "wrong3"])
    ctx = express(world)

    await overlapping_step().run(ctx)

    assert ctx.session.held_mailbox is None
    assert any(
        line.endswith("Your mailbox is asked again once the project is up.")
        for line in world.io.said
    )
    assert PROJECT_UP in world.io.said
    assert world.env.values["SUPABASE_URL"] == f"https://{NEW_PROJECT_REF}.supabase.co"


async def test_a_project_supabase_gives_up_on_stops_the_run_after_the_mailbox() -> None:
    world = make_world([GOOD_CODE, GMAIL_ADDRESS, GOOD_APP_PASSWORD])
    world.platform.statuses = ["INIT_FAILED"]

    assert not await SetupWizard(express(world), core_steps()).run_core()

    text = world.io.text()
    assert "Stopped: Supabase could not set the project up (status INIT_FAILED)" in text
    assert "run 'uv run tracker setup' again" in text
    # The checked password was never written anywhere.
    assert world.mailbox.saved == {}
    assert GOOD_APP_PASSWORD not in world.env.values.values()


async def test_the_project_is_still_looked_at_after_the_mailbox_until_it_is_up() -> None:
    world = make_world([GOOD_CODE, GMAIL_ADDRESS, GOOD_APP_PASSWORD])
    world.platform.statuses = ["COMING_UP", "COMING_UP", "ACTIVE_HEALTHY"]

    await overlapping_step().run(express(world))

    assert world.io.said.count("Waiting for Supabase to finish starting the project...") == 1
    assert world.waits[:2] == [PROJECT_READY_WAIT_SECONDS, PROJECT_READY_WAIT_SECONDS]
    assert PROJECT_UP in world.io.said


async def test_a_step_run_by_name_does_not_ask_for_the_mailbox() -> None:
    world = make_world([GOOD_CODE])
    ctx = express(world)
    ctx.session.named_step = StepName.SUPABASE

    await overlapping_step().run(ctx)

    assert MEANWHILE not in world.io.said
    assert ctx.session.held_mailbox is None
    assert PROJECT_UP in world.io.said


async def test_a_saved_outlook_mailbox_is_not_asked_for_while_the_project_starts() -> None:
    world = make_world([GOOD_CODE], {"MAIL_SOURCES": "outlook"})

    await overlapping_step().run(express(world))

    assert MEANWHILE not in world.io.said


async def test_outlook_told_from_the_address_is_held_and_saved_without_asking_again() -> None:
    world = make_world([GOOD_CODE, "sam@outlook.com"])
    ctx = express(world)

    await overlapping_step().run(ctx)

    assert ctx.session.held_mailbox is MailSource.OUTLOOK
    ctx.env.set("TOKEN_ENCRYPTION_KEY", "saved-key")
    await MailboxStep().run(ctx)

    assert world.env.values["MAIL_SOURCES"] == "outlook"
    assert ctx.session.held_mailbox is None


async def test_the_mailbox_step_asks_as_before_when_nothing_is_held() -> None:
    world = make_world([GMAIL_ADDRESS, GOOD_APP_PASSWORD], configured_env())

    await MailboxStep().run(express(world))

    assert world.io.asked == [ADDRESS_PROMPT, world.io.secret_prompts[0]]
    assert world.mailbox.saved == {GMAIL_ADDRESS: GOOD_APP_PASSWORD}


async def test_stopping_the_set_up_while_the_project_starts_is_not_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = make_world([GOOD_CODE])

    async def stopped(_ctx: SetupContext) -> None:
        message = "the page was closed"
        raise SetupStoppedError(message)

    monkeypatch.setattr(step_mailbox, "ask_mailbox", stopped)

    with pytest.raises(SetupStoppedError):
        await overlapping_step().run(express(world))
    assert world.mailbox.saved == {}


# --- The Claude key, while the project is still starting -----------------------------


async def test_the_claude_key_is_made_while_the_project_is_still_starting() -> None:
    world = full_run_world(["COMING_UP", "COMING_UP", "ACTIVE_HEALTHY"])

    assert await SetupWizard(express(world), core_steps()).run_core()

    said = world.io.said
    assert said.index(MEANWHILE) < said.index(MEANWHILE_KEY) < said.index(PROJECT_UP)
    assert world.claude.runs == 1
    assert world.github.secrets[CLAUDE_TOKEN_SECRET] == CLAUDE_KEY


async def test_no_claude_key_is_made_early_once_the_project_is_up() -> None:
    world = full_run_world(["ACTIVE_HEALTHY"])

    assert await SetupWizard(express(world), core_steps()).run_core()

    said = world.io.said
    assert MEANWHILE_KEY not in said
    assert said.index(PROJECT_UP) < said.index("Got the Claude key.")
    assert world.claude.runs == 1


async def test_a_key_github_already_has_is_not_made_early() -> None:
    world = full_run_world(["COMING_UP", "COMING_UP", "ACTIVE_HEALTHY"])
    world.github.secrets[CLAUDE_TOKEN_SECRET] = "the-key-github-has"

    assert await SetupWizard(express(world), core_steps()).run_core()

    assert MEANWHILE_KEY not in world.io.said
    assert world.claude.runs == 0
    assert world.github.secrets[CLAUDE_TOKEN_SECRET] == "the-key-github-has"


async def test_a_claude_key_not_made_early_is_made_again_at_the_github_step() -> None:
    world = full_run_world(["COMING_UP", "COMING_UP", "ACTIVE_HEALTHY"])
    world.claude.exit_code = 1
    # Made again at the GitHub step, where it stops again, so it is pasted.
    world.io.answers.append(CLAUDE_KEY)

    assert await SetupWizard(express(world), core_steps()).run_core()

    said = world.io.said
    early = said.index(MEANWHILE_KEY)
    assert said[early + 2] == (
        "The key could not be made here (Claude stopped before it made one). "
        "It is made again at the end."
    )
    assert world.claude.runs == 2
    assert world.github.secrets[CLAUDE_TOKEN_SECRET] == CLAUDE_KEY


async def test_a_held_claude_key_goes_to_github_without_being_made_again() -> None:
    world = make_world([], github_env())
    ctx = express(world)
    ctx.session.claude_key = SecretStr(CLAUDE_KEY)
    world.claude.state_now = ClaudeCodeState.READY

    await GitHubStep().run(ctx)

    assert world.claude.runs == 0
    assert world.github.secrets[CLAUDE_TOKEN_SECRET] == CLAUDE_KEY
    assert ctx.session.claude_key is None


async def test_a_step_run_by_name_makes_no_claude_key_early() -> None:
    world = full_run_world(["COMING_UP", "COMING_UP", "ACTIVE_HEALTHY"])
    ctx = express(world)
    ctx.session.named_step = StepName.SUPABASE

    await make_while_project_starts(ctx)

    assert world.claude.runs == 0
    assert ctx.session.claude_key is None
