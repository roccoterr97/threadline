"""Collecting the owner's Slack direct messages, from one or several workspaces.

Every direct message and group direct message with a message inside the
window becomes one thread on the Slack channel. Slack Connect conversations
with people outside the workspace are direct messages too, so they come along.
Bots, apps, Slackbot and removed accounts are never a conversation.

Each person is filed under their e-mail address when Slack shares it, so a
Slack message joins that person's e-mail record; only without one is the
person known by their Slack user identifier.

Only the window is read, not a conversation's whole history: a direct message
can go back years, and reading all of it every time somebody writes would
spend the workspace's request allowance on what is already stored. The
replies in a thread are read when the message that starts it is inside the
window — direct messages rarely have threads, so that costs little.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Sequence
from datetime import datetime

from tracker.domain.enums import Channel, RunStep
from tracker.domain.rules import RulePack
from tracker.repositories import Repositories
from tracker.services.collection.models import CollectionReport, RawConversation, SaveStep
from tracker.services.collection.slack_threads import SlackWorkspace
from tracker.services.collection.slack_workspaces import SlackOpener, configured_workspaces
from tracker.services.collection.window import last_collected_at, window_start
from tracker.services.collection.writer import ConversationWriter
from tracker.services.identity.matcher import IdentityMatcher
from tracker.shared.clock import Clock
from tracker.shared.concurrency import gather_all
from tracker.shared.config import Settings
from tracker.shared.errors import TrackerError
from tracker.shared.logging import get_logger

_log = get_logger(__name__)


@dataclasses.dataclass(slots=True)
class _WorkspacesRead:
    """What reading every workspace came to, before anything is stored."""

    conversations: list[RawConversation] = dataclasses.field(default_factory=list)
    failures: list[TrackerError] = dataclasses.field(default_factory=list)


class SlackCollector:
    """Reads the owner's Slack workspaces and stores their direct messages."""

    def __init__(
        self,
        repositories: Repositories,
        settings: Settings,
        clock: Clock,
        rules: RulePack,
        workspaces: Sequence[SlackOpener] | None = None,
    ) -> None:
        """Bind the collector to the database, the configuration and a clock.

        Args:
            repositories: The repository container.
            settings: The process configuration.
            clock: Supplies the current instant.
            rules: The owner's collection rules, which the matcher uses.
            workspaces: The workspaces to read; every configured one when omitted.
        """
        self._workspaces = tuple(
            configured_workspaces(settings) if workspaces is None else workspaces
        )
        self._repositories = repositories
        self._clock = clock
        self._owner_addresses = frozenset(settings.owner_email_addresses)
        self._matcher = IdentityMatcher(repositories, rules)
        self._writer = ConversationWriter(repositories)

    def collect(self, *, since: datetime | None = None) -> CollectionReport:
        """Read every workspace and store what falls inside the window.

        One workspace that cannot be read never stops the others: what the
        others found is stored first, then why one was not read is raised.

        Args:
            since: An explicit start the owner asked for, which beats the run log.

        Returns:
            What the run found and wrote, all workspaces together.

        Raises:
            SlackTokenRefusedError: If Slack no longer accepts a saved token.
            SlackApprovalNeededError: If a workspace admin has not approved the app.
            SourceUnavailableError: If Slack could not be reached or asked to wait.
        """
        report = asyncio.run(self.read(since=since))()
        if report.problem is not None:
            raise report.problem
        return report

    async def read(self, *, since: datetime | None = None) -> SaveStep:
        """Read every workspace, and hand back the step that stores what was read.

        Args:
            since: An explicit start the owner asked for, which beats the run log.

        Returns:
            The step that stores the threads. When Slack is not set up it only
            reports "not configured", and no request was made. When one
            workspace could not be read, the step still stores the others and
            names why as the report's ``problem``.

        Raises:
            TrackerError: The first workspace's failure, when none could be read.
        """
        if not self._workspaces:
            _log.info("slack_not_configured")
            return lambda: CollectionReport(channel=Channel.SLACK, not_configured=True)
        start = window_start(
            self._clock,
            last_run_at=last_collected_at(self._repositories, RunStep.COLLECT_SLACK),
            since=since,
        )
        read = await self._read_all(start)
        if len(read.failures) == len(self._workspaces):
            raise read.failures[0]
        return lambda: self._save(read)

    async def _read_all(self, start: datetime) -> _WorkspacesRead:
        """Read the workspaces side by side: each has its own request allowance."""
        outcomes = await gather_all(
            self._read_or_failure(opener, start) for opener in self._workspaces
        )
        read = _WorkspacesRead()
        for outcome in outcomes:
            if isinstance(outcome, TrackerError):
                read.failures.append(outcome)
            else:
                read.conversations.extend(outcome)
        return read

    async def _read_or_failure(
        self, opener: SlackOpener, start: datetime
    ) -> list[RawConversation] | TrackerError:
        """Read one workspace, handing back its failure rather than raising it."""
        try:
            async with opener() as slack:
                workspace = SlackWorkspace(slack, await slack.who_am_i(), self._owner_addresses)
                return await workspace.threads(start)
        except TrackerError as error:
            _log.warning("slack_workspace_not_read", code=error.code)
            return error

    def _save(self, read: _WorkspacesRead) -> CollectionReport:
        """Store what was read, and name why a workspace was not read, if one was not."""
        report = self._store(_unique(read.conversations))
        problem = read.failures[0] if read.failures else None
        return dataclasses.replace(report, problem=problem)

    def _store(self, conversations: list[RawConversation]) -> CollectionReport:
        """Match the people, write everything, and report the counts."""
        participants = [
            participant
            for conversation in conversations
            for participant in conversation.participants
        ]
        matched = self._matcher.resolve(participants)
        counts = self._writer.write(Channel.SLACK, conversations, matched.person_by_identity)
        _log.info("slack_collected", conversations=len(conversations))
        return CollectionReport(
            channel=Channel.SLACK,
            conversations_found=len(conversations),
            conversations_new=counts.conversations_new,
            messages_found=counts.messages_found,
            messages_new=counts.messages_new,
            people_new=matched.people_created,
            review_items_new=matched.review_items_created,
        )


def _unique(conversations: list[RawConversation]) -> list[RawConversation]:
    """Keep one copy of a Slack Connect conversation seen from two of the owner's workspaces.

    Slack gives such a conversation one identifier everywhere, and the writer
    takes one row per identifier.
    """
    by_id: dict[str, RawConversation] = {}
    for conversation in conversations:
        by_id.setdefault(conversation.source_conversation_id, conversation)
    return list(by_id.values())
