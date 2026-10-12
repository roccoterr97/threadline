"""Slack's direct messages as plain records, and the rules about who is a person.

The Slack reader maps Slack's answers onto these records, so the collector
never sees Slack's own shapes. Everything here is pure: no HTTP, no database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class SlackIdentity:
    """Who a token belongs to, as Slack's ``auth.test`` says.

    Attributes:
        user_id: The owner's own user identifier in that workspace.
        team_id: The workspace's identifier.
        team_name: The workspace's name, as people know it.
    """

    user_id: str
    team_id: str
    team_name: str


@dataclass(frozen=True, slots=True)
class SlackConversation:
    """One direct message or group direct message the owner is in.

    Attributes:
        channel_id: Slack's identifier for it, unique across Slack, so a Slack
            Connect conversation seen from two workspaces is one thread.
        is_group: Whether it is a group direct message (several people).
        other_user_id: For a one-to-one message, the other person.
        other_user_deleted: Whether that person's account was removed.
    """

    channel_id: str
    is_group: bool
    other_user_id: str | None = None
    other_user_deleted: bool = False


@dataclass(frozen=True, slots=True)
class SlackMessage:
    """One message, as Slack wrote it.

    Attributes:
        ts: Slack's timestamp, which is also the message's identifier in its
            conversation.
        sent_at: When it was sent, in UTC.
        user_id: Who wrote it, or ``None`` for a message no person wrote.
        text: The text in Slack's own markup.
        from_bot: Whether a bot or an app wrote it.
        subtype: Slack's kind for a message that is not a plain one, if any.
        reply_count: How many replies its thread has, when it starts one.
        file_names: The names of the files it shares.
    """

    ts: str
    sent_at: datetime
    user_id: str | None
    text: str
    from_bot: bool = False
    subtype: str | None = None
    reply_count: int = 0
    file_names: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SlackUser:
    """One Slack account, as ``users.info`` describes it.

    Attributes:
        user_id: Slack's identifier.
        name: The name to show: the real name, else the display name.
        email: The e-mail address, when Slack shares it.
        is_bot: Whether it is a bot, an app or Slackbot.
        is_deleted: Whether the account was removed.
    """

    user_id: str
    name: str
    email: str | None
    is_bot: bool = False
    is_deleted: bool = False

    @property
    def is_person(self) -> bool:
        """Whether a person who can still answer stands behind the account."""
        return not self.is_bot and not self.is_deleted


def is_person_message(message: SlackMessage, person_subtypes: frozenset[str]) -> bool:
    """Whether a person wrote a message, rather than a bot or Slack itself.

    Args:
        message: The message.
        person_subtypes: The kinds that still carry what a person wrote.

    Returns:
        ``True`` for a plain message, or one of those kinds, by a user.
    """
    if message.user_id is None or message.from_bot:
        return False
    return message.subtype is None or message.subtype in person_subtypes
