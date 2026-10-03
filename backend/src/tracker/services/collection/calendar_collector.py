"""Collect the owner's Microsoft calendar as a third source.

An interview can be in the calendar with no e-mail about it left in the inbox,
so every meeting with somebody other than the owner becomes a thread on the
calendar channel, filed under the people in it. Those people are matched by
their e-mail address, so a meeting with Hanna joins Hanna's e-mail record.

What is never stored: the owner's own events with nobody else in them (flights,
the gym, blocked time) — not even as noise — and the description an organiser
typed into an invitation. The one exception is an entry the owner typed for an
interview no invitation came with ("Video interview - Sam and Acme"): it is
filed under the one person already on record at the company its title names,
or else under a record for that company (see :mod:`tracker.domain.own_meetings`).
Threadline writes each meeting's text itself, from the title, the time — in
the owner's time zone, labelled with it — the people and the owner's answer.

A meeting that moves or is cancelled gets a new message, dated when it changed,
so the assessment sees the change and "last contact" stays truthful.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, tzinfo
from typing import Final
from uuid import UUID

from tracker.domain.enums import Channel, Direction, Relevance
from tracker.domain.identity import name_from_address, organisation_key
from tracker.domain.linking import LinkCandidate, only_person_at
from tracker.domain.models import PersonIdentity
from tracker.domain.own_meetings import company_in_title, is_own_meeting, own_meeting_identifier
from tracker.domain.prefilter import is_relay_sender
from tracker.domain.relay import is_relay_identity
from tracker.domain.rules import RulePack
from tracker.infrastructure.microsoft.auth import MicrosoftAuthenticator
from tracker.infrastructure.microsoft.client import GraphEvent, GraphMailbox
from tracker.infrastructure.secret_store import SecretStore
from tracker.repositories import Repositories
from tracker.services.collection.models import (
    CollectionReport,
    RawConversation,
    RawMessage,
    RawParticipant,
    SaveStep,
)
from tracker.services.collection.writer import ConversationWriter
from tracker.services.identity.linker import link_candidates
from tracker.services.identity.matcher import IdentityMatcher
from tracker.shared.clock import Clock, zone_label
from tracker.shared.config import Settings
from tracker.shared.constants.collection import (
    CALENDAR_FUTURE_DAYS,
    CALENDAR_PAST_DAYS,
    GROUP_SUBJECT_PREFIX,
)
from tracker.shared.logging import get_logger

_log = get_logger(__name__)

#: How the owner's answer to an invitation is written in a meeting's text.
_RESPONSES: Final[dict[str, str]] = {
    "accepted": "accepted",
    "tentativelyAccepted": "said maybe",
    "declined": "declined",
    "organizer": "you organised it",
    "notResponded": "not answered yet",
    "none": "not answered yet",
}
_NO_ANSWER: Final[str] = "not answered yet"
_NO_TITLE: Final[str] = "(no title)"


class _PeopleOnRecord:
    """Everybody already stored, as the linking rules describe them.

    Read the first time an entry the owner typed asks who is at a company, and
    kept for the rest of one save: nothing is written between two events, so a
    second entry would read the same three tables to learn the same thing.
    """

    def __init__(self, repositories: Repositories, rules: RulePack) -> None:
        """Bind to the database and the owner's rules; nothing is read yet."""
        self._repositories = repositories
        self._rules = rules
        self._read: tuple[list[LinkCandidate], list[PersonIdentity]] | None = None

    def at_company(self, company: str) -> RawParticipant | None:
        """The one person already on record at a company, as a known identity.

        The company's hiring system or a recruiter may already have written
        ("Acme Hiring Team", Chloe at acmegroup.example): the meeting
        belongs on that line, not on a new record of its own.
        """
        if self._read is None:
            self._read = self._everybody()
        candidates, identities = self._read
        match = only_person_at(organisation_key(company), candidates)
        if match is None:
            return None
        own = [identity for identity in identities if identity.person_id == match.person_id]
        return _as_participant(own, self._rules)

    def _everybody(self) -> tuple[list[LinkCandidate], list[PersonIdentity]]:
        """Read the people who are not noise, and every identity, from the database."""
        people = [
            person
            for person in self._repositories.people.list_every()
            if person.relevance is not Relevance.NOISE
        ]
        identities = self._repositories.person_identities.list_every()
        organisations = self._repositories.organisations.list_every()
        return link_candidates(people, identities, organisations, self._rules), identities


