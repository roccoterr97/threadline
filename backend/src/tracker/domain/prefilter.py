"""The obvious-noise rules, applied before any AI looks at a thread.

These are pure functions over evidence a collector has already gathered: no
HTTP, no database, no configuration. They answer one question only — *is this
obviously machine traffic?* Deciding whether a human conversation matters to
the owner belongs to the assessment, not here. The few rules that depend on
what the owner tracks come in a :class:`~tracker.domain.rules.RulePack`.

Two rules outrank everything else:

* A thread the owner has written in is never noise. His own reply is the
  strongest evidence a conversation is real.
* A thread judged noise keeps no text. The collector stores its identifier, its
  dates and the decision, and nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from tracker.domain.enums import Relevance
from tracker.domain.rules import RulePack
from tracker.shared.constants.collection import (
    ALWAYS_SHARED_SENDER_DOMAINS,
    LINKEDIN_ADVERT_FOLDER_MARKERS,
    MACHINE_PREFIX_SEPARATORS,
    MACHINE_SENDER_DOMAINS,
    MACHINE_SENDER_PREFIXES,
    RELAY_SENDER_ADDRESSES,
)

_AT: Final[str] = "@"


@dataclass(frozen=True, slots=True)
class EmailThreadEvidence:
    """What the mailbox pass learned about one thread, without reading it.

    Attributes:
        sender_addresses: Every address that wrote in the thread, lower-cased.
        subjects: Every subject seen in the thread.
        has_list_unsubscribe: Whether any message carried a ``List-Unsubscribe``
            header, which only bulk senders set.
        has_owner_message: Whether the owner wrote in the thread himself.
        summary_subject_prefix: The configured prefix of Threadline's own
            summary, or ``None`` when there is no summary to recognise.
    """

    sender_addresses: tuple[str, ...] = ()
    subjects: tuple[str, ...] = ()
    has_list_unsubscribe: bool = False
    has_owner_message: bool = False
    summary_subject_prefix: str | None = None


@dataclass(frozen=True, slots=True)
class LinkedInThreadEvidence:
    """What the LinkedIn snapshot says about one thread.

    Attributes:
        folders: The distinct ``FOLDER`` values of the thread's rows.
        has_owner_message: Whether the owner wrote in the thread himself.
    """

    folders: tuple[str, ...] = ()
    has_owner_message: bool = False


def is_machine_sender(address: str) -> bool:
    """Decide whether an address belongs to a machine rather than a person.

    Args:
        address: A bare e-mail address, with or without surrounding spaces.

    Returns:
        ``True`` when the local part starts with a known machine prefix or the
        domain is a platform that only ever sends notifications.
    """
    local_part, _, domain = address.strip().lower().partition(_AT)
    if not domain:
        return False
    if _matches_machine_domain(domain):
        return True
    return any(_starts_with_prefix(local_part, prefix) for prefix in MACHINE_SENDER_PREFIXES)


def is_own_summary_email(subject: str, prefix: str | None) -> bool:
    """Decide whether a subject belongs to Threadline's own morning summary.

    Args:
        subject: The message subject.
        prefix: The configured summary subject prefix — the same value the
            summary is sent with. ``None`` or blank recognises nothing, so a
            missing prefix can never hide real mail.

    Returns:
        ``True`` when the subject carries the summary prefix, so the collector
        never feeds its own output back in.
    """
    cleaned = (prefix or "").strip().lower()
    if not cleaned:
        return False
    return subject.strip().lower().startswith(cleaned)


def is_work_subject(subject: str, rules: RulePack) -> bool:
    """Decide whether a subject is plainly about the owner's own work.

    For a job search: an application or an interview.

    Args:
        subject: The message subject.
        rules: The owner's rule pack.

    Returns:
        ``True`` when one of the pack's work phrasings appears in it.
    """
    return any(pattern.search(subject) for pattern in rules.work_subjects)


def is_platform_sender(address: str) -> bool:
    """Decide whether an address is on a notification-only platform's domain.

    Args:
        address: A bare e-mail address.

    Returns:
        ``True`` for LinkedIn, Facebook and the like, whose mail about an
        application is the platform's, not the company's.
    """
    domain = address.strip().lower().partition(_AT)[2]
    return bool(domain) and _matches_machine_domain(domain)


def is_linkedin_advert_folder(folder: str) -> bool:
    """Decide whether a snapshot folder marks a sponsored message or an InMail advert.

    Args:
        folder: The row's ``FOLDER`` value.

    Returns:
        ``True`` when the value contains one of the advert markers.
    """
    words = _split_words(folder.strip().lower())
    return any(
        word.startswith(marker) for word in words for marker in LINKEDIN_ADVERT_FOLDER_MARKERS
    )


def is_work_system_sender(address: str, rules: RulePack) -> bool:
    """Whether an address belongs to a system whose mail is the work itself.

    Signature services and shared calendars always are; the pack adds its own,
    such as hiring systems and scheduling tools for a job search. These senders
    look exactly like newsletters — a no-reply address and an unsubscribe
    header — but what they send is the work: invitations, times, exercises,
    NDAs and decisions. They are never obvious noise; the assessment decides.

    Args:
        address: The sender's e-mail address.
        rules: The owner's rule pack.

    Returns:
        True when the address is one of those systems.
    """
    cleaned = address.strip().lower()
    return cleaned in RELAY_SENDER_ADDRESSES or _on_domains(
        cleaned, (*rules.system_sender_domains, *ALWAYS_SHARED_SENDER_DOMAINS)
    )


def is_relay_sender(address: str, rules: RulePack) -> bool:
    """Whether an address is shared by many senders, so it names none of them.

    Calendars and signature services always are; one of the pack's systems is
    when it writes from a no-reply address, not from a recruiter's own one.

    Args:
        address: The sender's e-mail address.
        rules: The owner's rule pack.

    Returns:
        True for a shared address (see :mod:`tracker.domain.relay`).
    """
    cleaned = address.strip().lower()
    if cleaned in RELAY_SENDER_ADDRESSES or _on_domains(cleaned, ALWAYS_SHARED_SENDER_DOMAINS):
        return True
    local_part = cleaned.partition(_AT)[0]
    return _on_domains(cleaned, rules.system_sender_domains) and any(
        _starts_with_prefix(local_part, prefix) for prefix in MACHINE_SENDER_PREFIXES
    )


def _on_domains(address: str, domains: tuple[str, ...]) -> bool:
    """Whether an address sits on one of the domains or a subdomain of one."""
    local_part, separator, domain = address.partition(_AT)
    if not separator or not local_part or not domain:
        return False
    return any(domain == known or domain.endswith(f".{known}") for known in domains)


def judge_email_thread(evidence: EmailThreadEvidence, rules: RulePack) -> Relevance:
    """Apply the obvious-machine-mail rules to one e-mail thread.

    Args:
        evidence: What the metadata pass learned about the thread.
        rules: The owner's rule pack.

    Returns:
        :attr:`Relevance.NOISE` for obvious machine traffic, otherwise
        :attr:`Relevance.UNSURE` — the assessment decides the rest.
    """
    if evidence.has_owner_message:
        return Relevance.UNSURE
    if any(is_work_system_sender(address, rules) for address in evidence.sender_addresses):
        # A machine, but the one that carries the meeting times and the
        # decisions. Throwing this away loses the work itself.
        return Relevance.UNSURE
    prefix = evidence.summary_subject_prefix
    if any(is_own_summary_email(subject, prefix) for subject in evidence.subjects):
        return Relevance.NOISE
    if _is_company_work_mail(evidence, rules):
        return Relevance.UNSURE
    if evidence.has_list_unsubscribe:
        return Relevance.NOISE
    if evidence.sender_addresses and all(
        is_machine_sender(address) for address in evidence.sender_addresses
    ):
        return Relevance.NOISE
    return Relevance.UNSURE


def _is_company_work_mail(evidence: EmailThreadEvidence, rules: RulePack) -> bool:
    """Whether a thread is about the owner's own work, sent by the company.

    For a job search: a hiring system writing under the company's own domain
    looks like a newsletter, but its "Thank you for applying" and "Video
    interview" are the job search. A platform's own mail (LinkedIn's "Your
    application was sent") is not rescued: the platform, not the company,
    wrote it.
    """
    from_company = any(not is_platform_sender(address) for address in evidence.sender_addresses)
    return from_company and any(is_work_subject(subject, rules) for subject in evidence.subjects)


def judge_linkedin_thread(evidence: LinkedInThreadEvidence) -> Relevance:
    """Apply the sponsored-message rule to one LinkedIn thread.

    Args:
        evidence: The thread's folders and whether the owner wrote in it.

    Returns:
        :attr:`Relevance.NOISE` for an advert the owner never answered,
        otherwise :attr:`Relevance.UNSURE`.
    """
    if evidence.has_owner_message:
        return Relevance.UNSURE
    if any(is_linkedin_advert_folder(folder) for folder in evidence.folders):
        return Relevance.NOISE
    return Relevance.UNSURE


def _matches_machine_domain(domain: str) -> bool:
    """Decide whether a sending domain is a notification-only platform."""
    return any(domain == known or domain.endswith(f".{known}") for known in MACHINE_SENDER_DOMAINS)


def _starts_with_prefix(local_part: str, prefix: str) -> bool:
    """Decide whether a local part opens with a machine word.

    A bare prefix match would classify ``newsom@…`` as a newsletter, so the word
    must either be the whole local part or be followed by a separator or a
    digit. The plural is accepted too, so one entry covers ``alert`` and
    ``alerts``.
    """
    return any(_opens_with(local_part, word) for word in (prefix, f"{prefix}s"))


def _opens_with(local_part: str, word: str) -> bool:
    """Decide whether a local part is exactly a word, or that word plus a suffix."""
    if local_part == word:
        return True
    if not local_part.startswith(word):
        return False
    following = local_part[len(word)]
    return following in MACHINE_PREFIX_SEPARATORS or following.isdigit()


def _split_words(folder: str) -> list[str]:
    """Split a folder value into comparable words."""
    separators = " -_/\\.,;:"
    for separator in separators:
        folder = folder.replace(separator, " ")
    return folder.split()
