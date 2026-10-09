"""Asking about records that probably belong on one line, across everything stored.

The matcher only looks at an address the moment it is first collected. This
walks what the database already holds, applies the rules in
:mod:`tracker.domain.linking`, and adds a ``same_person`` question for every
new pair. It never merges: a "yes" in the review list is applied by
:class:`~tracker.services.identity.merge.PersonMerger`.

No message text is read. Only who sent something in which thread.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Final
from uuid import UUID

from tracker.domain.enums import Channel, Relevance, ReviewAnswer, ReviewKind
from tracker.domain.identity import organisation_key, organisation_name_from_domain
from tracker.domain.linking import (
    LinkCandidate,
    LinkReason,
    LinkSuggestion,
    company_record_matches,
    suggest_links,
)
from tracker.domain.models import Organisation, Person, PersonIdentity, ReviewItem
from tracker.domain.relay import is_relay_identity
from tracker.domain.rules import RulePack
from tracker.repositories import Repositories
from tracker.services.identity.matcher import SAME_PERSON_QUESTION
from tracker.services.identity.merge import PersonMerger
from tracker.shared.constants.linking import MAX_QUESTIONS_PER_ADDRESS
from tracker.shared.logging import get_logger

#: Question asked when two records look like one opportunity.
SAME_OPPORTUNITY_QUESTION: Final[str] = (
    "Should {name} be shown on the same line as {other}? Both are at {organisation} and {reason}."
)

#: The end of that question, per rule.
_REASON_WORDING: Final[dict[LinkReason, str]] = {
    LinkReason.SHARED_THREAD: "wrote in the same e-mail conversation",
    LinkReason.ADDRESS_IN_COMPANY: "this address has no name of its own",
}

#: Question asked when a company record fits several people of that company.
COMPANY_RECORD_QUESTION: Final[str] = (
    "Should {name} be shown on the same line as {other}? {other} is at that company, "
    "and so is somebody else, so Threadline will not choose on its own."
)

_log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class LinkReport:
    """What a run of the linker found.

    Attributes:
        asked: New questions added to the review list.
        already_asked: Pairs found again that the owner was already asked about.
        joined: Company records folded into the one person they can only mean.
    """

    asked: int = 0
    already_asked: int = 0
    joined: int = 0


class PeopleLinker:
    """Adds "same person?" questions for pairs the matcher could not see."""

    def __init__(self, repositories: Repositories, rules: RulePack) -> None:
        """Bind the linker to the database.

        Args:
            repositories: The repository container.
            rules: The owner's collection rules, which say which addresses are
                shared systems rather than people.
        """
        self._repositories = repositories
        self._rules = rules

    def link(self) -> LinkReport:
        """Look at every stored person and ask about each new likely pair.

        Returns:
            How many questions were added, and how many were already asked.
        """
        people = [
            person
            for person in self._repositories.people.list_every()
            if person.relevance is not Relevance.NOISE
        ]
        identities = self._repositories.person_identities.list_every()
        organisations = self._repositories.organisations.list_every()
        candidates = link_candidates(people, identities, organisations, self._rules)
        questions = self._repositories.review_items.list_by_kind(ReviewKind.SAME_PERSON)
        joined, ambiguous = self._join_company_records(
            candidates, people, _pairs(questions, answer=ReviewAnswer.NO)
        )
        if joined:
            return replace(self.link(), joined=joined)
        suggestions = [*suggest_links(candidates, self._thread_groups(identities)), *ambiguous]
        asked = _pairs(questions)
        new = [suggestion for suggestion in suggestions if suggestion.pair not in asked]
        questions = self._questions(new, people, identities)
        self._repositories.review_items.bulk_upsert(questions)
        report = LinkReport(asked=len(questions), already_asked=len(suggestions) - len(new))
        _log.info("people_linked", asked=report.asked, already_asked=report.already_asked)
        return report

    def _join_company_records(
        self,
        candidates: Sequence[LinkCandidate],
        people: Sequence[Person],
        declined: set[frozenset[UUID]],
    ) -> tuple[int, list[LinkSuggestion]]:
        """Fold a company record into the one person of that company, or ask.

        "Northwind AI Hiring Team" and Hanna at northwind.ai are one opportunity,
        so they are joined without a question, under Hanna's name, and assessed
        again together. When the company has several people, choosing one would
        be a guess: the owner is asked about each instead. A pair the owner has
        already answered "no" about is never joined, even when it is the only
        match left: the owner's answer outranks the rule.

        Args:
            candidates: Every person, described for the rules.
            people: The same people, by record.
            declined: The pairs the owner answered "no, not the same person" about.

        Returns:
            How many records were joined, and the questions for the rest.
        """
        by_id = {person.id: person for person in people}
        joined = 0
        ambiguous: list[LinkSuggestion] = []
        for record, matches in company_record_matches(candidates):
            if len(matches) != 1:
                ambiguous.extend(
                    LinkSuggestion(record.person_id, match.person_id, LinkReason.COMPANY_RECORD)
                    for match in matches[:MAX_QUESTIONS_PER_ADDRESS]
                )
                continue
            (only,) = matches
            if frozenset((record.person_id, only.person_id)) in declined:
                continue
            survivor = by_id[only.person_id]
            PersonMerger(self._repositories).join(survivor, by_id[record.person_id])
            joined += 1
        return joined, ambiguous

    def _thread_groups(self, identities: Sequence[PersonIdentity]) -> list[frozenset[UUID]]:
        """List, per kept e-mail conversation, the people who took part in it."""
        threads = [
            thread
            for thread in self._repositories.conversations.list_every()
            if thread.channel is Channel.EMAIL and thread.relevance is not Relevance.NOISE
        ]
        owner_of = {
            identity.identifier.lower(): identity.person_id
            for identity in identities
            if identity.channel is Channel.EMAIL
        }
        groups: dict[UUID, set[UUID]] = defaultdict(set)
        for thread in threads:
            if thread.person_id is not None:
                groups[thread.id].add(thread.person_id)
        for thread_id, sender in self._repositories.messages.list_senders(list(groups)):
            person_id = owner_of.get(sender.strip().lower())
            if person_id is not None:
                groups[thread_id].add(person_id)
        return [frozenset(group) for group in groups.values() if len(group) > 1]

    def _questions(
        self,
        suggestions: Sequence[LinkSuggestion],
        people: Sequence[Person],
        identities: Sequence[PersonIdentity],
    ) -> list[ReviewItem]:
        """Word one review item per suggestion."""
        if not suggestions:
            return []
        names = {person.id: person.full_name for person in people}
        channels: dict[UUID, set[str]] = defaultdict(set)
        for identity in identities:
            channels[identity.person_id].add(identity.channel.value)
        organisations = self._organisation_names(suggestions)
        return [
            ReviewItem(
                kind=ReviewKind.SAME_PERSON,
                person_id=suggestion.person_id,
                other_person_id=suggestion.other_person_id,
                question=_wording(suggestion, names, channels, organisations),
            )
            for suggestion in suggestions
        ]

    def _organisation_names(self, suggestions: Sequence[LinkSuggestion]) -> dict[str, str]:
        """Name the company behind each shared domain, as the owner last saw it."""
        domains = sorted({suggestion.domain for suggestion in suggestions if suggestion.domain})
        if not domains:
            return {}
        return {
            organisation.email_domain: organisation.name
            for organisation in self._repositories.organisations.list_by_email_domains(domains)
            if organisation.email_domain
        }


def _pairs(
    questions: Sequence[ReviewItem], *, answer: ReviewAnswer | None = None
) -> set[frozenset[UUID]]:
    """The pairs "same person?" questions name, in either direction.

    Args:
        questions: Every "same person?" question.
        answer: When given, only the questions answered this way count.

    Returns:
        Each pair once.
    """
    return {
        frozenset((item.person_id, item.other_person_id))
        for item in questions
        if item.person_id is not None
        and item.other_person_id is not None
        and (answer is None or item.answer is answer)
    }


def link_candidates(
    people: Sequence[Person],
    identities: Sequence[PersonIdentity],
    organisations: Sequence[Organisation],
    rules: RulePack,
) -> list[LinkCandidate]:
    """Describe each person by name, e-mail addresses and company, for the rules.

    Args:
        people: The people to describe.
        identities: Every identity, of these people and others.
        organisations: Every organisation.
        rules: The owner's collection rules.

    Returns:
        One candidate per person that can still be reached.
    """
    company = {
        organisation.id: organisation_key(organisation.name) for organisation in organisations
    }
    addresses: dict[UUID, list[str]] = defaultdict(list)
    reachable: set[UUID] = set()
    personal: set[UUID] = set()
    for identity in identities:
        reachable.add(identity.person_id)
        shared = identity.channel is Channel.EMAIL and is_relay_identity(
            identity.identifier, rules
        )
        if not shared:
            personal.add(identity.person_id)
        # A shared sender's address (or a key built on one) names nobody: mining
        # it for a name or a company domain would tie unrelated people together.
        if identity.channel is Channel.EMAIL and not shared:
            addresses[identity.person_id].append(identity.identifier.strip().lower())
    return [
        LinkCandidate(
            person.id,
            person.full_name,
            tuple(sorted(addresses[person.id])),
            company.get(person.organisation_id, "") if person.organisation_id else "",
            is_company_record=person.id not in personal,
        )
        for person in people
        # A record with no address or profile left is a leftover nobody can
        # reach; pairing it with somebody would only produce a dead question.
        if person.id in reachable
    ]


def _wording(
    suggestion: LinkSuggestion,
    names: dict[UUID, str],
    channels: dict[UUID, set[str]],
    organisations: dict[str, str],
) -> str:
    """Write the question for one suggestion in plain English."""
    name = names[suggestion.person_id]
    other = names[suggestion.other_person_id]
    if suggestion.reason is LinkReason.COMPANY_RECORD:
        return COMPANY_RECORD_QUESTION.format(name=name, other=other)
    if suggestion.reason is LinkReason.ADDRESS_NAME or suggestion.domain is None:
        return SAME_PERSON_QUESTION.format(
            name=name,
            channel=", ".join(sorted(channels[suggestion.person_id])),
            other=other,
            other_channel=", ".join(sorted(channels[suggestion.other_person_id])),
        )
    organisation = (
        organisations.get(suggestion.domain)
        or organisation_name_from_domain(suggestion.domain)
        or suggestion.domain
    )
    return SAME_OPPORTUNITY_QUESTION.format(
        name=name,
        other=other,
        organisation=organisation,
        reason=_REASON_WORDING[suggestion.reason],
    )
