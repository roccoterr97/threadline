"""Rules for spotting records that probably belong on one line.

The matcher only compares a *new* address with the people already known, and
only by name. That misses three situations the owner met on real data:

1. A person recorded under an address before the matching name existed, so the
   question was never asked (``erik@…`` next to Erik Lindqvist).
2. Two people from one company writing in the same e-mail conversation — one
   opportunity shown as two lines.
3. A bare address at a company where exactly one other person has a real name
   (``is@farsight.example`` next to the one named Farsight contact), or where
   the address's own name fits a few of them (``alex@anchor.example`` next to
   Alex Bronski). The company may be known by domain or, for LinkedIn contacts
   who have no address, only by its name.

Every rule here only ever produces a *suggestion*. The owner answers it in the
review list and :mod:`tracker.services.identity.merge` acts on a yes. Pure
functions only: no database, no framework.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from tracker.domain.identity import (
    company_stem,
    could_be_the_same_person,
    email_domain,
    is_shown_as_address,
    name_from_address,
    normalise_name,
    organisation_key,
    organisation_name_from_domain,
    registrable_label,
)
from tracker.shared.constants.linking import MAX_QUESTIONS_PER_ADDRESS


class LinkReason(StrEnum):
    """Why two records were put to the owner."""

    ADDRESS_NAME = "address_name"
    SHARED_THREAD = "shared_thread"
    ADDRESS_IN_COMPANY = "address_in_company"
    COMPANY_RECORD = "company_record"


@dataclass(frozen=True, slots=True)
class LinkCandidate:
    """What the rules know about one person.

    Attributes:
        person_id: The person's identifier.
        full_name: The name the person is recorded under.
        addresses: The person's e-mail addresses, lower case.
        organisation_key: Their company's name in the form every spelling of
            it shares (see :func:`~tracker.domain.identity.organisation_key`),
            or empty when no company is recorded.
        is_company_record: Whether the record is a company, not a person: it
            is only known through a hiring system ("Northwind AI Hiring Team").
    """

    person_id: UUID
    full_name: str
    addresses: tuple[str, ...] = ()
    organisation_key: str = ""
    is_company_record: bool = False

    @property
    def is_address_only(self) -> bool:
        """Whether the record shows an address instead of a name."""
        return is_shown_as_address(self.full_name)

    @property
    def company_domains(self) -> frozenset[str]:
        """The domains of this person's addresses that name an employer."""
        return company_domains(self.addresses)


@dataclass(frozen=True, slots=True)
class LinkSuggestion:
    """One pair of records worth asking the owner about.

    Attributes:
        person_id: The weaker record — the one shown as an address, if any.
        other_person_id: The record it would join.
        reason: Which rule fired.
        domain: The company domain both share, when the rule rests on one.
    """

    person_id: UUID
    other_person_id: UUID
    reason: LinkReason
    domain: str | None = None

    @property
    def pair(self) -> frozenset[UUID]:
        """The two records, in no particular order."""
        return frozenset((self.person_id, self.other_person_id))


def company_domains(addresses: Iterable[str]) -> frozenset[str]:
    """Keep the domains that say where somebody works.

    Args:
        addresses: E-mail addresses.

    Returns:
        Their domains, minus free mail providers and platforms.
    """
    domains = (email_domain(address) for address in addresses)
    return frozenset(
        domain for domain in domains if domain and organisation_name_from_domain(domain)
    )


def company_keys(addresses: Iterable[str]) -> frozenset[str]:
    """Every way a company name may be written that these addresses prove.

    ``hanna@northwind.ai`` proves "Northwind" and "Northwind AI": a company
    often carries its domain ending in its name. ``chloe@acmegroup.example``
    proves "Acme" too: a purpose word at the end of the label is dropped (see
    :func:`~tracker.domain.identity.company_stem`). Compared with
    :func:`~tracker.domain.identity.organisation_key`.

    Args:
        addresses: E-mail addresses.

    Returns:
        The keys, minus free mail providers and platforms.
    """
    keys: set[str] = set()
    for domain in company_domains(addresses):
        label = registrable_label(domain)
        if label:
            ending = domain.rsplit(".", maxsplit=1)[-1]
            keys |= {
                organisation_key(label),
                organisation_key(label + ending),
                organisation_key(company_stem(label)),
            }
    return frozenset(keys)


def works_at(person: LinkCandidate, key: str) -> bool:
    """Say whether a person is at the company a key stands for.

    Args:
        person: The person.
        key: A company key (see :func:`~tracker.domain.identity.organisation_key`).

    Returns:
        True when their recorded company or one of their addresses proves it.
    """
    return bool(key) and (person.organisation_key == key or key in company_keys(person.addresses))


def only_person_at(key: str, everyone: Sequence[LinkCandidate]) -> LinkCandidate | None:
    """Find the one record a company's mail or meeting belongs to.

    A named person wins over a company record, because the linker folds the
    record into that person anyway.

    Args:
        key: The company's key.
        everyone: Every person known.

    Returns:
        The one named person at the company, else the one company record,
        else ``None`` when nobody or several fit.
    """
    at_company = [person for person in everyone if works_at(person, key)]
    named = [person for person in at_company if not person.is_company_record]
    fitting = named or at_company
    return fitting[0] if len(fitting) == 1 else None


def company_record_matches(
    everyone: Sequence[LinkCandidate],
) -> list[tuple[LinkCandidate, tuple[LinkCandidate, ...]]]:
    """Pair each company record with the named people of that company.

    Args:
        everyone: Every person known.

    Returns:
        Per company record that matches anybody, the people it matches.
    """
    matches: list[tuple[LinkCandidate, tuple[LinkCandidate, ...]]] = []
    for record in everyone:
        if not record.is_company_record or not record.organisation_key:
            continue
        people = tuple(
            other
            for other in everyone
            if not other.is_company_record and works_at(other, record.organisation_key)
        )
        if people:
            matches.append((record, people))
    return matches


