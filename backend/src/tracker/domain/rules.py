"""The collection rules that depend on what the owner tracks.

Most of the noise rules hold for anybody: a no-reply address is a machine, a
newsletter carries an unsubscribe header, LinkedIn's own mail is a platform's.
A few only make sense for one kind of work. For a job search, a hiring system's
no-reply mail *is* the conversation, a subject such as "Thank you for applying"
rescues a company's machine mail, and "Video interview - Acme" in the owner's
own calendar is a meeting worth tracking. For sales, none of that applies.

Those lists form a :class:`RulePack`, which comes from the owner's profile (the
``[rules]`` part of a preset) and is handed to every rule that needs it. The
lists that hold for everybody stay in :mod:`tracker.shared.constants.collection`.
"""

from __future__ import annotations

import re
from functools import cached_property
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

#: Suffix added to a company only known through a shared system, unless the
#: pack names its own ("Northwind AI Hiring Team").
DEFAULT_TEAM_LABEL: Final[str] = "Team"

#: One lower-case word or phrase.
Phrase = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=1)]


class RulePack(BaseModel):
    """The collection rules one kind of work adds to the general ones.

    Attributes:
        system_sender_domains: Systems whose machine mail is the work itself —
            hiring systems and scheduling tools for a job search, booking tools
            for sales. Their mail is never obvious noise, and a no-reply address
            there is shared by many companies, so Threadline looks behind it.
        platform_names: Display names that name such a system rather than the
            company behind it ("Greenhouse").
        team_suffixes: Endings a system adds to a company's name ("Hiring
            Team"). Longest first, so a whole ending is removed at once.
        team_label: What a company known only through a system is shown as,
            after its name ("Hiring Team").
        company_subject_patterns: Regular expressions reading a company out of
            a subject; each has one group named ``company``.
        work_subject_patterns: Regular expressions for subjects that plainly
            concern the owner's own work ("Thank you for applying"). A company's
            machine mail with such a subject is never obvious noise.
        own_meeting_words: Words that make an entry the owner typed in their
            own calendar, with nobody invited, a meeting worth tracking.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    system_sender_domains: tuple[Phrase, ...] = ()
    platform_names: frozenset[Phrase] = frozenset()
    team_suffixes: tuple[Phrase, ...] = ()
    team_label: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] = (
        DEFAULT_TEAM_LABEL
    )
    company_subject_patterns: tuple[str, ...] = ()
    work_subject_patterns: tuple[str, ...] = ()
    own_meeting_words: frozenset[Phrase] = frozenset()

    @field_validator("company_subject_patterns", "work_subject_patterns")
    @classmethod
    def _compile(cls, patterns: tuple[str, ...]) -> tuple[str, ...]:
        """Refuse a pattern that is not a valid regular expression."""
        for pattern in patterns:
            try:
                re.compile(pattern)
            except re.error as error:
                message = f"not a valid pattern: {pattern!r} ({error})"
                raise ValueError(message) from error
        return patterns

    @field_validator("company_subject_patterns")
    @classmethod
    def _names_the_company(cls, patterns: tuple[str, ...]) -> tuple[str, ...]:
        """Refuse a company pattern with no ``company`` group to read."""
        for pattern in patterns:
            if "company" not in re.compile(pattern).groupindex:
                message = f"pattern {pattern!r} has no group named 'company'"
                raise ValueError(message)
        return patterns

    @cached_property
    def company_subjects(self) -> tuple[re.Pattern[str], ...]:
        """The company patterns, compiled once, case-insensitive."""
        return tuple(
            re.compile(pattern, re.IGNORECASE) for pattern in self.company_subject_patterns
        )

    @cached_property
    def work_subjects(self) -> tuple[re.Pattern[str], ...]:
        """The work-subject patterns, compiled once, case-insensitive."""
        return tuple(re.compile(pattern, re.IGNORECASE) for pattern in self.work_subject_patterns)
