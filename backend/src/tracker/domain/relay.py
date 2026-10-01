"""Who is really writing when a shared system sends the e-mail.

Hiring systems (Ashby, Greenhouse, Workable…), booking tools, e-signature
services and shared calendars send for many companies and people from one
address. Which systems count depends on what the owner tracks: the rule pack
(:class:`~tracker.domain.rules.RulePack`) names them. Taking that
address as the person put fifteen companies' applications under one name and
hid an interview. This module looks behind the address, in order of how much
the mail itself proves:

1. a Reply-To that is a real person — calendar invitations and DocuSign carry
   the organiser or the requester there;
2. an address written in the display name ("erik@acme.example (Google Calendar)");
3. a company in the display name ("Northwind AI Hiring Team");
4. a company in the subject ("Thank you for applying to Tasko");
5. otherwise the shared address, as before.

Cases 3 and 4 have no address of their own, so they get a synthetic identifier
joining the shared address and the company. It is never read as an address.

A hiring system can also write under the company's own domain
(``notification@acmecareers.example``). A machine address there, sending mail
about the owner's application, is the company too: every such address of the
domain becomes one company record, named from the display name, the subject or
else the domain ("Acme").
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final

from tracker.domain.identity import company_name_from_domain, email_domain, normalise_name
from tracker.domain.prefilter import (
    is_machine_sender,
    is_platform_sender,
    is_relay_sender,
    is_work_subject,
)
from tracker.domain.rules import RulePack
from tracker.shared.constants.collection import (
    COMPANY_SYSTEM_LOCAL_PART,
    OWN_MEETING_IDENTIFIER_PREFIX,
    RELAY_IDENTITY_SEPARATOR,
    RELAY_MAX_COMPANY_WORDS,
    RELAY_PLATFORM_NAMES,
    RELAY_VIA_MARKER,
)

_ADDRESS_IN_TEXT: Final[re.Pattern[str]] = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_TEAM_WORDS: Final[str] = "team"


@dataclass(frozen=True, slots=True)
class RelayedSender:
    """The person or company behind one message.

    Attributes:
        identifier: A real address, or a synthetic ``address#company`` key.
        display_name: The name to record them under.
        organisation_name: The company, when only the company is known.
    """

    identifier: str
    display_name: str
    organisation_name: str | None = None


def is_relay_identity(identifier: str, rules: RulePack) -> bool:
    """Whether an identifier is a shared address or a synthetic key built on one.

    Such an identifier names no person: it must never be mined for a name or a
    company domain.

    Args:
        identifier: A stored e-mail identifier.
        rules: The owner's rule pack.

    Returns:
        ``True`` for a shared address, an ``address#company`` key (including
        one built on a company's own machine address), or the key of a company
        named only in the owner's own calendar entry.
    """
    head, separator, _ = identifier.partition(RELAY_IDENTITY_SEPARATOR)
    if head == OWN_MEETING_IDENTIFIER_PREFIX or is_relay_sender(head, rules):
        return True
    return bool(separator) and is_machine_sender(head)


def real_sender(
    address: str,
    display_name: str,
    reply_to: Sequence[tuple[str, str]],
    subject: str,
    is_owner: Callable[[str], bool],
    rules: RulePack,
) -> RelayedSender:
    """Work out who is behind one message.

    Args:
        address: The sender address, lower-cased.
        display_name: The sender's display name.
        reply_to: The Reply-To entries, as ``(address, name)`` pairs.
        subject: The message subject.
        is_owner: Says whether an address is one of the owner's own.
        rules: The owner's rule pack.

    Returns:
        The sender unchanged when the address is not a shared system;
        otherwise the best evidence of the real person or company.
    """
    if _is_company_system(address, subject, rules):
        return _company_system_sender(address, display_name, subject, rules)
    if not is_relay_sender(address, rules):
        return RelayedSender(identifier=address, display_name=display_name)
    person = _reply_to_person(reply_to, display_name, is_owner, rules)
    if person is not None:
        return person
    written = _ADDRESS_IN_TEXT.search(display_name)
    if written is not None and not is_relay_sender(written.group(0), rules):
        return RelayedSender(identifier=written.group(0).lower(), display_name="")
    return _company_sender(address, display_name, subject, rules)


def _company_sender(
    address: str,
    display_name: str,
    subject: str,
    rules: RulePack,
) -> RelayedSender:
    """File a message under the company behind a shared address.

    A team name ("Northwind AI Hiring Team") settles the company. Otherwise the
    subject's company wins, because a plain name may be a recruiter's own
    ("Jane Doe") — that name is kept to show, but the company is the key.
    """
    shown = display_name.strip()
    named, was_team = _display_company(shown, address, rules)
    company = named if was_team else company_from_subject(subject, rules) or named
    if company is None:
        return RelayedSender(identifier=address, display_name=display_name)
    return RelayedSender(
        identifier=relay_identifier(address, company),
        display_name=shown if named else f"{company} {rules.team_label}",
        organisation_name=company,
    )


def _is_company_system(address: str, subject: str, rules: RulePack) -> bool:
    """Whether a company's own machine address is writing about the application."""
    domain = email_domain(address)
    return (
        domain is not None
        and company_name_from_domain(domain) is not None
        and is_machine_sender(address)
        and not is_platform_sender(address)
        and not is_relay_sender(address, rules)
        and is_work_subject(subject, rules)
    )