class CalendarCollector:
    """Reads the owner's calendar and stores the meetings with other people."""

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
            rules: The owner's collection rules.
        """
        self._repositories = repositories
        self._settings = settings
        self._clock = clock
        self._rules = rules
        self._owner_addresses = frozenset(settings.owner_email_addresses)
        self._owner_names = _owner_names(settings)
        self._matcher = IdentityMatcher(repositories, rules)
        self._writer = ConversationWriter(repositories)

    def collect(self) -> CollectionReport:
        """Read the calendar around today and store the meetings with people.

        Returns:
            What the run found and wrote, or a "not configured" report when
            Outlook is not one of the owner's mailboxes.

        Raises:
            SourceAuthError: If nobody has signed in, or Microsoft refused.
            SourceUnavailableError: If the calendar could not be reached.
        """
        return asyncio.run(self.read())()

    async def read(self) -> SaveStep:
        """Read the calendar around today, and hand back the step that stores it.

        Returns:
            The step that stores the meetings. When Outlook is not one of the
            owner's mailboxes it only reports "not configured".

        Raises:
            SourceAuthError: If nobody has signed in, or Microsoft refused.
            SourceUnavailableError: If the calendar could not be reached.
        """
        if not self._settings.outlook_enabled:
            # The calendar is read from Outlook only; without it there is none.
            _log.info("calendar_not_configured")
            return lambda: CollectionReport(channel=Channel.CALENDAR, not_configured=True)
        now = self._clock.now()
        events = await self._events_between(
            now - timedelta(days=CALENDAR_PAST_DAYS),
            now + timedelta(days=CALENDAR_FUTURE_DAYS),
        )
        _log.info("calendar_scanned", events=len(events))
        return lambda: self._save(events, now)

    def _save(self, events: list[GraphEvent], now: datetime) -> CollectionReport:
        """Turn the events into threads and store them.

        This reads who the mail collector filed each shared calendar's
        invitations under, so it must run after the mail has been stored.
        """
        behind = self._people_behind_shared_calendars(events)
        on_record = _PeopleOnRecord(self._repositories, self._rules)
        threads: dict[str, RawConversation] = {}
        for event in events:
            thread = self._thread(event, now, behind, on_record)
            if thread is not None:
                threads[thread.source_conversation_id] = _merged(
                    threads.get(thread.source_conversation_id), thread
                )
        return self._store(list(threads.values()))

    async def _events_between(self, start: datetime, end: datetime) -> list[GraphEvent]:
        """Read every event between two moments."""
        store = SecretStore(
            self._repositories.app_secrets,
            self._settings.token_encryption_key,
            self._clock,
        )
        authenticator = MicrosoftAuthenticator.for_settings(store, self._clock, self._settings)
        async with authenticator, GraphMailbox(authenticator) as calendar:
            return await calendar.list_events(start, end)

    def _thread(
        self,
        event: GraphEvent,
        now: datetime,
        behind: dict[str, RawParticipant],
        on_record: _PeopleOnRecord,
    ) -> RawConversation | None:
        """Turn one event into a thread, or ``None`` when only the owner is in it."""
        participants = (
            self._participants(event)
            or tuple(
                {
                    behind[address].identifier: behind[address]
                    for address in _addresses(event)
                    if address in behind
                }.values()
            )
            or self._company_of_own_entry(event, on_record)
        )
        if not participants:
            return None
        title = event.subject or _NO_TITLE
        return RawConversation(
            channel=Channel.CALENDAR,
            source_conversation_id=event.ical_uid,
            subject=f"{GROUP_SUBJECT_PREFIX} {title}" if len(participants) > 1 else title,
            relevance=Relevance.UNSURE,
            participants=participants,
            meeting_at=None if event.is_cancelled else event.start,
            messages=(
                RawMessage(
                    source_message_id=f"{event.event_id}@{event.changed_at.isoformat()}",
                    sent_at=min(event.changed_at, now),
                    direction=Direction.OUTBOUND if event.is_organizer else Direction.INBOUND,
                    sender_identifier=event.organizer[0] or None,
                    body=describe(event, self._clock.zone),
                ),
            ),
        )

    def _participants(self, event: GraphEvent) -> tuple[RawParticipant, ...]:
        """Everybody in a meeting except the owner and shared calendar addresses."""
        found: dict[str, RawParticipant] = {}
        for address, name in (event.organizer, *event.attendees):
            if (
                not address
                or address in self._owner_addresses
                or is_relay_sender(address, self._rules)
            ):
                continue
            found.setdefault(
                address,
                RawParticipant(channel=Channel.EMAIL, identifier=address, display_name=name),
            )
        return tuple(found.values())

    def _company_of_own_entry(
        self, event: GraphEvent, on_record: _PeopleOnRecord
    ) -> tuple[RawParticipant, ...]:
        """The company a meeting entry the owner typed themselves is with, if any."""
        if (
            event.attendees
            or not event.is_organizer
            or not is_own_meeting(event.subject, self._rules)
        ):
            return ()
        company = company_in_title(event.subject, self._owner_names, self._rules)
        if company is None:
            return ()
        known = on_record.at_company(company)
        if known is not None:
            return (known,)
        return (
            RawParticipant(
                channel=Channel.EMAIL,
                identifier=own_meeting_identifier(company),
                display_name=company,
                organisation_name=company,
            ),
        )

    def _people_behind_shared_calendars(
        self,
        events: list[GraphEvent],
    ) -> dict[str, RawParticipant]:
        """Who a shared calendar stands for, learnt from the invitations it e-mailed.

        A company's interview calendar ("Interviews") organises a meeting whose
        only other attendee is the owner, so the event names nobody. The e-mail
        invitation from the same calendar was filed under the real person
        through its Reply-To (see :mod:`tracker.domain.relay`); that person is
        who the meeting is with.
        """
        shared = sorted(
            {
                address
                for event in events
                for address in _addresses(event)
                if is_relay_sender(address, self._rules)
            }
        )
        sent = self._repositories.messages.list_threads_from(shared)
        # One pair per message, so a thread of five invitations is named five
        # times: each thread is fetched once, and all of them together.
        threads = {
            thread.id: thread
            for thread in self._repositories.conversations.list_by_ids(
                list(dict.fromkeys(thread_id for thread_id, _ in sent))
            )
        }
        person_by_address: dict[str, UUID] = {}
        for thread_id, sender in sent:
            thread = threads.get(thread_id)
            if thread is not None and thread.person_id is not None:
                person_by_address.setdefault(sender, thread.person_id)
        return {
            address: participant
            for address, person_id in person_by_address.items()
            if (participant := self._email_identity_of(person_id)) is not None
        }

    def _email_identity_of(self, person_id: UUID) -> RawParticipant | None:
        """A person's own e-mail address, as a participant the matcher knows."""
        for identity in self._repositories.person_identities.list_for_person(person_id):
            if identity.channel is Channel.EMAIL and not is_relay_identity(
                identity.identifier, self._rules
            ):
                return RawParticipant(
                    channel=Channel.EMAIL,
                    identifier=identity.identifier,
                    display_name=identity.display_name or "",
                )
        return None

    def _store(self, threads: list[RawConversation]) -> CollectionReport:
        """Match the people, write the meetings, and report the counts."""
        participants = [person for thread in threads for person in thread.participants]
        matched = self._matcher.resolve(participants)
        counts = self._writer.write(Channel.CALENDAR, threads, matched.person_by_identity)
        _log.info("calendar_collected", meetings=len(threads))
        return CollectionReport(
            channel=Channel.CALENDAR,
            conversations_found=len(threads),
            conversations_new=counts.conversations_new,
            messages_found=counts.messages_found,
            messages_new=counts.messages_new,
            people_new=matched.people_created,
            review_items_new=matched.review_items_created,
        )


