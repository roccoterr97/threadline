"""The Teams set-up step: one stop for the sign-in, and no question at all."""

from __future__ import annotations

import pytest

from tests.setup_world import configured_env, make_world
from tracker.services.setup.models import StepGroup, StepName
from tracker.services.setup.step_teams import TEAMS_ENABLED, TeamsStep
from tracker.services.setup.wizard import SetupWizard, default_steps
from tracker.shared.constants.collection import MICROSOFT_TEAMS_TENANT
from tracker.shared.errors import AdminApprovalRequiredError, WorkAccountRequiredError


@pytest.mark.asyncio
async def test_by_name_it_signs_in_with_a_work_account_and_asks_nothing() -> None:
    world = make_world([], configured_env())

    finished = await SetupWizard(world.context(), default_steps()).run_one(StepName.TEAMS)

    assert finished
    assert world.io.asked == []
    (access,) = world.microsoft.teams_accesses
    assert access.tenant == MICROSOFT_TEAMS_TENANT
    assert world.microsoft.accesses == []
    assert world.io.opened == ["https://microsoft.example/link"]
    text = world.io.text()
    assert "Your code: TEAMS-123" in text
    assert "Signed in to Teams as sam.rivera@work.example." in text
    assert world.env.values[TEAMS_ENABLED] == "true"


@pytest.mark.asyncio
async def test_teams_is_switched_on_for_the_daily_run_on_github_without_asking() -> None:
    world = make_world([], configured_env())

    await SetupWizard(world.context(), default_steps()).run_one(StepName.TEAMS)

    assert world.github.variables == {TEAMS_ENABLED: "true"}
    assert world.io.asked == []


@pytest.mark.asyncio
async def test_without_the_github_tool_it_names_the_command_that_sends_the_setting() -> None:
    world = make_world([], configured_env())
    world.github.signed_in = False

    await SetupWizard(world.context(), default_steps()).run_one(StepName.TEAMS)

    assert world.github.variables == {}
    assert "uv run tracker setup github" in world.io.text()


@pytest.mark.asyncio
async def test_an_organisation_that_blocks_it_is_told_its_it_admin_must_allow_it() -> None:
    world = make_world([], configured_env())
    world.microsoft.teams_refusal = AdminApprovalRequiredError("blocked")

    finished = await SetupWizard(world.context(), default_steps()).run_one(StepName.TEAMS)

    assert finished
    assert TEAMS_ENABLED not in world.env.values
    text = world.io.text()
    assert "Your organisation's IT admin has to allow this." in text
    assert "Chat.Read" in text
    assert world.github.variables == {}


@pytest.mark.asyncio
async def test_a_personal_account_stops_the_step_with_a_plain_reason() -> None:
    world = make_world([], configured_env())
    world.microsoft.teams_refusal = WorkAccountRequiredError(
        "Teams chats can be read only with a work or school account"
    )

    finished = await SetupWizard(world.context(), default_steps()).run_one(StepName.TEAMS)

    assert not finished
    assert TEAMS_ENABLED not in world.env.values
    assert "work or school account" in world.io.text()


@pytest.mark.asyncio
async def test_the_extras_leave_teams_out_and_say_how_to_add_it() -> None:
    world = make_world([], configured_env())
    step = TeamsStep()

    await step.run(world.context())

    assert world.microsoft.teams_accesses == []
    assert "To add them: uv run tracker setup teams" in world.io.text()
    assert StepName.TEAMS.group is StepGroup.EXTRAS


@pytest.mark.asyncio
async def test_it_is_done_only_with_a_stored_key_and_teams_switched_on() -> None:
    world = make_world([], configured_env())
    step = TeamsStep()

    assert not await step.is_done(world.context())
    world.microsoft.teams_signed_in = True
    assert not await step.is_done(world.context())
    world.env.values[TEAMS_ENABLED] = "true"
    assert await step.is_done(world.context())
