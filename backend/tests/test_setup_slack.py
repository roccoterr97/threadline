"""The Slack set-up step, without a terminal or a network."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from pydantic import SecretStr

from tests.setup_world import World, configured_env, make_world
from tracker.domain.slack import SlackIdentity
from tracker.services.setup.context import SetupContext
from tracker.services.setup.models import StepName
from tracker.services.setup.step_slack import SlackStep
from tracker.services.setup.wizard import SetupWizard
from tracker.shared.constants.slack import SLACK_NEW_APP_LINK
from tracker.shared.errors import (
    SlackApprovalNeededError,
    SlackTokenRefusedError,
    SourceUnavailableError,
    ValidationFailedError,
)

pytestmark = pytest.mark.asyncio

ACME = "xoxp-acme-new"
BETA = "xoxp-beta"
PROMPT = "Paste the User OAuth Token (it is not shown)"
ANOTHER = "Add another Slack workspace?"


@dataclass
class FakeSlackCheck:
    """Slack's ``auth.test``: which workspace each token belongs to, and what it refuses."""

    teams: dict[str, tuple[str, str]] = field(
        default_factory=lambda: {
            ACME: ("T0ACME", "Acme"),
            "xoxp-acme-old": ("T0ACME", "Acme"),
            BETA: ("T0BETA", "Beta"),
        }
    )
    refused: set[str] = field(default_factory=set)
    approval_needed: set[str] = field(default_factory=set)
    unreachable: set[str] = field(default_factory=set)
    checked: list[str] = field(default_factory=list)

    async def __call__(self, token: SecretStr) -> SlackIdentity:
        value = token.get_secret_value()
        self.checked.append(value)
        if value in self.unreachable:
            message = "Slack could not be reached"
            raise SourceUnavailableError(message)
        if value in self.approval_needed:
            message = "Slack says your workspace admin must approve the Threadline app"
            raise SlackApprovalNeededError(message)
        if value in self.refused or value not in self.teams:
            message = "Slack no longer accepts the saved key (invalid_auth)"
            raise SlackTokenRefusedError(message)
        team_id, team = self.teams[value]
        return SlackIdentity(user_id="U0OWNER", team_id=team_id, team_name=team)


async def by_name(world: World, check: FakeSlackCheck) -> bool:
    """Run the step as ``tracker setup slack`` does."""
    return await SetupWizard(world.context(), [SlackStep(check)]).run_one(StepName.SLACK)


async def test_asked_for_by_name_it_stops_only_for_the_token_and_the_last_line() -> None:
    world = make_world([ACME, False], configured_env())
    check = FakeSlackCheck()

    assert await by_name(world, check)

    assert world.io.asked == [PROMPT, ANOTHER]
    assert world.io.opened == [SLACK_NEW_APP_LINK]
    assert world.env.values["SLACK_USER_TOKENS"] == ACME
    assert world.github.secrets == {"SLACK_USER_TOKENS": ACME}
    text = world.io.text()
    assert "Slack accepted the token for the Acme workspace." in text
    assert "Request to Install" in text
    assert ACME not in text


async def test_in_the_extras_it_asks_once_and_can_be_skipped() -> None:
    world = make_world([False], configured_env())

    await SlackStep(FakeSlackCheck()).run(world.context())

    assert world.io.asked == ["Connect Slack now? Threadline then reads your Slack direct messages"]
    assert "SLACK_USER_TOKENS" not in world.env.values
    assert "Skipped. Run 'uv run tracker setup slack' whenever you want it." in world.io.said


async def test_a_bot_token_or_a_refused_token_is_asked_for_again() -> None:
    world = make_world(["xoxb-bot", "xoxp-wrong", ACME, False], configured_env())
    check = FakeSlackCheck()

    assert await by_name(world, check)

    assert world.env.values["SLACK_USER_TOKENS"] == ACME
    text = world.io.text()
    assert "that is not the User OAuth Token, which starts with xoxp-" in text
    assert "Slack no longer accepts the saved key" in text
    assert check.checked == ["xoxp-wrong", ACME]


async def test_a_workspace_waiting_for_approval_is_said_plainly() -> None:
    world = make_world([ACME, ACME, ACME], configured_env())
    check = FakeSlackCheck(approval_needed={ACME})

    assert not await by_name(world, check)

    assert "admin must approve" in world.io.text()
    assert "SLACK_USER_TOKENS" not in world.env.values


async def test_another_workspace_is_saved_beside_the_first() -> None:
    world = make_world([ACME, True, BETA, False], configured_env())

    assert await by_name(world, FakeSlackCheck())

    assert world.env.values["SLACK_USER_TOKENS"] == f"{ACME},{BETA}"
    assert world.github.secrets == {"SLACK_USER_TOKENS": f"{ACME},{BETA}"}
    assert world.io.opened == [SLACK_NEW_APP_LINK, SLACK_NEW_APP_LINK]


async def test_a_new_token_replaces_its_workspaces_old_one_and_a_dead_one_goes() -> None:
    saved = "xoxp-acme-old,xoxp-revoked,xoxp-offline"
    world = make_world([ACME, False], configured_env() | {"SLACK_USER_TOKENS": saved})
    check = FakeSlackCheck(refused={"xoxp-revoked"}, unreachable={"xoxp-offline"})

    assert await by_name(world, check)

    assert world.env.values["SLACK_USER_TOKENS"] == f"xoxp-offline,{ACME}"
    text = world.io.text()
    assert "Replaced the earlier token for Acme." in text
    assert "Removed a saved Slack token that Slack no longer accepts." in text


async def test_without_the_github_cli_it_names_the_command_that_sends_it() -> None:
    world = make_world([ACME, False], configured_env())
    world.github.signed_in = False

    assert await by_name(world, FakeSlackCheck())

    assert world.github.secrets == {}
    assert "To send it to your copy on GitHub, run: uv run tracker setup github" in world.io.said


async def test_it_is_done_once_a_token_is_saved() -> None:
    step = SlackStep(FakeSlackCheck())

    assert not await step.is_done(make_world([], configured_env()).context())
    assert await step.is_done(
        make_world([], configured_env() | {"SLACK_USER_TOKENS": ACME}).context()
    )


async def test_nothing_pasted_three_times_stops_the_step() -> None:
    world = make_world(["", "", ""], configured_env())

    with pytest.raises(ValidationFailedError):
        await SlackStep(FakeSlackCheck()).run(_named(world))


def _named(world: World) -> SetupContext:
    context = world.context()
    context.session.named_step = StepName.SLACK
    return context
