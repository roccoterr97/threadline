"""One person per address, and one person across both channels when it is safe.

Every LinkedIn profile link and every e-mail address becomes exactly one
identity, owned by exactly one person. When a new identity's normalised name
already belongs to somebody on the *other* channel, and that name is unique on
both sides, the two are merged. Anything less certain creates a separate person
and a ``same_person`` question for the owner, because a wrong merge produces one
timeline made of two unrelated conversations and nobody can tell afterwards.

A non-free e-mail domain also names an organisation: ``someone@acme.example``
says the person works at Acme, while ``someone@gmail.com`` says nothing at all.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Final, Protocol
from uuid import UUID

from tracker.domain.enums import Channel, ReviewKind
from tracker.domain.identity import (
    could_be_the_same_person,
    email_domain,
    may_auto_merge,
    name_from_address,
    normalise_name,
    organisation_key,
    organisation_name_from_domain,
    shown_name_from_address,
)
from tracker.domain.models import Organisation, Person, PersonIdentity, ReviewItem
from tracker.domain.relay import is_relay_identity
from tracker.domain.rules import RulePack
from tracker.repositories import Repositories
from tracker.services.collection.models import RawParticipant
from tracker.shared.constants.pagination import MAX_PAGE_SIZE
from tracker.shared.logging import get_logger

#: Question shown to the owner when two identities might be one person.
SAME_PERSON_QUESTION: str = "Is {name} on {channel} the same person as {other} on {other_channel}?"

_log = get_logger(__name__)

#: Marks an organisation key built from a company name rather than a domain.
_NAME_KEY_PREFIX: Final[str] = "name:"


class _PageReader[RowT](Protocol):
    """A repository ``list`` method, seen from the paging helper."""

    def __call__(self, *, limit: int, offset: int) -> list[RowT]:
        """Return one page of rows."""
        ...


@dataclass(frozen=True, slots=True)
class MatchResult:
    """Who each collected identity belongs to.

    Attributes:
        person_by_identity: Person identifier for every participant key.
        people_created: How many people the run added.
        review_items_created: How many "same person?" questions it asked.
    """

    person_by_identity: dict[tuple[Channel, str], UUID] = field(default_factory=dict)
    people_created: int = 0
    review_items_created: int = 0


@dataclass(slots=True)
class _Pending:
    """Records built in memory before anything is written."""

    people: list[Person] = field(default_factory=list)
    identities: list[PersonIdentity] = field(default_factory=list)
    organisations: list[Organisation] = field(default_factory=list)
    review_items: list[ReviewItem] = field(default_factory=list)


class IdentityMatcher:
    """Turns collected participants into people, identities and organisations."""

    def __init__(self, repositories: Repositories, rules: RulePack) -> None:
        """Bind the matcher to the repositories it reads and writes.

        Args:
            repositories: The repository container.
            rules: The owner's collection rules, which say which addresses are
                shared systems rather than people.
        """
        self._repositories = repositories
        self._rules = rules

    def resolve(self, participants: list[RawParticipant]) -> MatchResult:
        """Find or create the person behind every participant.

        Args:
            participants: Everybody the collectors saw, duplicates allowed.

        Returns:
            The person behind each participant key, plus what was created.
        """
        unique = _deduplicate(participants)
        if not unique:
            return MatchResult()
        known = self._known_identities(unique)
        resolved: dict[tuple[Channel, str], UUID] = dict(known)
        pending = _Pending()
        index = _NameIndex(self._read_all_people(), self._read_all_identities())
        counts = _count_new_names(unique, known)
        organisations = self._organisations_for(unique, known, pending)
        for participant in unique:
            if participant.key in resolved:
                continue
            resolved[participant.key] = self._place(
                participant, index, counts, organisations, pending
            )
        self._write(pending)
        return MatchResult(
            person_by_identity=resolved,
            people_created=len(pending.people),
            review_items_created=len(pending.review_items),
        )

    def _place(
        self,
        participant: RawParticipant,
        index: _NameIndex,
        counts: dict[tuple[Channel, str], int],
        organisations: dict[str, UUID],
        pending: _Pending,
    ) -> UUID:
        """Attach one new identity to an existing person, or create one.

        Args:
            participant: The identity to place.
            index: Who is already known, by normalised name.
            counts: How many new identities share each normalised name per channel.
            organisations: Organisation identifier per e-mail domain.
            pending: Collects the records to write.

        Returns:
            The identifier of the person the identity now belongs to.
        """
        name = normalise_name(participant.display_name)
        candidates = index.on_other_channels(name, participant.channel)
        if name and may_auto_merge(
            matches_on_other_side=len(candidates),
            matches_on_this_side=counts.get((participant.channel, name), 1),
        ):
            person_id = candidates[0]
            pending.identities.append(_identity_of(participant, person_id))
            index.remember(name, participant.channel, person_id)
            return person_id
        person = _person_of(participant, organisations, self._rules)
        pending.people.append(person)
        pending.identities.append(_identity_of(participant, person.id))
        index.remember(name, participant.channel, person.id)
        if name and candidates:
            pending.review_items.append(_question(participant, person, candidates[0], index))
            return person.id
        # No display name to match on. Many senders set none, so the person is
        # recorded as their address and can never meet anyone. The part before
        # the "@" often still holds the name, which is enough to ask about —
        # never enough to merge on.
        suggested = self._suggested_match(participant, index, self._rules)
        if suggested is not None:
            pending.review_items.append(_question(participant, person, suggested, index))
        return person.id

    @staticmethod
    def _suggested_match(
        participant: RawParticipant,
        index: _NameIndex,
        rules: RulePack,
    ) -> UUID | None:
        """Find the one person an address-derived name could belong to.

        Args:
            participant: The identity being placed.
            index: Who is already known.
            rules: The owner's collection rules.

        Returns:
            That person's identifier, or ``None`` when the address suggests
            nothing usable or more than one person could fit.
        """
        if participant.channel is not Channel.EMAIL or is_relay_identity(
            participant.identifier, rules
        ):
            return None
        derived = name_from_address(participant.identifier)
        if not derived:
            return None
        candidates = index.plausibly_the_same(derived)
        return candidates[0] if len(candidates) == 1 else None

    def _known_identities(
        self,
        participants: list[RawParticipant],
    ) -> dict[tuple[Channel, str], UUID]:
        """Look up the participants that already have an identity row."""
        known: dict[tuple[Channel, str], UUID] = {}
        for channel in Channel:
            wanted = [item.identifier for item in participants if item.channel is channel]
            for identity in self._repositories.person_identities.list_by_identifiers(
                channel, wanted
            ):
                known[(identity.channel, identity.identifier)] = identity.person_id
        return known

    def _organisations_for(
        self,
        participants: list[RawParticipant],
        known: dict[tuple[Channel, str], UUID],
        pending: _Pending,
    ) -> dict[str, UUID]:
        """Find or create the organisation of every new participant.

        Args:
            participants: Everybody the collectors saw.
            known: Participants that already belong to somebody.
            pending: Collects the organisations to write.

        Returns:
            Organisation identifier per key (see :func:`_organisation_key_of`).
        """
        new = [item for item in participants if item.key not in known]
        return {
            **self._organisations_by_domain(new, pending),
            **self._organisations_by_name(new, pending),
        }

    def _organisations_by_domain(
        self,
        participants: list[RawParticipant],
        pending: _Pending,
    ) -> dict[str, UUID]:
        """One organisation per company e-mail domain, found or created."""
        domains = {
            key
            for participant in participants
            if participant.organisation_name is None
            for key in [_organisation_key_of(participant, self._rules)]
            if key
        }
        if not domains:
            return {}
        by_domain: dict[str, UUID] = {
            organisation.email_domain: organisation.id
            for organisation in self._repositories.organisations.list_by_email_domains(
                sorted(domains)
            )
            if organisation.email_domain
        }
        for domain in sorted(domains - by_domain.keys()):
            name = organisation_name_from_domain(domain)
            if name is None:
                continue
            organisation = Organisation(name=name, email_domain=domain)
            pending.organisations.append(organisation)
            by_domain[domain] = organisation.id
        return by_domain

    def _organisations_by_name(
        self,
        participants: list[RawParticipant],
        pending: _Pending,
    ) -> dict[str, UUID]:
        """One organisation per company a shared sender named, found or created.

        Matched on :func:`organisation_key`, so "Northwind AI" finds "NORTHWIND AI".
        """
        named = {
            _organisation_key_of(participant, self._rules): participant.organisation_name
            for participant in participants
            if participant.organisation_name
        }
        if not named:
            return {}
        by_key: dict[str, UUID] = {
            _NAME_KEY_PREFIX + organisation_key(organisation.name): organisation.id
            for organisation in read_every(self._repositories.organisations.list)
        }
        for key, name in sorted((key, name) for key, name in named.items() if key and name):
            if key in by_key:
                continue
            organisation = Organisation(name=name)
            pending.organisations.append(organisation)
            by_key[key] = organisation.id
        return by_key

    def _read_all_people(self) -> list[Person]:
        """Read every person, one page at a time."""
        return read_every(self._repositories.people.list)

    def _read_all_identities(self) -> list[PersonIdentity]:
        """Read every identity, one page at a time."""
        return read_every(self._repositories.person_identities.list)

    def _write(self, pending: _Pending) -> None:
        """Write the new records, parents before children."""
        self._repositories.organisations.bulk_upsert(pending.organisations)
        self._repositories.people.bulk_upsert(pending.people)
        self._repositories.person_identities.bulk_upsert(pending.identities)
        self._repositories.review_items.bulk_upsert(self._new_questions(pending.review_items))
        _log.info(
            "identities_resolved",
            people=len(pending.people),
            identities=len(pending.identities),
            organisations=len(pending.organisations),
            questions=len(pending.review_items),
        )

    def _new_questions(self, candidates: list[ReviewItem]) -> list[ReviewItem]:
        """Drop the questions the owner has already been asked.

        Args:
            candidates: The questions this run would like to ask.

        Returns:
            Only the pairs of people that have never been questioned.
        """
        if not candidates:
            return []
        asked = {
            (item.person_id, item.other_person_id)
            for item in self._repositories.review_items.list_by_kind(ReviewKind.SAME_PERSON)
        }
        return [item for item in candidates if (item.person_id, item.other_person_id) not in asked]


class _NameIndex:
    """Which people carry which normalised name, on which channel."""

    def __init__(self, people: list[Person], identities: list[PersonIdentity]) -> None:
        """Build the index from what the database already holds."""
        self._names: dict[UUID, str] = {
            person.id: normalise_name(person.full_name) for person in people
        }
        self._channels: dict[UUID, set[Channel]] = defaultdict(set)
        for identity in identities:
            self._channels[identity.person_id].add(identity.channel)
        self._by_name: dict[str, list[UUID]] = defaultdict(list)
        for person_id, name in self._names.items():
            if name:
                self._by_name[name].append(person_id)

    def on_other_channels(self, name: str, channel: Channel) -> list[UUID]:
        """List the people with this name who are known on a different channel.

        Args:
            name: The normalised name to look for.
            channel: The channel the new identity uses.

        Returns:
            The identifiers of the people who match, in insertion order.
        """
        if not name:
            return []
        return [
            person_id
            for person_id in self._by_name.get(name, [])
            if channel not in self._channels[person_id] and self._channels[person_id]
        ]

    def plausibly_the_same(self, derived: str) -> list[UUID]:
        """List the people an address-derived name could belong to.

        Unlike a match on two display names, this one does not require the
        other person to be on a different channel: the whole situation is that
        one record is a bare address and the other is a name, and they are
        often both e-mail — a work address and a personal one, or one record
        made from a display name and one from an address.

        Args:
            derived: The normalised name an address suggested.

        Returns:
            The identifiers of the people who could fit, in insertion order.
        """
        return [
            person_id
            for person_id, known in self._names.items()
            if known
            and "@" not in known
            and self._channels[person_id]
            and could_be_the_same_person(derived, known)
        ]

    def remember(self, name: str, channel: Channel, person_id: UUID) -> None:
        """Record a person this run has just created or extended.

        Args:
            name: The person's normalised name.
            channel: The channel the new identity uses.
            person_id: The person the identity belongs to.
        """
        self._channels[person_id].add(channel)
        if name and person_id not in self._by_name[name]:
            self._by_name[name].append(person_id)
            self._names[person_id] = name

    def name_of(self, person_id: UUID) -> str:
        """Return the normalised name of a known person, or an empty string."""
        return self._names.get(person_id, "")

    def channels_of(self, person_id: UUID) -> set[Channel]:
        """Return the channels a known person is reachable on."""
        return self._channels[person_id]


def _deduplicate(participants: list[RawParticipant]) -> list[RawParticipant]:
    """Keep one entry per participant key, the first spelling of the name winning."""
    unique: dict[tuple[Channel, str], RawParticipant] = {}
    for participant in participants:
        if not participant.identifier.strip():
            continue
        unique.setdefault(participant.key, participant)
    return list(unique.values())


def _count_new_names(
    participants: list[RawParticipant],
    known: dict[tuple[Channel, str], UUID],
) -> dict[tuple[Channel, str], int]:
    """Count how many *new* identities per channel share each normalised name."""
    counts: dict[tuple[Channel, str], int] = defaultdict(int)
    for participant in participants:
        if participant.key in known:
            continue
        name = normalise_name(participant.display_name)
        if name:
            counts[(participant.channel, name)] += 1
    return counts


def _person_of(
    participant: RawParticipant,
    organisations: dict[str, UUID],
    rules: RulePack,
) -> Person:
    """Build a new person from one identity."""
    return Person(
        full_name=participant.display_name.strip() or _name_from_identifier(participant, rules),
        organisation_id=organisations.get(_organisation_key_of(participant, rules) or ""),
    )


def _name_from_identifier(participant: RawParticipant, rules: RulePack) -> str:
    """The name to show for somebody whose source spelled none.

    A work address such as ``alessia.conti@quick-solve.example`` plainly spells
    one; anything else, including a shared sender's address, is shown as is.
    """
    if participant.channel is not Channel.EMAIL or is_relay_identity(
        participant.identifier, rules
    ):
        return participant.identifier
    return shown_name_from_address(participant.identifier) or participant.identifier


def _organisation_key_of(participant: RawParticipant, rules: RulePack) -> str | None:
    """How a participant's organisation is looked up.

    A company a shared sender named is keyed by its name; anybody else by the
    e-mail domain, when it is a company's. A shared system's own domain names
    no employer.
    """
    if participant.organisation_name:
        return _NAME_KEY_PREFIX + organisation_key(participant.organisation_name)
    if participant.channel is not Channel.EMAIL or is_relay_identity(
        participant.identifier, rules
    ):
        return None
    domain = email_domain(participant.identifier)
    return domain if domain and organisation_name_from_domain(domain) else None


def _identity_of(participant: RawParticipant, person_id: UUID) -> PersonIdentity:
    """Build the identity row for one participant."""
    return PersonIdentity(
        person_id=person_id,
        channel=participant.channel,
        identifier=participant.identifier,
        display_name=participant.display_name.strip() or None,
    )


def _question(
    participant: RawParticipant,
    person: Person,
    other_person_id: UUID,
    index: _NameIndex,
) -> ReviewItem:
    """Build the "same person?" question for an ambiguous match."""
    other_channels = sorted(channel.value for channel in index.channels_of(other_person_id))
    return ReviewItem(
        kind=ReviewKind.SAME_PERSON,
        person_id=person.id,
        other_person_id=other_person_id,
        question=SAME_PERSON_QUESTION.format(
            name=person.full_name,
            channel=participant.channel.value,
            other=index.name_of(other_person_id).title() or person.full_name,
            other_channel=", ".join(other_channels) or "another channel",
        ),
    )


def read_every[RowT](read_page: _PageReader[RowT]) -> list[RowT]:
    """Read a whole table by asking for one full page after another.

    Args:
        read_page: A repository ``list`` method.

    Returns:
        Every row the table holds.
    """
    rows: list[RowT] = []
    offset = 0
    while True:
        page = read_page(limit=MAX_PAGE_SIZE, offset=offset)
        rows.extend(page)
        # Stopping on an empty page rather than a short one: a short page is
        # also what a server-side cap below MAX_PAGE_SIZE looks like, and that
        # would truncate the table silently.
        if not page:
            return rows
        offset += len(page)
