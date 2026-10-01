"""Closed sets of values, mirroring the database enums one for one.

Every member's value is exactly the label stored in PostgreSQL, so a model can
be written straight to the database and read back without translation. Changing
a member here requires a new migration under ``supabase/migrations/``.
"""

from __future__ import annotations

from enum import StrEnum


class Channel(StrEnum):
    """Where a message was exchanged."""

    LINKEDIN = "linkedin"
    EMAIL = "email"
    CALENDAR = "calendar"


class Direction(StrEnum):
    """Who sent a message, relative to the owner."""

    INBOUND = "inbound"
    OUTBOUND = "outbound"


class Relevance(StrEnum):
    """Whether something belongs to what the owner tracks."""

    RELEVANT = "relevant"
    NOISE = "noise"
    UNSURE = "unsure"


class RelevanceDecidedBy(StrEnum):
    """What decided a relevance value."""

    RULE = "rule"
    AI = "ai"
    OWNER = "owner"


class ContactStatus(StrEnum):
    """Where a conversation with a person stands."""

    CONTACTED_NO_REPLY = "contacted_no_reply"
    IN_CONVERSATION = "in_conversation"
    MEETING_PLANNED = "meeting_planned"
    IN_PROCESS = "in_process"
    GONE_QUIET = "gone_quiet"
    CLOSED = "closed"


class WaitingOn(StrEnum):
    """Who owes the next move."""

    ME = "me"
    THEM = "them"
    NOBODY = "nobody"


class Signal(StrEnum):
    """How warm the conversation reads."""

    POSITIVE = "positive"
    NEUTRAL = "neutral"
    COLD = "cold"


class ReviewKind(StrEnum):
    """What a review item asks the owner."""

    RELEVANCE = "relevance"
    SAME_PERSON = "same_person"


class ReviewAnswer(StrEnum):
    """The owner's answer to a review item."""

    YES = "yes"
    NO = "no"


class RunStatus(StrEnum):
    """Outcome of a daily run or of one of its steps."""

    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class RunStep(StrEnum):
    """The steps a daily run is made of."""

    COLLECT_LINKEDIN = "collect_linkedin"
    COLLECT_EMAIL = "collect_email"
    COLLECT_CALENDAR = "collect_calendar"
    ASSESS = "assess"
    SUMMARY_EMAIL = "summary_email"


class RunTrigger(StrEnum):
    """What started a run."""

    CLOUD = "cloud"
    MAC = "mac"
    MANUAL = "manual"
    #: The scheduled daily run on GitHub Actions, or "Run workflow" there.
    GITHUB = "github"
    #: An extra run between two mornings: new messages only, no summary e-mail.
    REFRESH = "refresh"


class OrganisationKind(StrEnum):
    """What kind of organisation a person belongs to."""

    STARTUP = "startup"
    VC_FUND = "vc_fund"
    OTHER = "other"
