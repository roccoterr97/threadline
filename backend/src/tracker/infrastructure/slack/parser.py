"""Turning Slack's JSON answers into the records in :mod:`tracker.domain.slack`.

Slack's answers are loose: fields are left out rather than sent empty. Every
reader here takes what is there and falls back to an empty value otherwise.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from tracker.domain.slack import SlackConversation, SlackIdentity, SlackMessage, SlackUser
from tracker.shared.constants.slack import SLACKBOT_USER_ID


def identity_from(payload: dict[str, Any]) -> SlackIdentity:
    """Read ``auth.test``'s answer.

    Args:
        payload: The answer, already checked to be ``ok``.

    Returns:
        Who the token belongs to.
    """
    return SlackIdentity(
        user_id=str(payload.get("user_id") or ""),
        team_id=str(payload.get("team_id") or ""),
        team_name=str(payload.get("team") or "Slack"),
    )


def conversation_from(item: dict[str, Any]) -> SlackConversation:
    """Read one conversation of ``users.conversations``.

    Args:
        item: One entry of its ``channels`` list.

    Returns:
        The conversation.
    """
    is_group = bool(item.get("is_mpim"))
    other = item.get("user")
    return SlackConversation(
        channel_id=str(item.get("id") or ""),
        is_group=is_group,
        other_user_id=str(other) if other and not is_group else None,
        other_user_deleted=bool(item.get("is_user_deleted")),
    )


def message_from(item: dict[str, Any]) -> SlackMessage:
    """Read one message of ``conversations.history`` or ``conversations.replies``.

    Args:
        item: One entry of its ``messages`` list.

    Returns:
        The message.
    """
    ts = str(item.get("ts") or "0")
    user = item.get("user")
    files = item.get("files") or []
    return SlackMessage(
        ts=ts,
        sent_at=sent_at(ts),
        user_id=str(user) if user else None,
        text=str(item.get("text") or ""),
        from_bot=bool(item.get("bot_id")) or user == SLACKBOT_USER_ID,
        subtype=str(item["subtype"]) if item.get("subtype") else None,
        reply_count=int(item.get("reply_count") or 0),
        file_names=tuple(
            str(entry.get("name") or entry.get("title") or "file")
            for entry in files
            if isinstance(entry, dict)
        ),
    )


def user_from(item: dict[str, Any]) -> SlackUser:
    """Read ``users.info``'s ``user``.

    Args:
        item: The user object.

    Returns:
        The account, with the e-mail address when Slack shares it.
    """
    profile = item.get("profile") or {}
    user_id = str(item.get("id") or "")
    name = (
        profile.get("real_name")
        or item.get("real_name")
        or profile.get("display_name")
        or item.get("name")
        or user_id
    )
    email = profile.get("email")
    return SlackUser(
        user_id=user_id,
        name=str(name),
        email=str(email).strip().lower() if email else None,
        is_bot=bool(item.get("is_bot") or item.get("is_app_user")) or user_id == SLACKBOT_USER_ID,
        is_deleted=bool(item.get("deleted")),
    )


def sent_at(ts: str) -> datetime:
    """Turn Slack's ``ts`` (seconds since 1970, with a fraction) into a UTC moment.

    Args:
        ts: Slack's timestamp, such as ``1726650000.000200``.

    Returns:
        The moment, in UTC; the start of 1970 for a value that is not a number.
    """
    try:
        return datetime.fromtimestamp(float(ts), tz=UTC)
    except (ValueError, OverflowError, OSError):
        return datetime.fromtimestamp(0, tz=UTC)


def slack_ts(moment: datetime) -> str:
    """Turn a moment into Slack's ``ts`` form, for ``oldest``.

    Args:
        moment: An aware moment.

    Returns:
        Seconds since 1970, with six decimals.
    """
    return f"{moment.timestamp():.6f}"