def describe(event: GraphEvent, zone: tzinfo) -> str:
    """Write a meeting's text from its fields, never from its description.

    Args:
        event: The calendar event.
        zone: The owner's time zone; the times are shown in it and labelled
            with its name, so "10:00" means ten o'clock where the owner is.

    Returns:
        A few plain lines: title, time, organiser, invitees, the owner's answer.
    """
    start = event.start.astimezone(zone)
    end = event.end.astimezone(zone)
    lines = [
        f"Meeting in your calendar: {event.subject or _NO_TITLE}",
        f"When: {start:%a %d %b %Y, %H:%M}–{end:%H:%M} ({zone_label(zone)})",
        f"Organiser: {_person(event.organizer)}",
        f"Invited: {', '.join(_person(entry) for entry in event.attendees) or 'nobody'}",
        f"Your answer: {_RESPONSES.get(event.response, _NO_ANSWER)}",
    ]
    if event.is_cancelled:
        lines.append("This meeting was cancelled.")
    return "\n".join(lines)


def _owner_names(settings: Settings) -> tuple[str, ...]:
    """The owner's own names, which an interview entry's title often repeats.

    The configured display name wins. Without one, the names are read from the
    owner's addresses — which works for ``sam.rivera@`` but not for ``jd123@``.
    """
    if settings.owner_display_name is not None:
        return (settings.owner_display_name,)
    return tuple(name for name in map(name_from_address, settings.owner_email_addresses) if name)


def _as_participant(identities: list[PersonIdentity], rules: RulePack) -> RawParticipant | None:
    """One person's identity the matcher already knows, a real address first."""
    ranked = sorted(
        identities,
        key=lambda identity: (
            identity.channel is not Channel.EMAIL,
            is_relay_identity(identity.identifier, rules),
        ),
    )
    if not ranked:
        return None
    chosen = ranked[0]
    return RawParticipant(
        channel=chosen.channel,
        identifier=chosen.identifier,
        display_name=chosen.display_name or "",
    )


def _addresses(event: GraphEvent) -> list[str]:
    """Every address on an event: the organiser first, then the invitees."""
    return [address for address, _ in (event.organizer, *event.attendees) if address]


def _person(entry: tuple[str, str]) -> str:
    """Write one ``(address, name)`` pair as "Name <address>"."""
    address, name = entry
    if name and name.lower() != address:
        return f"{name} <{address}>"
    return address or "unknown"


def _merged(existing: RawConversation | None, new: RawConversation) -> RawConversation:
    """Join two occurrences of one meeting into one thread."""
    if existing is None:
        return new
    people = {person.identifier: person for person in (*existing.participants, *new.participants)}
    return RawConversation(
        channel=existing.channel,
        source_conversation_id=existing.source_conversation_id,
        subject=existing.subject,
        relevance=existing.relevance,
        participants=tuple(people.values()),
        messages=(*existing.messages, *new.messages),
        meeting_at=max(
            (moment for moment in (existing.meeting_at, new.meeting_at) if moment is not None),
            default=None,
        ),
    )
