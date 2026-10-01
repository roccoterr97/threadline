"""Rules for deciding when two identities are the same person.

Pure functions only: name normalisation, the free-mail domain list, and the
evidence rule that decides between merging two identities and asking the owner.
The service that walks the database lives in
:mod:`tracker.services.identity.matcher`.

The merge rule is deliberately cautious. Merging two people who are not the
same is far worse than leaving them apart: the owner would see one timeline
made of two unrelated conversations and could not tell. So a merge happens only
when the normalised name matches *and* is unique on both sides; anything less
becomes a question in the review list.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final

#: Second-level names of the mail providers anyone can sign up to. A person's
#: address at one of these says nothing about where they work, whatever the
#: country suffix is, so ``hotmail.it`` and ``hotmail.com`` both land here.
FREE_MAIL_PROVIDERS: Final[frozenset[str]] = frozenset(
    {
        "aol",
        "fastmail",
        "free",
        "gmail",
        "gmx",
        "googlemail",
        "hotmail",
        "icloud",
        "hey",
        "inbox",
        "libero",
        "live",
        "mac",
        "mail",
        "me",
        "msn",
        "orange",
        "outlook",
        "posteo",
        "proton",
        "protonmail",
        "tiscali",
        "tutanota",
        "virgilio",
        "wanadoo",
        "web",
        "yahoo",
        "yandex",
        "ymail",
        "zoho",
    }
)

#: Domains that belong to a platform rather than to an employer.
NON_ORGANISATION_DOMAINS: Final[frozenset[str]] = frozenset(
    {"linkedin.com", "microsoft.com", "outlook.office365.com"}
)

#: Labels that a country registry hands out to everybody, so they identify no
#: holder: ``example.co.uk`` belongs to ``example``, not to ``co``.
_PUBLIC_SECOND_LEVEL_LABELS: Final[frozenset[str]] = frozenset(
    {"ac", "co", "com", "edu", "gov", "net", "or", "org", "sch"}
)

#: Words a company adds to the end of its name to make a domain for one
#: purpose: ``acmecareers.example`` and ``acmegroup.example`` are both Acme's.
#: Longest first, so "careers" is removed whole rather than just "s".
COMPANY_DOMAIN_SUFFIXES: Final[tuple[str, ...]] = (
    "recruitment",
    "recruiting",
    "careers",
    "career",
    "hiring",
    "talent",
    "group",
    "jobs",
    "mail",
    "hr",
)

#: What must be left of a label once a suffix is removed for it to still name
#: a company: ``hr.example`` or ``myjobs.example`` keep their label as it is.
MIN_COMPANY_STEM_LENGTH: Final[int] = 3

#: A domain needs at least a label and a suffix.
_MINIMUM_DOMAIN_LABELS: Final[int] = 2

_AT: Final[str] = "@"
_COMBINING_MARK: Final[str] = "Mn"
_NAME_SEPARATORS: Final[str] = "-_.,'’`"


def normalise_name(raw: str) -> str:
    """Reduce a display name to a form two spellings of one person share.

    Accents are stripped, case is dropped, punctuation becomes a space and runs
    of whitespace collapse, so ``"Élodie  Martin"`` and ``"elodie martin"`` come
    out the same.

    Args:
        raw: The name as a source spelled it.

    Returns:
        The normalised name, or an empty string when nothing is left.
    """
    decomposed = unicodedata.normalize("NFKD", raw)
    without_accents = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != _COMBINING_MARK
    )
    flattened = "".join(
        " " if character in _NAME_SEPARATORS else character for character in without_accents
    )
    return " ".join(flattened.lower().split())


def is_shown_as_address(full_name: str) -> bool:
    """Say whether a person is recorded under an e-mail address, not a name.

    That happens when a sender set no display name. Such a record is the weaker
    side of any pairing: the owner does not recognise it on the dashboard.

    Args:
        full_name: The name the person is recorded under.

    Returns:
        ``True`` when the "name" is really an address.
    """
    return _AT in full_name


def email_domain(address: str) -> str | None:
    """Extract the domain part of an e-mail address.

    Args:
        address: A bare e-mail address.

    Returns:
        The lower-case domain, or ``None`` when the address has none.
    """
    _, separator, domain = address.strip().lower().partition(_AT)
    if not separator or not domain:
        return None
    return domain.strip(".")


def is_free_mail_domain(domain: str) -> bool:
    """Decide whether a domain is a mail provider anyone can sign up to.

    Args:
        domain: The domain part of an address, in any case.

    Returns:
        ``True`` when the domain says nothing about where its owner works.
    """
    label = registrable_label(domain)
    return label is None or label in FREE_MAIL_PROVIDERS


def organisation_name_from_domain(domain: str) -> str | None:
    """Guess an organisation name from an e-mail domain.

    Args:
        domain: The domain part of an address.

    Returns:
        A readable name, or ``None`` when the domain is a free mail provider or
        a platform and therefore proves nothing about an employer.
    """
    cleaned = domain.strip().lower().strip(".")
    if not cleaned or cleaned in NON_ORGANISATION_DOMAINS:
        return None
    label = registrable_label(cleaned)
    if label is None or label in FREE_MAIL_PROVIDERS:
        return None
    return label.replace("-", " ").title()


def registrable_label(domain: str) -> str | None:
    """Return the label that identifies the holder of a domain.

    ``acme.example`` and ``acme.co.uk`` both answer ``acme``: the public suffix
    in front of the country code carries no information about the holder.

    Args:
        domain: The domain part of an address.

    Returns:
        The holder's label, or ``None`` when the value is not a domain.
    """
    labels = [label for label in domain.strip().lower().strip(".").split(".") if label]
    if len(labels) < _MINIMUM_DOMAIN_LABELS:
        return None
    if labels[-2] in _PUBLIC_SECOND_LEVEL_LABELS and len(labels) >= _MINIMUM_DOMAIN_LABELS + 1:
        return labels[-3]
    return labels[-2]


def company_stem(label: str) -> str:
    """Remove a purpose word from the end of a domain label.

    ``acmecareers`` and ``acme-group`` both answer ``acme``, so a
    company's careers domain, its group domain and its name share one key.
    Conservative: one suffix at most, and only when at least
    :data:`MIN_COMPANY_STEM_LENGTH` letters remain.

    Args:
        label: A domain's holder label (see :func:`registrable_label`).

    Returns:
        The label without the suffix, or the label unchanged.
    """
    cleaned = label.strip().lower()
    for suffix in COMPANY_DOMAIN_SUFFIXES:
        if not cleaned.endswith(suffix):
            continue
        stem = cleaned[: -len(suffix)].rstrip("-")
        if sum(character.isalpha() for character in stem) >= MIN_COMPANY_STEM_LENGTH:
            return stem
        return cleaned
    return cleaned


def company_name_from_domain(domain: str) -> str | None:
    """Name the company behind a domain it uses for one purpose.

    Args:
        domain: The domain part of an address, such as ``acmecareers.example``.

    Returns:
        "Acme", or ``None`` when the domain names no employer.
    """
    if organisation_name_from_domain(domain) is None:
        return None
    label = registrable_label(domain)
    return company_stem(label).replace("-", " ").title() if label else None


def may_auto_merge(*, matches_on_other_side: int, matches_on_this_side: int) -> bool:
    """Decide whether one new identity may join an existing person without asking.

    Args:
        matches_on_other_side: How many known people already carry the same
            normalised name on a different channel.
        matches_on_this_side: How many identities being collected right now
            carry that normalised name on this channel, this one included.

    Returns:
        ``True`` only when exactly one person matches on each side. Anything
        else is ambiguous and becomes a ``same_person`` review item.
    """
    return matches_on_other_side == 1 and matches_on_this_side == 1


#: Local parts that name a function, not a human, so they can never be somebody.
ROLE_LOCAL_PARTS: Final[frozenset[str]] = frozenset(
    {
        "admin",
        "applications",
        "billing",
        "careers",
        "contact",
        "customer",
        "hello",
        "hi",
        "hr",
        "info",
        "interview",
        "interviews",
        "jobs",
        "mail",
        "newsletter",
        "no reply",
        "noreply",
        "notifications",
        "office",
        "people",
        "recruiting",
        "recruitment",
        "sales",
        "service",
        "support",
        "talent",
        "team",
    }
)

#: Shortest local part that can stand for a person's name. "is@" or "jm@" say
#: nothing; guessing from them would pair unrelated people.
MIN_DERIVED_NAME_LENGTH: Final[int] = 4

#: A first initial and a surname need a name of at least two parts.
_MIN_NAME_PARTS: Final[int] = 2


def name_from_address(address: str) -> str:
    """Guess the name hiding in an e-mail address, when there is one.

    Many senders set no display name, so the person ends up recorded as their
    address. The part before the ``@`` often still holds the name:
    ``jeanmarc@acmedata.example`` or ``nicolas.rey75@acme.example``.

    Args:
        address: The e-mail address.

    Returns:
        The normalised name the address suggests, or an empty string when it
        suggests nothing usable — a role mailbox, or something too short to
        tell people apart.
    """
    local = address.strip().lower().rpartition("@")[0] or address.strip().lower()
    without_digits = "".join(character for character in local if not character.isdigit())
    candidate = normalise_name(without_digits)
    if not candidate or candidate in ROLE_LOCAL_PARTS:
        return ""
    if len(candidate.replace(" ", "")) < MIN_DERIVED_NAME_LENGTH:
        return ""
    return candidate


#: What splits a work address into first name and surname: ``alessia.conti``
#: or ``alessia_conti``. A hyphen joins a double name, so it is kept.
_ADDRESS_NAME_SEPARATOR: Final[re.Pattern[str]] = re.compile(r"[._]")

#: A name shown from an address has a first name and a surname, at most one
#: middle part; anything longer is more likely a team or a project.
_MAX_SHOWN_NAME_PARTS: Final[int] = 3

#: Each part must be a real name, not an initial: ``a.conti`` stays an address.
_MIN_SHOWN_NAME_PART_LENGTH: Final[int] = 2


def shown_name_from_address(address: str) -> str:
    """Spell the name an address clearly holds, for showing on the dashboard.

    Narrower than :func:`name_from_address`: only an address that separates a
    first name from a surname qualifies, so ``alessia.conti@quick-solve.example``
    shows as "Alessia Conti" while ``jeanmarc@`` or ``a.conti@`` stay as
    they are. It changes what is shown, never who is matched with whom.

    Args:
        address: The e-mail address.

    Returns:
        The capitalised name, or an empty string when the address does not
        plainly spell one.
    """
    local = address.strip().lower().rpartition(_AT)[0]
    pieces = (piece.strip("-0123456789") for piece in _ADDRESS_NAME_SEPARATOR.split(local))
    parts = [piece for piece in pieces if piece]
    if not _MIN_NAME_PARTS <= len(parts) <= _MAX_SHOWN_NAME_PARTS:
        return ""
    if any(not _is_name_part(part) for part in parts):
        return ""
    return " ".join("-".join(piece.capitalize() for piece in part.split("-")) for part in parts)


def _is_name_part(part: str) -> bool:
    """Say whether one piece of an address can be part of a person's name."""
    letters = part.replace("-", "")
    return (
        letters.isalpha()
        and len(letters) >= _MIN_SHOWN_NAME_PART_LENGTH
        and normalise_name(part) not in ROLE_LOCAL_PARTS
    )


