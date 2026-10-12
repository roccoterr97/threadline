"""Turning one Slack workspace's direct messages into collected threads.

One conversation is one thread. Its people are everybody in it except the
owner, bots, apps, Slackbot and removed accounts; a conversation left with
nobody is not a conversation and is skipped. A message's direction is whether
the token's own user wrote it.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime

from tracker.domain.enums import Channel, Direction, Relevance
from tracker.domain.slack import (
    SlackConversation,
    SlackIdentity,
    SlackMessage,
    SlackUser,
    is_person_message,
)
from tracker.domain.slack_markup import mentioned_users, plain_text
from tracker.services.collection.models import RawConversation, RawMessage, RawParticipant
from tracker.services.collection.slack_workspaces import SlackReader
from tracker.shared.constants.collection import GROUP_SUBJECT_PREFIX
from tracker.shared.constants.slack import (
    SLACK_FILE_PLACEHOLDER,
    SLACK_PERSON_SUBTYPES,
    SLACK_UNKNOWN_PERSON,
    SLACKBOT_USER_ID,
)
from tracker.shared.errors import SourceRequestRejectedError
from tracker.shared.logging import get_logger

_log = get_logger(__name__)


class SlackWorkspace:
    """Reads one workspace's direct messages into threads, looking each person up once."""

    def __init__(
        self, slack: SlackReader, me: SlackIdentity, owner_addresses: frozenset[str]
    ) -> None:
        """Bind the reader to an open workspace and its owner.

        Args:
            slack: The open workspace.
            me: Whose token it is: their messages are the owner's.
            owner_addresses: The owner's own e-mail addresses, never a contact.
        """
        self._slack = slack
        self._me = me
        self._owner_addresses = owner_addresses
        self._users: dict[str, SlackUser] = {}

    async def threads(self, start: datetime) -> list[RawConversation]:
        """Read every direct message with something inside the window.

        Args:
            start: The earliest moment read.

        Returns:
            One thread per conversation that has a person in it and a message
            from a person inside the window.
        """
        found: list[RawConversation] = []
        for conversation in await self._slack.direct_conversations():
            if _never_a_person(conversation):
                continue
            thread = await self._thread(conversation, start)
            if thread is not None:
                found.append(thread)
        _log.info("slack_workspace_read", threads=len(found))
        return found

    async def _thread(
        self, conversation: SlackConversation, start: datetime
    ) -> RawConversation | None:
        """Read one conversation; ``None`` when nothing in it is worth a thread."""
        try:
            messages = await self._messages(conversation.channel_id, start)
            if not messages:
                return None
            people = await self._people(conversation)
        except SourceRequestRejectedError as error:
            # One conversation Slack will not read (such as one closed since it
            # was listed) must not cost the rest of the workspace.
            _log.warning("slack_conversation_skipped", code=error.code)
            return None
        authors = {person.user_id for person in people} | {self._me.user_id}
        kept = [message for message in messages if message.user_id in authors]
        if not people or not kept:
            return None
        return await self._build(conversation, people, kept)

    async def _messages(self, channel_id: str, start: datetime) -> list[SlackMessage]:
        """Read a conversation's messages in the window, thread replies included, oldest first."""
        top = await self._slack.history(channel_id, start)
        replies: list[SlackMessage] = []
        for message in top:
            if message.reply_count:
                replies.extend(await self._slack.replies(channel_id, message.ts, start))
        everything = {message.ts: message for message in (*top, *replies)}
        persons = (
            message
            for message in everything.values()
            if is_person_message(message, SLACK_PERSON_SUBTYPES)
        )
        return sorted(persons, key=lambda message: message.sent_at)

    async def _people(self, conversation: SlackConversation) -> list[SlackUser]:
        """Everybody in a conversation except the owner, bots and removed accounts."""
        if conversation.is_group:
            ids = await self._slack.members(conversation.channel_id)
        else:
            ids = [conversation.other_user_id] if conversation.other_user_id else []
        people = [await self._user(user_id) for user_id in ids if user_id != self._me.user_id]
        return [
            person
            for person in people
            if person.is_person and person.email not in self._owner_addresses
        ]

    async def _user(self, user_id: str) -> SlackUser:
        """Look an account up once; one Slack will not describe is known by its identifier."""
        known = self._users.get(user_id)
        if known is not None:
            return known
        try:
            user = await self._slack.user(user_id)
        except SourceRequestRejectedError as error:
            _log.warning("slack_user_unknown", code=error.code)
            user = SlackUser(user_id=user_id, name=user_id, email=None)
        self._users[user_id] = user
        return user

    async def _build(
        self,
        conversation: SlackConversation,
        people: Sequence[SlackUser],
        messages: Sequence[SlackMessage],
    ) -> RawConversation:
        """Put one conversation's thread together."""
        names = await self._names(messages)
        participants = tuple(_participant(person) for person in people)
        identifiers = {person.user_id: _identifier(person) for person in people}
        return RawConversation(
            channel=Channel.SLACK,
            source_conversation_id=conversation.channel_id,
            subject=_subject(self._me.team_name, group=len(participants) > 1),
            relevance=Relevance.UNSURE,
            participants=participants,
            messages=tuple(self._message(message, names, identifiers) for message in messages),
        )

    async def _names(self, messages: Iterable[SlackMessage]) -> dict[str, str]:
        """The names of everybody the messages mention, for spelling mentions out."""
        mentioned = {user_id for message in messages for user_id in mentioned_users(message.text)}
        return {user_id: (await self._user(user_id)).name for user_id in sorted(mentioned)}

    def _message(
        self, message: SlackMessage, names: dict[str, str], identifiers: dict[str, str]
    ) -> RawMessage:
        """Turn one Slack message into a collected one, its markup spelled out."""
        author = message.user_id or ""
        return RawMessage(
            source_message_id=message.ts,
            sent_at=message.sent_at,
            direction=Direction.OUTBOUND if author == self._me.user_id else Direction.INBOUND,
            sender_identifier=identifiers.get(author, author) or None,
            body=_body(message, names),
        )


def _never_a_person(conversation: SlackConversation) -> bool:
    """Whether a direct message is with Slackbot or a removed account, before reading it."""
    if conversation.is_group:
        return False
    return conversation.other_user_deleted or conversation.other_user_id in {
        None,
        SLACKBOT_USER_ID,
    }


def _participant(person: SlackUser) -> RawParticipant:
    """File a person by e-mail address when Slack shares it, else by their Slack identifier.

    An e-mail identity is what the matcher joins across sources, so a Slack
    message from somebody already known by e-mail lands on their record.
    """
    channel = Channel.EMAIL if person.email else Channel.SLACK
    return RawParticipant(channel=channel, identifier=_identifier(person), display_name=person.name)


def _identifier(person: SlackUser) -> str:
    """The identifier a person is filed under."""
    return person.email or person.user_id


def _subject(team_name: str, *, group: bool) -> str:
    """Name a Slack thread after its workspace, marking a group conversation."""
    subject = f"Slack · {team_name}"
    return f"{GROUP_SUBJECT_PREFIX} {subject}" if group else subject


def _body(message: SlackMessage, names: dict[str, str]) -> str:
    """The message as plain text; a message holding only files names them."""
    text = plain_text(message.text, names, SLACK_UNKNOWN_PERSON)
    files = [SLACK_FILE_PLACEHOLDER.format(name=name) for name in message.file_names]
    return "\n".join(part for part in (text, *files) if part)
