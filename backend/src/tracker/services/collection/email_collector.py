"""Collecting the conversations in the owner's mailboxes.

Every configured mailbox — Microsoft's over Graph, any other over IMAP — is read
through the same :class:`~tracker.services.collection.mailbox.MailboxReader`,
so grouping, the noise rules, shared-sender resolution and writing are one
piece of code whichever mailbox a thread came from.

Each mailbox is read in two passes so text Threadline will never keep is never
fetched: metadata for everything in the window, then whole threads and bodies
only for what the obvious-noise rules kept. A newsletter therefore ends up in
the database as an identifier, a date and the decision — no subject, no body.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime

from tracker.domain.enums import Channel, Direction, Relevance, RunStep
from tracker.domain.mail import MailMessage
from tracker.domain.prefilter import EmailThreadEvidence, is_relay_sender, judge_email_thread
from tracker.domain.relay import real_sender
from tracker.domain.rules import RulePack
from tracker.repositories import Repositories
from tracker.services.collection.mailbox import MailboxReader, MailboxSource
from tracker.services.collection.mailboxes import configured_mailboxes
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
from tracker.shared.errors import TrackerError
from tracker.shared.logging import get_logger

_log = get_logger(__name__)


class EmailCollector:
    """Reads the owner's mailboxes and stores the threads worth keeping."""

    def __init__(
        self,
        repositories: Repositories,
        settings: Settings,
        clock: Clock,
        rules: RulePack,
        sources: Sequence[MailboxSource] | None = None,
    ) -> None:
        """Bind the collector to the database, the configuration and a clock.

        Args:
            repositories: The repository container.
            settings: The process configuration.
            clock: Supplies the current instant.
            rules: The owner's collection rules.
            sources: The mailboxes to read; every configured one when omitted.
        """
        self._sources = tuple(
            configured_mailboxes(repositories, settings, clock) if sources is None else sources
        )
        self._repositories = repositories
        self._settings = settings
        self._clock = clock
        self._rules = rules
        self._owner_addresses = frozenset(settings.owner_email_addresses)
        self._matcher = IdentityMatcher(repositories, rules)
        self._writer = ConversationWriter(repositories)

    def collect(self, *, since: datetime | None = None) -> CollectionReport:
        """Read every mailbox and store what falls inside the window.

        One mailbox that cannot be read never stops the others: what the others
        found is stored first, then the first failure is raised so the run
        records the step as failed.

        Args:
            since: An explicit start the owner asked for, which beats the run log.

        Returns:
            What the run found and wrote, all mailboxes together.

        Raises:
            SourceAuthError: If a mailbox refused the saved sign-in or password.
            SourceUnavailableError: If a mailbox could not be reached.
        """
        return asyncio.run(self.read(since=since))()

    async def read(self, *, since: datetime | None = None) -> SaveStep:
        """Read every mailbox, and hand back the step that stores what was read.

        Args:
            since: An explicit start the owner asked for, which beats the run log.

        Returns:
            The step that stores the threads. When one mailbox could not be
            read, the step stores what the others found and then raises that
            mailbox's failure.

        Raises:
            SourceAuthError: If no mailbox could be read and the first one
                refused the saved sign-in or password.
            SourceUnavailableError: If no mailbox could be read and the first
                one could not be reached.
        """
        if not self._sources:
            _log.info("email_not_configured")
            return lambda: CollectionReport(channel=Channel.EMAIL, not_configured=True)
        start = window_start(
            self._clock,
            last_run_at=last_collected_at(self._repositories, RunStep.COLLECT_EMAIL),
            since=since,
        )
        conversations, failures = await self._read_all(start)
        if len(failures) == len(self._sources):
            raise failures[0]
        return lambda: self._save(conversations, failures)

    def _save(
        self, conversations: list[RawConversation], failures: list[TrackerError]
    ) -> CollectionReport:
        """Store what was read, then raise the failure of a mailbox that was not."""
        report = self._store(conversations)
        if failures:
            raise failures[0]
        return report

    async def _read_all(
        self, start: datetime
    ) -> tuple[list[RawConversation], list[TrackerError]]:
        """Read the mailboxes side by side, keeping what failed apart from what was read.

        Two mailboxes are two different services, so neither waits for the
        other; the threads still come back in the order the mailboxes are
        configured.

        Args:
            start: Earliest moment the metadata pass asks for.

        Returns:
            Every thread read, and the failure of each mailbox that was not.
        """
        outcomes = await gather_all(
            self._read_or_failure(source, start) for source in self._sources
        )
        conversations: list[RawConversation] = []
        failures: list[TrackerError] = []
        for outcome in outcomes:
            if isinstance(outcome, TrackerError):
                failures.append(outcome)
                continue
            conversations.extend(outcome)
        return conversations, failures

    async def _read_or_failure(
        self, source: MailboxSource, start: datetime
    ) -> list[RawConversation] | TrackerError:
        """Read one mailbox, handing back its failure rather than raising it.

        Args:
            source: The mailbox to open.
            start: Earliest moment the metadata pass asks for.

        Returns:
            The mailbox's threads, or why it could not be read.
        """
        try:
            return await self._read_mailbox(source, start)
        except TrackerError as error:
            _log.warning("mailbox_not_read", mailbox=source.kind.value, code=error.code)
            return error

    async def _read_mailbox(
        self, source: MailboxSource, start: datetime
    ) -> list[RawConversation]:
        """Run the metadata pass, then the body pass, on one mailbox.

        Args:
            source: The mailbox to open.
            start: Earliest moment the metadata pass asks for.

        Returns:
            One entry per thread touched by the window.
        """
        async with source.open() as mailbox:
            recent = await mailbox.list_messages_since(start)
            _log.info("mailbox_scanned", mailbox=source.kind.value, messages=len(recent))
            return await self._threads(mailbox, recent)

    async def _threads(
        self,
        mailbox: MailboxReader,
        recent: Sequence[MailMessage],
    ) -> list[RawConversation]:
        """Judge each thread, then read the kept ones in full.

        Args:
            mailbox: The reader to fetch whole threads and bodies with.
            recent: The metadata pass's result.

        Returns:
            One entry per thread.
        """
        grouped: dict[str, list[MailMessage]] = defaultdict(list)
        for message in recent:
            grouped[message.conversation_id].append(message)
        already_kept = self._already_kept(grouped)
        # Threads do not depend on each other, so they are asked for together;
        # each mailbox reader decides how many requests it lets through at once.
        return await gather_all(
            self._read_thread(
                mailbox, conversation_id, seen, already_kept=conversation_id in already_kept
            )
            for conversation_id, seen in grouped.items()
        )

    async def _read_thread(
        self,
        mailbox: MailboxReader,
        conversation_id: str,
        seen: Sequence[MailMessage],
        *,
        already_kept: bool,
    ) -> RawConversation:
        """Judge one thread and, when it is kept, read it in full.

        Args:
            mailbox: The reader to fetch the whole thread and its bodies with.
            conversation_id: The mailbox's identifier for the thread.
            seen: The thread's messages that fell inside the window.
            already_kept: Whether the database holds the thread as not noise.

        Returns:
            The thread; a noise thread carries no body.
        """
        relevance = judge_email_thread(self._evidence(seen), self._rules)
        if relevance is Relevance.NOISE and not already_kept:
            return self._thread(conversation_id, seen, relevance)
        whole = await mailbox.list_thread(conversation_id) or list(seen)
        # The window may hold only part of a thread. Judging a thread the
        # database already keeps on that slice alone can flip it to noise —
        # dropping its subject and erasing every stored body — when the
        # owner's own reply simply falls outside the window. Such a thread
        # is judged again on all of it.
        if relevance is Relevance.NOISE:
            relevance = judge_email_thread(self._evidence(whole), self._rules)
        if relevance is Relevance.NOISE:
            return self._thread(conversation_id, whole, relevance)
        return self._thread(conversation_id, await self._with_bodies(mailbox, whole), relevance)

    def _already_kept(self, grouped: dict[str, list[MailMessage]]) -> frozenset[str]:
        """Thread identifiers the database does not already hold as noise.

        Args:
            grouped: The window's messages, by thread.

        Returns:
            The identifiers worth re-reading in full before calling them noise.
        """
        stored = self._repositories.conversations.list_by_sources(
            Channel.EMAIL, tuple(grouped)
        )
        return frozenset(
            conversation.source_conversation_id
            for conversation in stored
            if conversation.relevance is not Relevance.NOISE
        )

    async def _with_bodies(
        self,
        mailbox: MailboxReader,
        messages: Sequence[MailMessage],
    ) -> list[MailMessage]:
        """Fetch the plain-text body of every message of a kept thread.

        The thread's bodies are asked for in one go, so each reader can fetch
        them the cheapest way it has.
        """
        bodies = await mailbox.fetch_bodies([message.message_id for message in messages])
        return [
            dataclasses.replace(message, body=body)
            for message, body in zip(messages, bodies, strict=True)
        ]

    def _evidence(self, messages: Sequence[MailMessage]) -> EmailThreadEvidence:
        """Gather what the obvious-noise rules need from a thread's metadata."""
        return EmailThreadEvidence(
            sender_addresses=tuple(
                message.sender_address
                for message in messages
                if message.sender_address and not self._is_owner_message(message)
            ),
            subjects=tuple(message.subject for message in messages if message.subject),
            has_list_unsubscribe=any(message.has_list_unsubscribe for message in messages),
            has_owner_message=any(self._is_owner_message(message) for message in messages),
            summary_subject_prefix=self._settings.summary_subject_prefix,
        )

    def _thread(
        self,
        conversation_id: str,
        messages: Sequence[MailMessage],
        relevance: Relevance,
    ) -> RawConversation:
        """Turn one group of mailbox messages into a thread."""
        ordered = sorted(messages, key=lambda message: message.sent_at)
        participants = self._participants(ordered)
        return RawConversation(
            channel=Channel.EMAIL,
            source_conversation_id=conversation_id,
            subject=_subject(ordered, len(participants)),
            relevance=relevance,
            participants=participants,
            messages=tuple(
                RawMessage(
                    source_message_id=message.message_id,
                    sent_at=message.sent_at,
                    direction=(
                        Direction.OUTBOUND
                        if self._is_owner_message(message)
                        else Direction.INBOUND
                    ),
                    sender_identifier=message.sender_address or None,
                    body=message.body,
                )
                for message in ordered
            ),
        )

    def _participants(self, messages: Sequence[MailMessage]) -> tuple[RawParticipant, ...]:
        """List everybody in a thread except the owner.

        A shared sender (a hiring system, a calendar, an e-signature service) is
        replaced by the person or company behind it; a shared address among the
        recipients names nobody and is left out.
        """
        found: dict[str, RawParticipant] = {}
        for message in messages:
            for participant in (self._sender_of(message), *self._recipients_of(message)):
                if participant is not None:
                    found.setdefault(participant.identifier, participant)
        return tuple(found.values())

    def _sender_of(self, message: MailMessage) -> RawParticipant | None:
        """The person behind a message's sender, or ``None`` for the owner."""
        address = message.sender_address
        if not address or self._is_owner_message(message):
            return None
        sender = real_sender(
            address,
            message.sender_name,
            message.reply_to,
            message.subject,
            self._is_owner,
            self._rules,
        )
        return RawParticipant(
            channel=Channel.EMAIL,
            identifier=sender.identifier,
            display_name=sender.display_name,
            organisation_name=sender.organisation_name,
        )

    def _recipients_of(self, message: MailMessage) -> list[RawParticipant]:
        """The recipients other than the owner and shared addresses."""
        return [
            RawParticipant(channel=Channel.EMAIL, identifier=address, display_name=name)
            for address, name in message.recipients
            if address and not self._is_owner(address) and not is_relay_sender(address, self._rules)
        ]

    def _is_owner(self, address: str) -> bool:
        """Whether an address is one of the owner's own."""
        return address.strip().lower() in self._owner_addresses

    def _is_owner_message(self, message: MailMessage) -> bool:
        """Whether the owner wrote a message: filed as sent, or from their own address."""
        return message.from_owner or self._is_owner(message.sender_address)

    def _store(self, conversations: list[RawConversation]) -> CollectionReport:
        """Match the people, write everything, and report the counts."""
        participants = [
            participant
            for conversation in conversations
            if not conversation.is_noise
            for participant in conversation.participants
        ]
        matched = self._matcher.resolve(participants)
        counts = self._writer.write(Channel.EMAIL, conversations, matched.person_by_identity)
        _log.info("email_collected", conversations=len(conversations))
        return CollectionReport(
            channel=Channel.EMAIL,
            conversations_found=len(conversations),
            conversations_new=counts.conversations_new,
            conversations_noise=sum(1 for item in conversations if item.is_noise),
            messages_found=counts.messages_found,
            messages_new=counts.messages_new,
            people_new=matched.people_created,
            review_items_new=matched.review_items_created,
        )


def _subject(messages: Sequence[MailMessage], participant_count: int) -> str | None:
    """Work out a thread's subject, marking group conversations."""
    title = next((message.subject for message in messages if message.subject), "")
    if not title:
        return None
    if participant_count > 1:
        return f"{GROUP_SUBJECT_PREFIX} {title}"
    return title

