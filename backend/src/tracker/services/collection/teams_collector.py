"""Collecting Microsoft Teams chats.

Every one-to-one or group chat in which somebody wrote inside the window
becomes a thread on the Teams channel. Its people are filed under their e-mail
address, on the e-mail channel, so a Teams chat with Hanna joins Hanna's e-mail
record; somebody Graph gives no address for is filed under their Teams
directory identifier instead.

Only the messages inside the window are read: the chat's earlier ones were
stored by earlier runs, and the writer keeps what it stored before. A chat is
read newest first and the read stops at the window's start, so a long chat
costs one request when nothing new happened in it.

Teams is optional, and it is a sign-in of its own (a work or school account)
next to Outlook's. Without it the collector reads nothing and reports "not
configured", which is not a failure.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from tracker.domain.enums import Channel, Direction, Relevance, RunStep
from tracker.domain.rules import RulePack
from tracker.infrastructure.microsoft.auth import MicrosoftAuthenticator
from tracker.infrastructure.microsoft.teams import (
    TeamsChat,
    TeamsChats,
    TeamsMember,
    TeamsMessage,
)
from tracker.infrastructure.secret_store import SecretStore
from tracker.repositories import Repositories
from tracker.services.collection.models import (
    CollectionReport,
    RawConversation,
    RawMessage,
    RawParticipant,
    SaveStep,
)
from tracker.services.collection.window import last_collected_at, window_start
from tracker.services.collection.writer import ConversationWriter
from tracker.services.identity.matcher import IdentityMatcher
from tracker.shared.clock import Clock
from tracker.shared.concurrency import gather_all
from tracker.shared.config import Settings
from tracker.shared.constants.collection import GROUP_SUBJECT_PREFIX
from tracker.shared.logging import get_logger

_log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class _ChatRead:
    """One chat and the messages read from it."""

    chat: TeamsChat
    messages: tuple[TeamsMessage, ...]


class TeamsCollector:
    """Reads the Teams chats and stores the ones written in since the window's start."""

    def __init__(
        self,
        repositories: Repositories,
        settings: Settings,
        clock: Clock,
        rules: RulePack,
    ) -> None:
        """Bind the collector to the database, the configuration and a clock.

        Args:
            repositories: The repository container.
            settings: The process configuration.
            clock: Supplies the current instant.
            rules: The owner's collection rules, which the matcher uses.
        """
        self._repositories = repositories
        self._settings = settings
        self._clock = clock
        self._matcher = IdentityMatcher(repositories, rules)
        self._writer = ConversationWriter(repositories)

    def collect(self, *, since: datetime | None = None) -> CollectionReport:
        """Read the Teams chats and store what falls inside the window.

        Args:
            since: An explicit start the owner asked for, which beats the run log.

        Returns:
            What the run found and wrote, or a "not configured" report.

        Raises:
            SourceAuthError: If nobody signed in, or Microsoft refused.
            SourceUnavailableError: If Teams could not be reached.
        """
        return asyncio.run(self.read(since=since))()

    async def read(self, *, since: datetime | None = None) -> SaveStep:
        """Read the chats, and hand back the step that stores them.

        Args:
            since: An explicit start the owner asked for, which beats the run log.

        Returns:
            The step that stores the chats. When Teams is not set up it only
            reports "not configured", and no request was made.

        Raises:
            SourceAuthError: If nobody signed in, or Microsoft refused.
            SourceUnavailableError: If Teams could not be reached.
        """
        if not self._settings.teams_enabled:
            _log.info("teams_not_configured")
            return lambda: CollectionReport(channel=Channel.TEAMS, not_configured=True)
        start = window_start(
            self._clock,
            last_run_at=last_collected_at(self._repositories, RunStep.COLLECT_TEAMS),
            since=since,
        )
        owner, reads = await self._read_chats(start)
        _log.info("teams_scanned", chats=len(reads))
        return lambda: self._store([thread for read in reads if (thread := _thread(read, owner))])

    async def _read_chats(self, start: datetime) -> tuple[TeamsMember, list[_ChatRead]]:
        """Read who signed in, the chats, and each touched chat's new messages."""
        store = SecretStore(
            self._repositories.app_secrets,
            self._settings.token_encryption_key,
            self._clock,
        )
        authenticator = MicrosoftAuthenticator.for_teams(store, self._clock, self._settings)
        async with authenticator, TeamsChats(authenticator) as teams:
            owner = await teams.signed_in_user()
            chats = [chat for chat in await teams.list_chats() if chat.touched_since(start)]
            messages = await gather_all(teams.messages_since(chat.chat_id, start) for chat in chats)
        return owner, [
            _ChatRead(chat, tuple(found)) for chat, found in zip(chats, messages, strict=True)
        ]

    def _store(self, conversations: list[RawConversation]) -> CollectionReport:
        """Match the people, write everything, and report the counts."""
        participants = [
            participant
            for conversation in conversations
            for participant in conversation.participants
        ]
        matched = self._matcher.resolve(participants)
        counts = self._writer.write(Channel.TEAMS, conversations, matched.person_by_identity)
        _log.info("teams_collected", conversations=len(conversations))
        return CollectionReport(
            channel=Channel.TEAMS,
            conversations_found=len(conversations),
            conversations_new=counts.conversations_new,
            messages_found=counts.messages_found,
            messages_new=counts.messages_new,
            people_new=matched.people_created,
            review_items_new=matched.review_items_created,
        )


