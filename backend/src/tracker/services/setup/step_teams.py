"""Extra step: Microsoft Teams chats, through a work or school account.

Teams is a sign-in of its own, next to Outlook's: Microsoft shows a personal
account's Teams chats to no application, so this one always signs in with a
work or school account, which may differ from the Outlook mailbox. The only
stop is the one the owner must make: open Microsoft's page, type the code and
approve. Nothing else is asked.

``tracker setup extras`` does not sign in: most people have no work Teams to
connect, so it names the command and moves on. ``tracker setup teams`` signs in.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Final

from tracker.services.setup.context import SetupContext
from tracker.services.setup.github_copy import linked_copy
from tracker.services.setup.github_values import save_on_github
from tracker.services.setup.models import StepName
from tracker.services.setup.ports import MicrosoftAccess
from tracker.services.setup.step_microsoft import microsoft_access
from tracker.shared.constants.collection import MICROSOFT_TEAMS_TENANT
from tracker.shared.errors import AdminApprovalRequiredError, SourceUnavailableError
from tracker.shared.logging import get_logger

#: The setting that switches Teams on for every run.
TEAMS_ENABLED: Final[str] = "TEAMS_ENABLED"

#: What the setting holds once Teams is connected.
_ON: Final[str] = "true"

#: How the owner types the set-up.
_COMMAND: Final[str] = "uv run tracker setup"

_BEFORE_SIGN_IN: Final[tuple[str, ...]] = (
    "Threadline reads your Teams chats, read-only. This needs your work or school",
    "account: the one you use for Teams. A personal Outlook or Hotmail account does not work.",
    "A Microsoft page opens: type the code below, sign in with that account, and approve.",
    "If Microsoft says an admin has to approve, your organisation blocks this and only",
    "its IT admin can allow it.",
)

_ADMIN_HAS_TO_ALLOW: Final[tuple[str, ...]] = (
    "Teams is not connected: your organisation does not let you allow Threadline yourself.",
    "Your organisation's IT admin has to allow this. Ask them to allow the application you",
    "just signed in to, with the permission 'Read user chat messages' (Chat.Read).",
)

_log = get_logger(__name__)


class TeamsStep:
    """Signs in to Teams once with a short code; the key then renews itself."""

    name = StepName.TEAMS
    title = "Microsoft Teams chats (work or school account)"

    async def is_done(self, ctx: SetupContext) -> bool:
        """Done when the Teams key is stored and Teams is switched on."""
        if ctx.env.get(TEAMS_ENABLED) != _ON:
            return False
        return await ctx.gateways.microsoft.is_signed_in_to_teams(teams_access(ctx))

    async def run(self, ctx: SetupContext) -> None:
        """Show the code, wait for the sign-in, then switch Teams on here and on GitHub."""
        io = ctx.io
        if ctx.session.named_step != StepName.TEAMS:
            io.say("Teams chats left out: they need a work or school account.")
            io.say(f"To add them: {_COMMAND} {StepName.TEAMS}")
            return
        for line in _BEFORE_SIGN_IN:
            io.say(line)
        try:
            address = await ctx.gateways.microsoft.sign_in_to_teams(
                teams_access(ctx), lambda url, code: _show_code(ctx, url, code)
            )
        except AdminApprovalRequiredError:
            _log.info("teams_admin_approval_required")
            for line in _ADMIN_HAS_TO_ALLOW:
                io.say(line)
            return
        io.say(f"Signed in to Teams as {address}." if address else "Signed in to Teams.")
        ctx.env.set(TEAMS_ENABLED, _ON)
        io.say("Your Teams chats are read from the next run on.")
        _send_to_github(ctx)


def teams_access(ctx: SetupContext) -> MicrosoftAccess:
    """What the Teams sign-in needs: the Outlook one's, with work accounts only."""
    return replace(microsoft_access(ctx), tenant=MICROSOFT_TEAMS_TENANT)


def _send_to_github(ctx: SetupContext) -> None:
    """Switch Teams on for the daily run on GitHub too, without asking.

    Without a copy on GitHub yet there is nothing to do: the GitHub step sends
    every saved setting when it runs.
    """
    io = ctx.io
    command = f"{_COMMAND} {StepName.GITHUB}"
    copy = linked_copy(ctx)
    if copy is None:
        return
    if not copy.confirmed:
        io.say(f"To let the daily run on GitHub read Teams too, run: {command}")
        return
    io.say("Telling the daily run on GitHub to read Teams too:")
    try:
        save_on_github(ctx, copy.name, (), (TEAMS_ENABLED,))
    except SourceUnavailableError as error:
        io.say(f"{error.message}. To send it later, run: {command}")


def _show_code(ctx: SetupContext, url: str, code: str) -> None:
    """Show the one-time code and open the page it is typed on."""
    ctx.io.say(f"Your code: {code}")
    ctx.io.open_page(url)
