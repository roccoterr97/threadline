"""What the Slack collector needs from a workspace, and which workspaces are set up.

The real reader is :class:`~tracker.infrastructure.slack.client.SlackClient`;
tests hand the collector their own. Several workspaces are read side by side,
each through its own opener, as several mailboxes are.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from functools import partial
from typing import Protocol

from tracker.domain.slack import SlackConversation, SlackIdentity, SlackMessage, SlackUser
from tracker.infrastructure.slack.client import SlackClient
from tracker.shared.config import Settings


class SlackReader(Protocol):
    """Reads one workspace's direct messages, read-only."""

    async def who_am_i(self) -> SlackIdentity:
        """Say whose token this is."""
        ...

    async def direct_conversations(self) -> list[SlackConversation]:
        """List the direct and group direct messages the owner is in."""
        ...

    async def history(self, channel_id: str, oldest: datetime) -> list[SlackMessage]:
        """Read a conversation's messages since a moment, thread replies left out."""
        ...

    async def replies(
        self, channel_id: str, thread_ts: str, oldest: datetime
    ) -> list[SlackMessage]:
        """Read one thread's replies since a moment."""
        ...

    async def members(self, channel_id: str) -> list[str]:
        """List who is in a group direct message."""
        ...

    async def user(self, user_id: str) -> SlackUser:
        """Look one account up."""
        ...


#: Opens one workspace for the length of a collection and closes it afterwards.
SlackOpener = Callable[[], AbstractAsyncContextManager[SlackReader]]


def configured_workspaces(settings: Settings) -> tuple[SlackOpener, ...]:
    """List the Slack workspaces the owner set up, one opener each.

    Args:
        settings: The process configuration.

    Returns:
        One opener per saved token, in the order they were saved.
    """
    return tuple(partial(SlackClient, token) for token in settings.slack_tokens)