def _thread(read: _ChatRead, owner: TeamsMember) -> RawConversation | None:
    """Turn one chat into a thread, or ``None`` when nobody else is in it or nothing new was said.

    Args:
        read: The chat and its messages inside the window.
        owner: Who signed in.

    Returns:
        The thread, left for the assessment to judge.
    """
    people = _others(read, owner)
    if not read.messages or not people:
        return None
    participants = tuple(_participant(member) for member in people)
    addresses = {member.user_id: _identifier(member) for member in (*read.chat.members, *people)}
    return RawConversation(
        channel=Channel.TEAMS,
        source_conversation_id=read.chat.chat_id,
        subject=_subject(read.chat, people),
        relevance=Relevance.UNSURE,
        participants=participants,
        messages=tuple(
            RawMessage(
                source_message_id=message.message_id,
                sent_at=message.sent_at,
                direction=(
                    Direction.OUTBOUND if message.sender_id == owner.user_id else Direction.INBOUND
                ),
                sender_identifier=addresses.get(message.sender_id, message.sender_id),
                body=message.text,
            )
            for message in read.messages
        ),
    )


def _others(read: _ChatRead, owner: TeamsMember) -> tuple[TeamsMember, ...]:
    """Everybody in a chat but the owner: its members, then anyone who wrote but left."""
    found: dict[str, TeamsMember] = {}
    for member in read.chat.members:
        found.setdefault(member.user_id, member)
    for message in read.messages:
        found.setdefault(
            message.sender_id,
            TeamsMember(user_id=message.sender_id, name=message.sender_name, email=""),
        )
    found.pop(owner.user_id, None)
    return tuple(
        member for member in found.values() if not owner.email or member.email != owner.email
    )


def _participant(member: TeamsMember) -> RawParticipant:
    """File a person under their address when Graph gives one, else their Teams identifier."""
    if member.email:
        return RawParticipant(
            channel=Channel.EMAIL, identifier=member.email, display_name=member.name
        )
    return RawParticipant(
        channel=Channel.TEAMS, identifier=member.user_id, display_name=member.name
    )


def _identifier(member: TeamsMember) -> str:
    """The identifier a message from this person is recorded with."""
    return member.email or member.user_id


def _subject(chat: TeamsChat, people: Sequence[TeamsMember]) -> str | None:
    """A chat's name, marked when it is a group; a one-to-one chat without a name has none."""
    if len(people) <= 1:
        return chat.topic or None
    title = chat.topic or ", ".join(member.name for member in people if member.name)
    return f"{GROUP_SUBJECT_PREFIX} {title}".strip()
