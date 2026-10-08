"""Collecting the LinkedIn conversations.

LinkedIn hands back the member's whole message archive rather than a window, so
the window is applied here: a thread is kept when at least one of its messages
falls inside it, and then the **whole** thread is stored, because a status
cannot be judged from half a conversation.

LinkedIn is optional. Without the owner's profile address or without a key the
collector reads nothing and reports "not configured", which is not a failure:
nobody is told to fix a source they never set up.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from itertools import zip_longest

from pydantic import SecretStr

from tracker.domain.enums import Channel, Direction
from tracker.domain.prefilter import LinkedInThreadEvidence, judge_linkedin_thread
from tracker.domain.rules import RulePack
from tracker.infrastructure.linkedin.client import LinkedInSnapshotClient
from tracker.infrastructure.linkedin.parser import (
    SnapshotMessage,
    normalise_profile_url,
    parse_rows,
)
from tracker.repositories import Repositories
from tracker.services.collection.models import (
    CollectionReport,
    RawConversation,
    RawMessage,
    RawParticipant,
    SaveStep,
)
from tracker.services.collection.window import last_successful_run_at, window_start
from tracker.services.collection.writer import ConversationWriter
from tracker.services.identity.matcher import IdentityMatcher
from tracker.shared.clock import Clock
from tracker.shared.config import Settings
from tracker.shared.constants.collection import GROUP_SUBJECT_PREFIX, LINKEDIN_OVERLAP_DAYS
from tracker.shared.logging import get_logger

_log = get_logger(__name__)


class LinkedInCollector:
    """Reads the LinkedIn archive and stores the threads it touches."""

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
        """Read LinkedIn and store what falls inside the window.

        Args:
            since: An explicit start the owner asked for, which beats the run log.

        Returns:
            What the run found and wrote, or a "not configured" report when
            LinkedIn is not set up — without a single request being made.

        Raises:
            SourceAuthError: If LinkedIn rejected the key.
            SourceUnavailableError: If LinkedIn could not be reached.
        """
        return asyncio.run(self.read(since=since))()

    async def read(self, *, since: datetime | None = None) -> SaveStep:
        """Read the archive, and hand back the step that stores it.

        Args:
            since: An explicit start the owner asked for, which beats the run log.

        Returns:
            The step that stores what was read. When LinkedIn is not set up it
            only reports "not configured", and no request was made.

        Raises:
            SourceAuthError: If LinkedIn rejected the key.
            SourceUnavailableError: If LinkedIn could not be reached.
        """
        profile = self._settings.owner_linkedin_profile_url
        token = self._settings.linkedin_access_token
        if profile is None or token is None:
            _log.info("linkedin_not_configured")
            return lambda: CollectionReport(channel=Channel.LINKEDIN, not_configured=True)
        start = window_start(
            self._clock,
            last_run_at=last_successful_run_at(self._repositories),
            since=since,
            overlap_days=LINKEDIN_OVERLAP_DAYS,
        )
        messages = await _read_archive(token)
        owner = normalise_profile_url(profile)
        return lambda: self._store(self._build(messages, start, owner), _folders_of(messages))

    def _build(
        self,
        messages: Sequence[SnapshotMessage],
        start: datetime,
        owner: str,
    ) -> list[RawConversation]:
        """Group messages into threads and judge each one.

        Args:
            messages: Every archived message.
            start: Earliest moment that makes a thread worth keeping.
            owner: The owner's normalised profile link.

        Returns:
            One entry per thread touched by the window.
        """
        threads: dict[str, list[SnapshotMessage]] = defaultdict(list)
        for message in messages:
            threads[message.conversation_id].append(message)
        return [
            self._thread(conversation_id, sorted(items, key=lambda item: item.sent_at), owner)
            for conversation_id, items in threads.items()
            if any(item.sent_at >= start for item in items)
        ]

    def _thread(
        self,
        conversation_id: str,
        messages: list[SnapshotMessage],
        owner: str,
    ) -> RawConversation:
        """Turn one group of archived messages into a thread.

        Args:
            conversation_id: LinkedIn's identifier for the thread.
            messages: Its messages, oldest first.
            owner: The owner's normalised profile link.

        Returns:
            The thread, with the sponsored-message rule already applied.
        """
        has_owner_message = any(message.sender_profile_url == owner for message in messages)
        relevance = judge_linkedin_thread(
            LinkedInThreadEvidence(
                folders=tuple({message.folder for message in messages if message.folder}),
                has_owner_message=has_owner_message,
            )
        )
        participants = _participants(messages, owner)
        return RawConversation(
            channel=Channel.LINKEDIN,
            source_conversation_id=conversation_id,
            subject=_subject(messages, len(participants)),
            relevance=relevance,
            participants=participants,
            messages=tuple(
                RawMessage(
                    source_message_id=message.message_id,
                    sent_at=message.sent_at,
                    direction=(
                        Direction.OUTBOUND
                        if message.sender_profile_url == owner
                        else Direction.INBOUND
                    ),
                    sender_identifier=message.sender_profile_url or None,
                    body=message.content,
                )
                for message in messages
            ),
        )

    def _store(
        self,
        conversations: list[RawConversation],
        folders: tuple[str, ...],
    ) -> CollectionReport:
        """Match the people, write everything, and report the counts.

        Args:
            conversations: The threads to store.
            folders: Distinct folder values seen, for the advert rule.

        Returns:
            What the run found and wrote.
        """
        participants = [
            participant
            for conversation in conversations
            if not conversation.is_noise
            for participant in conversation.participants
        ]
        matched = self._matcher.resolve(participants)
        counts = self._writer.write(Channel.LINKEDIN, conversations, matched.person_by_identity)
        _log.info("linkedin_collected", conversations=len(conversations))
        return CollectionReport(
            channel=Channel.LINKEDIN,
            conversations_found=len(conversations),
            conversations_new=counts.conversations_new,
            conversations_noise=sum(1 for item in conversations if item.is_noise),
            messages_found=counts.messages_found,
            messages_new=counts.messages_new,
            people_new=matched.people_created,
            review_items_new=matched.review_items_created,
            folders_seen=folders,
        )


async def _read_archive(token: SecretStr) -> list[SnapshotMessage]:
    """Read and parse the whole archive.

    Args:
        token: The LinkedIn key.

    Returns:
        Every archived message LinkedIn returned.
    """
    async with LinkedInSnapshotClient(token) as client:
        rows = [row async for row in client.inbox_rows()]
    return list(parse_rows(rows))


def _participants(messages: Sequence[SnapshotMessage], owner: str) -> tuple[RawParticipant, ...]:
    """List everybody in a thread except the owner.

    Args:
        messages: The thread's messages.
        owner: The owner's normalised profile link.

    Returns:
        One participant per distinct profile link, first known spelling winning.
    """
    found: dict[str, RawParticipant] = {}
    for message in messages:
        pairs = [(message.sender_profile_url, message.sender_name)]
        # The parser leaves the names out when they do not line up with the
        # links, so every link is kept even when its name is unknown.
        pairs.extend(
            zip_longest(message.recipient_profile_urls, message.recipient_names, fillvalue="")
        )
        for url, name in pairs:
            if not url or url == owner:
                continue
            # A name left out of one message is filled in by a later one, such
            # as the person's own reply, instead of staying blank for good.
            known = found.get(url)
            if known is None or (not known.display_name and name):
                found[url] = RawParticipant(
                    channel=Channel.LINKEDIN, identifier=url, display_name=name
                )
    return tuple(found.values())


def _subject(messages: Sequence[SnapshotMessage], participant_count: int) -> str | None:
    """Work out a thread's subject.

    Args:
        messages: The thread's messages, oldest first.
        participant_count: How many people other than the owner are in it.

    Returns:
        The thread title, marked when it is a group conversation, or ``None``.
    """
    title = next(
        (message.conversation_title for message in messages if message.conversation_title),
        "",
    ) or next((message.subject for message in messages if message.subject), "")
    if not title:
        return None
    if participant_count > 1:
        return f"{GROUP_SUBJECT_PREFIX} {title}"
    return title


def _folders_of(messages: Sequence[SnapshotMessage]) -> tuple[str, ...]:
    """List the distinct folder values the archive used.

    LinkedIn does not document them, so the owner can print them and the advert
    rule can be corrected against the real values. Folder names carry no message
    text, so they are safe to show.
    """
    return tuple(sorted({message.folder for message in messages if message.folder}))