def could_be_the_same_person(derived: str, known: str) -> bool:
    """Say whether an address-derived name could belong to a known person.

    Deliberately narrow: the letters of the derived name must open the letters
    of the known one, so ``jeanmarc`` reaches ``Jean-Marc Valette`` and
    ``erik`` reaches ``Erik Lindqvist``, while ``martin`` does not reach
    ``Martin, Bernard`` by accident more often than it helps. The one other
    shape accepted is the common work address of first initial and surname:
    ``bwerner`` reaches ``Bruno Werner``. This is only ever grounds for
    asking the owner, never for merging.

    Args:
        derived: The normalised name an address suggested.
        known: The normalised name of a person already recorded.

    Returns:
        True when the two are worth putting to the owner as one question.
    """
    if not derived or not known:
        return False
    left = derived.replace(" ", "")
    right = known.replace(" ", "")
    if len(left) < MIN_DERIVED_NAME_LENGTH:
        return False
    if right.startswith(left) or left.startswith(right):
        return True
    parts = known.split()
    return len(parts) >= _MIN_NAME_PARTS and left == parts[0][0] + parts[-1]


def organisation_key(name: str) -> str:
    """Reduce a company name to a form every spelling of it shares.

    Sources and the assessment spell one company several ways — "Anchor VC",
    "ANCHOR VC", "Anchor.vc" — and each spelling became its own organisation
    record. Ignoring case, accents, spaces and punctuation makes them one,
    without guessing any further than that.

    Args:
        name: The company name as recorded.

    Returns:
        Letters and digits only, lower case; empty when nothing is left.
    """
    return "".join(character for character in normalise_name(name) if character.isalnum())
