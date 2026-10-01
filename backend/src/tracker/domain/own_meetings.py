"""Meetings the owner put in their calendar themselves, with nobody invited.

A video-interview platform or a phone call leaves no invitation behind, so the
owner types the entry: "Video interview - Sam Rivera and Acme". Such an
entry has no other person in it, and lone entries are otherwise private
(flights, prep blocks, to-dos). The title decides: it must name one of the rule
pack's meeting words (for a job search: an interview), and what is left once
the kind of meeting, the owner's own name and the joining words are removed is
the company it is with. A pack with no meeting words keeps every lone entry
private.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Final

from tracker.domain.identity import normalise_name
from tracker.domain.rules import RulePack
from tracker.shared.constants.collection import (
    OWN_MEETING_EXCLUDED_WORDS,
    OWN_MEETING_FILLER_WORDS,
    OWN_MEETING_IDENTIFIER_PREFIX,
    RELAY_IDENTITY_SEPARATOR,
    RELAY_MAX_COMPANY_WORDS,
)

#: What separates the names in a title: spaces and the marks people put between
#: two sides ("Sam <> Acme", "Sam x Acme", "Interview: Acme").
_TITLE_SEPARATORS: Final[re.Pattern[str]] = re.compile(r"[\s<>:|/,()\[\]–—-]+")


def is_own_meeting(title: str, rules: RulePack) -> bool:
    """Say whether a lone calendar entry is a meeting to track rather than private time.

    Args:
        title: The entry's title.
        rules: The owner's rule pack, which names the meeting words.

    Returns:
        ``True`` when the title names such a meeting and is not a preparation block.
    """
    words = set(normalise_name(title).split())
    return bool(words & rules.own_meeting_words) and not words & OWN_MEETING_EXCLUDED_WORDS


def company_in_title(title: str, owner_names: Iterable[str], rules: RulePack) -> str | None:
    """Read the company a meeting entry is with.

    Args:
        title: The entry's title, such as "Video interview - Sam and Acme".
        owner_names: The owner's own names, which the title often repeats.
        rules: The owner's rule pack, whose meeting words are skipped.

    Returns:
        The company as written ("Acme"), or ``None`` when nothing, or too much
        to be a name, is left.
    """
    skipped = rules.own_meeting_words | OWN_MEETING_FILLER_WORDS | _owner_words(owner_names)
    kept = [
        word
        for word in _TITLE_SEPARATORS.split(title)
        if word and normalise_name(word) not in skipped
    ]
    if not kept or len(kept) > RELAY_MAX_COMPANY_WORDS:
        return None
    return " ".join(kept)


def own_meeting_identifier(company: str) -> str:
    """Build the identifier a company named only in an entry's title is kept under.

    Args:
        company: The company's name.

    Returns:
        ``"own-calendar#<normalised company>"`` — never an address.
    """
    return f"{OWN_MEETING_IDENTIFIER_PREFIX}{RELAY_IDENTITY_SEPARATOR}{normalise_name(company)}"


def _owner_words(owner_names: Iterable[str]) -> frozenset[str]:
    """Each separate word of the owner's names, normalised."""
    return frozenset(word for name in owner_names for word in normalise_name(name).split())
