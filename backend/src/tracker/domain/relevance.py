"""Rules that decide, without any AI, what still needs judging.

The cheapest verdict is the one nobody has to make. A thread already judged
noise stays noise, a question the owner answered is settled for good, and a
person nothing has happened to since the last assessment is skipped. "Something
happened" means a new message, a meeting that has now taken place, or a
"yes, this is part of my search". Only what is left goes to the assistant, and
it goes with the evidence these rules collected: did the owner ever reply, and
how many back-and-forths were there.

Every function here is pure: no clock, no database, no configuration.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from tracker.domain.enums import Relevance, RelevanceDecidedBy, ReviewAnswer


class PreDecision(StrEnum):
    """What the rules alone can conclude about a thread."""

    SETTLED_NOISE = "settled_noise"
    SETTLED_RELEVANT = "settled_relevant"
    NEEDS_AI = "needs_ai"


@dataclass(frozen=True, slots=True)
class ThreadEvidence:
    """What is known about one thread before anyone judges it."""

    relevance: Relevance
    decided_by: RelevanceDecidedBy | None = None
    owner_answer: ReviewAnswer | None = None
    inbound_count: int = 0
    outbound_count: int = 0


@dataclass(frozen=True, slots=True)
class PersonEvidence:
    """What is known about one person before anyone judges them.

    Attributes:
        relevance: The person's current relevance.
        answered_not_relevant: The owner said "no" about this person.
        last_message_at: The newest message in any live thread.
        assessed_through: The newest message the last assessment had read.
        assessed_at: When the last assessment was made.
        last_meeting_started_at: The start of the latest of this person's
            meetings that is already in the past. The caller works it out from
            its clock; nothing here reads the time.
        last_confirmed_at: When the owner last answered "yes, part of my job
            search" about this person or one of their threads.
    """

    relevance: Relevance
    answered_not_relevant: bool = False
    last_message_at: datetime | None = None
    assessed_through: datetime | None = None
    assessed_at: datetime | None = None
    last_meeting_started_at: datetime | None = None
    last_confirmed_at: datetime | None = None


def decide_thread(evidence: ThreadEvidence) -> PreDecision:
    """Decide a thread by rule where a rule is enough.

    Args:
        evidence: What is already known about the thread.

    Returns:
        The rule's conclusion, or :attr:`PreDecision.NEEDS_AI` when the thread
        has to be read.
    """
    if evidence.relevance is Relevance.NOISE:
        return PreDecision.SETTLED_NOISE
    if evidence.owner_answer is ReviewAnswer.NO:
        return PreDecision.SETTLED_NOISE
    if evidence.owner_answer is ReviewAnswer.YES:
        return PreDecision.SETTLED_RELEVANT
    if evidence.decided_by is RelevanceDecidedBy.OWNER:
        return PreDecision.SETTLED_RELEVANT
    return PreDecision.NEEDS_AI


def owner_has_replied(evidence: ThreadEvidence) -> bool:
    """Say whether the owner ever wrote in this thread.

    The owner's own messages are the strongest hint that a thread is real: he
    answers people, not newsletters.

    Args:
        evidence: What is already known about the thread.

    Returns:
        ``True`` when at least one message went out from the owner.
    """
    return evidence.outbound_count > 0


def exchange_count(evidence: ThreadEvidence) -> int:
    """Count the completed back-and-forths in a thread.

    One exchange is a message in each direction. Ten messages from one side and
    none from the other are not a conversation, and this count says so.

    Args:
        evidence: What is already known about the thread.

    Returns:
        How many times the thread turned around.
    """
    return min(evidence.inbound_count, evidence.outbound_count)


def needs_assessment(evidence: PersonEvidence) -> bool:
    """Decide whether a person should be sent to the assistant at all.

    Args:
        evidence: What is already known about the person.

    Returns:
        ``True`` when the person still has to be judged.
    """
    if evidence.answered_not_relevant:
        return False
    if evidence.relevance is Relevance.NOISE:
        return False
    if evidence.last_message_at is None:
        return False
    if evidence.assessed_through is None:
        return True
    if evidence.last_message_at > evidence.assessed_through:
        return True
    return _happened_since_assessment(evidence)


def _happened_since_assessment(evidence: PersonEvidence) -> bool:
    """Say whether something other than a message moved on since the last verdict.

    A meeting that took place turns "Meeting planned" stale even when nobody
    writes; the owner's "yes" is evidence the last verdict never saw. Both are
    measured against when the assessment was made, not against the last
    message it read, because neither is a message.
    """
    if evidence.assessed_at is None:
        return False
    moments = (evidence.last_meeting_started_at, evidence.last_confirmed_at)
    assessed_at = evidence.assessed_at
    return any(moment is not None and moment > assessed_at for moment in moments)