def match_by_address_name(
    person: LinkCandidate,
    everyone: Sequence[LinkCandidate],
) -> UUID | None:
    """Find the one named person a bare address could belong to.

    Args:
        person: The record to place.
        everyone: Every person known.

    Returns:
        That person's identifier, or ``None`` when the record already shows a
        name, its address suggests nothing, or more than one person could fit.
    """
    if not person.is_address_only:
        return None
    derived = {name for name in map(name_from_address, person.addresses) if name}
    fits = {
        other.person_id
        for other in everyone
        if other.person_id != person.person_id
        and not other.is_address_only
        and any(could_be_the_same_person(name, normalise_name(other.full_name)) for name in derived)
    }
    return next(iter(fits)) if len(fits) == 1 else None


def shared_company_domain(first: LinkCandidate, second: LinkCandidate) -> str | None:
    """Return the employer domain two people share, if any.

    Args:
        first: One person.
        second: The other.

    Returns:
        The shared domain (the alphabetically first when there are several),
        or ``None``. Two ``gmail.com`` addresses never count.
    """
    shared = first.company_domains & second.company_domains
    return min(shared) if shared else None


def same_organisation(first: LinkCandidate, second: LinkCandidate) -> bool:
    """Say whether two people are recorded at the same company by name.

    Args:
        first: One person.
        second: The other.

    Returns:
        True when both have a company and its name is the same once case,
        spaces and punctuation are ignored.
    """
    return bool(first.organisation_key) and first.organisation_key == second.organisation_key


def named_colleagues(
    person: LinkCandidate,
    everyone: Sequence[LinkCandidate],
) -> list[tuple[UUID, str | None]]:
    """Find the named people at its company a bare address could belong to.

    A colleague shares a company e-mail domain or the company's name. With one
    named colleague, that one is the candidate. With several, only those the
    address's own name fits are — ``alex@`` fits Alex and Alexey, not Dana —
    and only when there are few enough to ask about each.

    Args:
        person: The record to place.
        everyone: Every person known.

    Returns:
        Each candidate with the domain both share (``None`` when they share
        only the company name), ordered by identifier; empty when the record
        shows a name or no candidate is clear enough to ask about.
    """
    if not person.is_address_only:
        return []
    colleagues = {
        other.person_id: (other, domain)
        for other in everyone
        if other.person_id != person.person_id and not other.is_address_only
        for domain in [shared_company_domain(person, other)]
        if domain or same_organisation(person, other)
    }
    if len(colleagues) == 1:
        return [(colleague_id, domain) for colleague_id, (_, domain) in colleagues.items()]
    derived = {name for name in map(name_from_address, person.addresses) if name}
    fits = sorted(
        (colleague_id, domain)
        for colleague_id, (other, domain) in colleagues.items()
        if any(could_be_the_same_person(name, normalise_name(other.full_name)) for name in derived)
    )
    return fits if len(fits) <= MAX_QUESTIONS_PER_ADDRESS else []


def suggest_links(
    everyone: Sequence[LinkCandidate],
    thread_groups: Iterable[frozenset[UUID]],
) -> list[LinkSuggestion]:
    """Apply every rule and keep one suggestion per pair.

    Args:
        everyone: Every person known.
        thread_groups: For each e-mail conversation, the people who took part.

    Returns:
        The suggestions, the strongest rule winning when several fire for the
        same pair: a name hidden in the address, then a shared conversation,
        then a named colleague.
    """
    by_id = {person.person_id: person for person in everyone}
    found: dict[frozenset[UUID], LinkSuggestion] = {}
    for suggestion in (
        *_address_name_links(everyone),
        *_shared_thread_links(by_id, thread_groups),
        *_colleague_links(everyone),
    ):
        found.setdefault(suggestion.pair, suggestion)
    return list(found.values())


def _address_name_links(everyone: Sequence[LinkCandidate]) -> list[LinkSuggestion]:
    """Rule 1: the address holds the name of exactly one known person."""
    links: list[LinkSuggestion] = []
    for person in everyone:
        other = match_by_address_name(person, everyone)
        if other is not None:
            links.append(LinkSuggestion(person.person_id, other, LinkReason.ADDRESS_NAME))
    return links


def _shared_thread_links(
    by_id: dict[UUID, LinkCandidate],
    thread_groups: Iterable[frozenset[UUID]],
) -> list[LinkSuggestion]:
    """Rule 2: two people of one company wrote in the same conversation."""
    links: list[LinkSuggestion] = []
    for group in thread_groups:
        members = sorted((by_id[item] for item in group if item in by_id), key=_weaker_first)
        for index, first in enumerate(members):
            for second in members[index + 1 :]:
                domain = shared_company_domain(first, second)
                if domain:
                    links.append(
                        LinkSuggestion(
                            first.person_id, second.person_id, LinkReason.SHARED_THREAD, domain
                        )
                    )
    return links


def _colleague_links(everyone: Sequence[LinkCandidate]) -> list[LinkSuggestion]:
    """Rule 3: a bare address and the named colleagues it could belong to."""
    return [
        LinkSuggestion(person.person_id, colleague, LinkReason.ADDRESS_IN_COMPANY, domain)
        for person in everyone
        for colleague, domain in named_colleagues(person, everyone)
    ]


def _weaker_first(person: LinkCandidate) -> tuple[bool, str]:
    """Sort key putting address-only records first, then by identifier.

    The question names the weaker record first ("Should is@… be shown on the
    same line as Dana?"), and a stable order keeps runs reproducible.
    """
    return (not person.is_address_only, str(person.person_id))