def _company_system_sender(
    address: str,
    display_name: str,
    subject: str,
    rules: RulePack,
) -> RelayedSender:
    """File a company's own machine mail under one record for its domain.

    The identifier is built from the domain alone, so ``notification@`` and
    ``notifications@acmecareers.example`` land on one line whatever each subject
    says. The name shown and the company come from the display name or the
    subject when they give one, else from the domain.
    """
    domain = email_domain(address) or ""
    from_domain = company_name_from_domain(domain) or domain
    shared = f"{COMPANY_SYSTEM_LOCAL_PART}@{domain}"
    # A display name such as "notifications" is the mailbox, not a name.
    local_form = normalise_name(display_name).replace(" ", "-")
    shown = "" if is_machine_sender(f"{local_form}@{domain}") else display_name
    named = _company_sender(shared, shown, subject, rules)
    company = named.organisation_name or from_domain
    # A bare company name ("Acme") reads as a person on the dashboard.
    plain = normalise_name(named.display_name) in {"", normalise_name(company)}
    return RelayedSender(
        identifier=relay_identifier(shared, from_domain),
        display_name=f"{company} {rules.team_label}" if plain else named.display_name.strip(),
        organisation_name=company,
    )


def relay_identifier(address: str, company: str) -> str:
    """Build the synthetic identifier for one company behind a shared address.

    Args:
        address: The shared address.
        company: The company's name.

    Returns:
        ``"<address>#<normalised company>"``.
    """
    return f"{address.strip().lower()}{RELAY_IDENTITY_SEPARATOR}{normalise_name(company)}"


def _display_company(
    display_name: str,
    address: str,
    rules: RulePack,
) -> tuple[str | None, bool]:
    """Read a company out of a shared system's display name.

    Args:
        display_name: The name the system set, such as "Bluebird Hiring Team".
        address: The sender address, which some systems repeat as the name.
        rules: The owner's rule pack.

    Returns:
        The name without its team words, or ``None`` when the name is empty, is
        the address or names the system itself; and whether team words were
        removed, which is what proves the name is a company's.
    """
    if not display_name or display_name.lower() == address.strip().lower():
        return None, False
    if "@" in display_name:
        return None, False
    company = _strip_team_suffix(display_name, rules)
    platform = normalise_name(company)
    if not company or platform in RELAY_PLATFORM_NAMES or platform in rules.platform_names:
        return None, False
    return company, company != _tidy(display_name)


def company_from_subject(subject: str, rules: RulePack) -> str | None:
    """Read a company out of a subject such as "Thank you for applying to Tasko".

    Args:
        subject: The message subject.
        rules: The owner's rule pack, which knows the phrasings.

    Returns:
        The company, or ``None`` when no known phrasing names one.
    """
    for pattern in rules.company_subjects:
        found = pattern.search(subject)
        if found is None:
            continue
        company = _tidy(found.group("company"))
        if company and len(company.split()) <= RELAY_MAX_COMPANY_WORDS:
            return company
    return None


def clean_via_name(display_name: str) -> str:
    """Drop the service a name was relayed through: "Ann Lee via Docusign" → "Ann Lee".

    Args:
        display_name: The display name as the service wrote it.

    Returns:
        The person's own name.
    """
    before, marker, _ = display_name.rpartition(RELAY_VIA_MARKER)
    return before.strip() if marker and before.strip() else display_name.strip()


def _reply_to_person(
    reply_to: Sequence[tuple[str, str]],
    display_name: str,
    is_owner: Callable[[str], bool],
    rules: RulePack,
) -> RelayedSender | None:
    """The first Reply-To entry that is a real person other than the owner."""
    for address, name in reply_to:
        cleaned = address.strip().lower()
        if not cleaned or is_owner(cleaned) or is_relay_sender(cleaned, rules):
            continue
        if is_machine_sender(cleaned):
            continue
        spelled = name.strip()
        if not spelled or spelled.lower() == cleaned:
            spelled = clean_via_name(display_name) if RELAY_VIA_MARKER in display_name else ""
        return RelayedSender(identifier=cleaned, display_name=spelled)
    return None


def _strip_team_suffix(name: str, rules: RulePack) -> str:
    """Remove "Hiring Team" and the like from the end of a name."""
    words = name.split()
    lowered = [word.lower() for word in words]
    for suffix in rules.team_suffixes:
        parts = suffix.split()
        if len(lowered) > len(parts) and lowered[-len(parts) :] == parts:
            return _tidy(" ".join(words[: -len(parts)]))
    if lowered and lowered[-1] == _TEAM_WORDS:
        return ""
    return _tidy(name)


def _tidy(text: str) -> str:
    """Trim spaces and trailing symbols such as an emoji or a dash."""
    kept = text.strip()
    while kept and not kept[-1].isalnum():
        kept = kept[:-1].rstrip()
    while kept and not kept[0].isalnum():
        kept = kept[1:].lstrip()
    return kept
