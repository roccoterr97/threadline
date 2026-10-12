"""Step: Slack, optional. Threadline reads your Slack direct messages.

You create a small app in your own workspace from a link that fills
everything in, install it, and paste its User OAuth Token. The step stops only
for that: it checks the token once with Slack, saves it, sends it to your copy
on GitHub when one is linked, and offers another workspace as its last line.

Asked for by name (``tracker setup slack``) it starts straight away; as part
of ``tracker setup extras`` it first asks whether to connect Slack at all.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Final

from pydantic import SecretStr

from tracker.domain.slack import SlackIdentity
from tracker.infrastructure.slack.client import check_slack_token
from tracker.services.setup import values
from tracker.services.setup.context import SetupContext
from tracker.services.setup.github_copy import linked_copy
from tracker.services.setup.github_values import save_on_github
from tracker.services.setup.models import StepName
from tracker.shared.config import split_slack_tokens
from tracker.shared.constants.slack import (
    SLACK_NEW_APP_LINK,
    SLACK_TOKEN_SEPARATOR,
    SLACK_USER_TOKEN_PREFIX,
)
from tracker.shared.errors import (
    SlackTokenRefusedError,
    SourceUnavailableError,
    TrackerError,
    ValidationFailedError,
)
from tracker.shared.logging import get_logger

TOKENS: Final[str] = "SLACK_USER_TOKENS"

#: Asks Slack whose token it is; replaced in tests.
TokenCheck = Callable[[SecretStr], Awaitable[SlackIdentity]]

_OFFER: Final[str] = "Connect Slack now? Threadline then reads your Slack direct messages"

_HOW: Final[tuple[str, ...]] = (
    "Threadline reads your Slack direct messages through a small app you create in your",
    "own workspace. It can only read; it never posts anything.",
    "On the Slack page that opens:",
    "  1. Pick your workspace, click 'Next', then 'Create'.",
    "  2. Open 'Install App' on the left, click 'Install to ...', then 'Allow'.",
    "  3. Copy the 'User OAuth Token' Slack then shows (it starts with xoxp-).",
    "If Slack shows 'Request to Install' instead, your workspace admin must approve the",
    f"app first. Once they have, run 'uv run tracker setup {StepName.SLACK}' again.",
)

_PROMPT: Final[str] = "Paste the User OAuth Token (it is not shown)"
_ANOTHER: Final[str] = "Add another Slack workspace?"
_SKIPPED: Final[str] = f"Skipped. Run 'uv run tracker setup {StepName.SLACK}' whenever you want it."

_log = get_logger(__name__)


class SlackStep:
    """Connects one Slack workspace after another, each with its own app."""

    name = StepName.SLACK
    title = "Slack (optional)"

    def __init__(self, check: TokenCheck = check_slack_token) -> None:
        """Bind the step to the way a token is checked.

        Args:
            check: Asks Slack whose token it is; Slack itself unless replaced.
        """
        self._check = check

    async def is_done(self, ctx: SetupContext) -> bool:
        """Done when at least one workspace's token is saved."""
        return bool(split_slack_tokens(ctx.env.get(TOKENS)))

    async def run(self, ctx: SetupContext) -> None:
        """Connect a workspace, then offer another one, until the owner says no."""
        if ctx.session.named_step != StepName.SLACK and not ctx.io.confirm(_OFFER, default=False):
            ctx.io.say(_SKIPPED)
            return
        await self._connect(ctx)
        while ctx.io.confirm(_ANOTHER, default=False):
            await self._connect(ctx)

    async def _connect(self, ctx: SetupContext) -> None:
        """Open the prefilled app page, check the pasted token, save and send it."""
        for line in _HOW:
            ctx.io.say(line)
        ctx.io.open_page(SLACK_NEW_APP_LINK)

        async def accept(raw: str) -> tuple[str, SlackIdentity]:
            token = _user_token(raw)
            return token, await self._check(SecretStr(token))

        token, identity = await ctx.ask_until_accepted(lambda: ctx.io.ask_secret(_PROMPT), accept)
        ctx.io.say(f"Slack accepted the token for the {identity.team_name} workspace.")
        tokens = await self._others_kept(ctx, token, identity)
        ctx.env.set(TOKENS, SLACK_TOKEN_SEPARATOR.join((*tokens, token)))
        ctx.io.say(f"Saved {TOKENS} in .env.")
        _send_to_github(ctx)

    async def _others_kept(
        self, ctx: SetupContext, token: str, identity: SlackIdentity
    ) -> list[str]:
        """The saved tokens to keep beside the new one.

        An earlier token for the same workspace is replaced, and one Slack no
        longer accepts is dropped: running the step again is how a refused
        token is fixed. A token that cannot be checked right now is kept.
        """
        kept: list[str] = []
        for saved in split_slack_tokens(ctx.env.get(TOKENS)):
            if saved == token:
                continue
            try:
                other = await self._check(SecretStr(saved))
            except SlackTokenRefusedError:
                ctx.io.say("Removed a saved Slack token that Slack no longer accepts.")
                continue
            except TrackerError as error:
                _log.warning("slack_saved_token_unchecked", code=error.code)
                kept.append(saved)
                continue
            if other.team_id == identity.team_id:
                ctx.io.say(f"Replaced the earlier token for {identity.team_name}.")
                continue
            kept.append(saved)
        return kept


def _user_token(raw: str) -> str:
    """Clean a pasted token and refuse anything but a User OAuth Token."""
    token = values.non_empty(raw, "the token")
    if not token.startswith(SLACK_USER_TOKEN_PREFIX):
        message = (
            f"that is not the User OAuth Token, which starts with {SLACK_USER_TOKEN_PREFIX} "
            "(a Bot token does not work)"
        )
        raise ValidationFailedError(message)
    return token


def _send_to_github(ctx: SetupContext) -> None:
    """Send the tokens to the owner's copy on GitHub, where the daily run reads them.

    Nothing is asked: the owner connected Slack so the daily run reads it.
    Without a copy yet, the GitHub step sends it with everything else later.
    """
    copy = linked_copy(ctx)
    command = f"uv run tracker setup {StepName.GITHUB}"
    if copy is None:
        return
    if not copy.confirmed:
        ctx.io.say(f"To send it to your copy on GitHub, run: {command}")
        return
    try:
        save_on_github(ctx, copy.name, [TOKENS], [])
    except SourceUnavailableError as error:
        ctx.io.say(f"{error.message}. To send it later, run: {command}")
