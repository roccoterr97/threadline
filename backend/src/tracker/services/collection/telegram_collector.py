"""Collecting the owner's one-to-one Telegram chats.

Telegram is read with the owner's own account, read-only: nothing is ever
sent and nothing is marked as read. Only private chats with real people are
kept; groups, channels, bots, Telegram's own notices and the owner's Saved
Messages are left out before any of their messages is read.

A chat counts when its newest message falls inside the window. It becomes one
thread, stored with its newest messages up to a fixed number, so the
assessment sees the conversation rather than its last line. A message keeps
its text; a photo, a voice message or a file is written as a short mark such
as ``[photo]``, and its content is never read.

Telegram is optional. Without the application's keys and a saved login the
collector reads nothing and reports "not configured", which is not a failure.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import datetime

from tracker.domain.enums import Channel, Direction, Relevance, RunStep
from tracker.domain.rules import RulePack
from tracker.domain.telegram import (
    TelegramAccount,
    TelegramApp,
    TelegramChat,
    TelegramMessage,
    display_name,
    is_person_chat,
    message_body,
)
from tracker.repositories import Repositories
from tracker.services.collection.models import (
    CollectionReport,
    RawConversation,
    RawMessage,
    RawParticipant,
    SaveStep,
)
from tracker.services.collection.telegram_reader import TelegramOpener, TelegramReader
from tracker.services.collection.window import last_collected_at, window_start
from tracker.services.collection.writer import ConversationWriter
from tracker.services.identity.matcher import IdentityMatcher
from tracker.shared.clock import Clock
from tracker.shared.config import Settings
from tracker.shared.constants.telegram import TELEGRAM_MAX_MESSAGES_PER_CHAT
from tracker.shared.logging import get_logger

_log = get_logger(__name__)

#: One chat as it was read: the chat, and its messages newest first.
_ReadChat = tuple[TelegramChat, Sequence[TelegramMessage]]


class TelegramCollector:
    """Reads the owner's private Telegram chats and stores the ones the window touches."""

    def __init__(
        self,
        repositories: Repositories,
        settings: Settings,
        clock: Clock,
        rules: RulePack,
        open_reader: TelegramOpener,
    ) -> None:
        """Bind the collector to the database, the configuration, a clock and Telegram.

        Args:
            repositories: The repository container.
            settings: The process configuration.
            clock: Supplies the current instant.
            rules: The owner's collection rules, which the matcher uses.
            open_reader: Opens a reader on the owner's account.
        """
        self._repositories = repositories
        self._settings = settings
        self._clock = clock
        self._open_reader = open_reader
        self._matcher = IdentityMatcher(repositories, rules)
        self._writer = ConversationWriter(repositories)

    def collect(self, *, since: datetime | None = None) -> CollectionReport:
        """Read Telegram and store what falls inside the window.

        Args:
            since: An explicit start the owner asked for, which beats the run log.

        Returns:
            What the run found and wrote, or a "not configured" report when
            Telegram is not set up — without a single request being made.

        Raises:
            SourceAuthError: If Telegram ended the saved login.
            SourceUnavailableError: If Telegram could not be reached, or asked
                for a longer pause than a run waits.
        """
        return asyncio.run(self.read(since=since))()

    async def read(self, *, since: datetime | None = None) -> SaveStep:
        """Read the chats the window touches, and hand back the step that stores them.

        Args:
            since: An explicit start the owner asked for, which beats the run log.

        Returns:
            The step that stores what was read. When Telegram is not set up it
            only reports "not configured", and no request was made.

        Raises:
            SourceAuthError: If Telegram ended the saved login.
            SourceUnavailableError: If Telegram could not be reached, or asked
                for a longer pause than a run waits.
        """
        account = telegram_account(self._settings)
        if account is None:
            _log.info("telegram_not_configured")
            return lambda: CollectionReport(channel=Channel.TELEGRAM, not_configured=True)
        start = window_start(
            self._clock,
            last_run_at=last_collected_at(self._repositories, RunStep.COLLECT_TELEGRAM),
            since=since,
        )
        async with self._open_reader(account) as reader:
            chats = await _read_chats(reader, start)
        _log.info("telegram_read", chats=len(chats))
        return lambda: self._store([_thread(chat, messages) for chat, messages in chats])

    def _store(self, conversations: list[RawConversation]) -> CollectionReport:
        """Match the people, write everything, and report the counts."""
        participants = [person for thread in conversations for person in thread.participants]
        matched = self._matcher.resolve(participants)
        counts = self._writer.write(Channel.TELEGRAM, conversations, matched.person_by_identity)
        _log.info("telegram_collected", conversations=len(conversations))
        return CollectionReport(
            channel=Channel.TELEGRAM,
            conversations_found=len(conversations),
            conversations_new=counts.conversations_new,
            messages_found=counts.messages_found,
            messages_new=counts.messages_new,
            people_new=matched.people_created,
            review_items_new=matched.review_items_created,
        )


def telegram_account(settings: Settings) -> TelegramAccount | None:
    """The owner's Telegram account from the settings.

    Args:
        settings: The process configuration.

    Returns:
        The application and saved login, or ``None`` when Telegram is not set up.
    """
    api_id = settings.telegram_api_id
    api_hash = settings.telegram_api_hash
    session = settings.telegram_session
    if api_id is None or api_hash is None or session is None:
        return None
    return TelegramAccount(app=TelegramApp(api_id, api_hash), session=session)


async def _read_chats(reader: TelegramReader, start: datetime) -> list[_ReadChat]:
    """Read every private chat with a person that has a message at or after ``start``.

    Chats are read one after another: Telegram asks a client that hurries to
    slow down, and a daily run has no need to.
    """
    read: list[_ReadChat] = []
    for chat in await reader.chats_since(start):
        if not is_person_chat(chat):
            continue
        messages = await reader.recent_messages(chat, TELEGRAM_MAX_MESSAGES_PER_CHAT)
        if any(message.sent_at >= start for message in messages):
            read.append((chat, messages))
    return read


def _thread(chat: TelegramChat, messages: Sequence[TelegramMessage]) -> RawConversation:
    """Turn one private chat into a thread filed under the person on the other side."""
    identifier = str(chat.chat_id)
    return RawConversation(
        channel=Channel.TELEGRAM,
        source_conversation_id=identifier,
        subject=None,
        relevance=Relevance.UNSURE,
        participants=(
            RawParticipant(
                channel=Channel.TELEGRAM, identifier=identifier, display_name=display_name(chat)
            ),
        ),
        messages=tuple(_message(message, identifier) for message in messages),
    )


def _message(message: TelegramMessage, sender: str) -> RawMessage:
    """Turn one Telegram message into a stored message, direction from who sent it."""
    return RawMessage(
        source_message_id=str(message.message_id),
        sent_at=message.sent_at,
        direction=Direction.OUTBOUND if message.outgoing else Direction.INBOUND,
        sender_identifier=None if message.outgoing else sender,
        body=message_body(message),
    )
