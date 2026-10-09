"""What Threadline decides for itself, after the assistant has judged.

The assistant reads conversations; it does not keep a calendar and it does not
know what the owner corrected by hand. Four decisions are therefore taken here,
in this order:

1. **Gone quiet** is a matter of dates, not of reading: the owner wrote last,
   the other person had replied at least once before, and nothing came back for
   :data:`GONE_QUIET_AFTER_DAYS` days. A first message that was never answered
   stays "contacted, no reply yet", and a meeting or a process under way is left
   alone, because waiting is what those look like while they run.
2. **The owner's corrections win.** Anything he set by hand survives, whatever
   the assistant concluded; everything he did not set still updates.
3. **A missing due date** is filled in — today when the owner owes the next
   move, five working days after the last contact when they do. It comes after
   the corrections, so it follows who the owner says owes the move, and a date
   he set himself is never replaced. "Today" and "working day" are the owner's:
   read in their time zone, skipping their weekend (see :class:`OwnerCalendar`).
4. **Low confidence** or an unsure verdict sends the person to the review list
   instead of the main table.

A noise verdict skips all four: the person is dropped. The exception is a person
the owner has already judged himself. That person is kept, goes through the same
four steps, and is always sent to the review list, so the disagreement between
the owner and the assistant is put to the owner instead of being settled for him.

Every function is pure: the current moment is passed in, never read.
"""

from __future__ import annotations

from calendar import Day
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, tzinfo
from decimal import Decimal

from tracker.domain.enums import ContactStatus, Relevance, Signal, WaitingOn
from tracker.shared.constants.assessment import (
    FOLLOW_UP_AFTER_WORKING_DAYS,
    GONE_QUIET_AFTER_DAYS,
    REVIEW_THRESHOLD,
)
from tracker.shared.errors import ValidationFailedError

#: Statuses the date rule never touches. A conversation the assistant read as
#: finished does not come back to life because nobody wrote for ten days, and
#: neither an agreed meeting nor a process (interviews, a deal, due diligence) waiting on a
#: decision is "gone quiet" — silence is what those look like while they run.
_DATE_RULE_NEVER_OVERRIDES = frozenset(
    {
        ContactStatus.CLOSED,
        ContactStatus.MEETING_PLANNED,
        ContactStatus.IN_PROCESS,
    }
)


@dataclass(frozen=True, slots=True)
class OwnerCalendar:
    """What "today" and "a working day" mean for the owner.

    Attributes:
        zone: The owner's time zone, in which a moment becomes a date.
        weekend: The days of the week that are not working days.
    """

    zone: tzinfo
    weekend: frozenset[Day]

    def __post_init__(self) -> None:
        """Refuse a week with no working day, which no date could ever reach.

        Raises:
            ValidationFailedError: If every day of the week is a day off.
        """
        if len(self.weekend) >= len(Day):
            message = "a week needs at least one working day"
            raise ValidationFailedError(message)

    def day_of(self, moment: datetime) -> date:
        """Return the owner's date at a given instant.

        Args:
            moment: A timezone-aware instant.

        Returns:
            The date on the owner's calendar at that instant.
        """
        return moment.astimezone(self.zone).date()


@dataclass(frozen=True, slots=True)
class VerdictValues:
    """The assistant's answer about one person, free of any file format."""

    relevance: Relevance
    person_type: str
    status: ContactStatus
    waiting_on: WaitingOn
    signal: Signal
    confidence: Decimal
    next_action: str | None = None
    due_date: date | None = None
    summary: str | None = None
    organisation_name: str | None = None
    role_title: str | None = None


@dataclass(frozen=True, slots=True)
class ContactTiming:
    """When a person last wrote, and when the owner last wrote to them."""

    last_message_at: datetime | None = None
    last_inbound_at: datetime | None = None
    last_outbound_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class OwnerCorrections:
    """What the owner set by hand. Any value here beats the assessment."""

    status: ContactStatus | None = None
    waiting_on: WaitingOn | None = None
    next_action: str | None = None
    due_date: date | None = None
    person_type: str | None = None


@dataclass(frozen=True, slots=True)
class AssessedState:
    """What Threadline will store and show for one person."""

    status: ContactStatus
    waiting_on: WaitingOn
    signal: Signal
    confidence: Decimal
    person_type: str
    next_action: str | None
    due_date: date | None
    summary: str | None
    is_noise: bool
    needs_review: bool


def has_gone_quiet(timing: ContactTiming, now: datetime) -> bool:
    """Say whether the owner's last message has been left unanswered too long.

    Args:
        timing: When each side last wrote.
        now: The current instant.

    Returns:
        ``True`` when the owner wrote last and :data:`GONE_QUIET_AFTER_DAYS`
        days or more have passed since.
    """
    last_outbound = timing.last_outbound_at
    if last_outbound is None:
        return False
    # Never having had a reply is not a conversation that went quiet: it is one
    # that never started. That is "contacted, no reply yet", and calling it
    # gone quiet hides the difference between being ignored and being dropped.
    if timing.last_inbound_at is None:
        return False
    if timing.last_inbound_at >= last_outbound:
        return False
    return (now - last_outbound) >= timedelta(days=GONE_QUIET_AFTER_DAYS)


def add_working_days(start: date, working_days: int, weekend: frozenset[Day]) -> date:
    """Move a date forward by whole working days, skipping the owner's weekend.

    Args:
        start: The date to count from.
        working_days: How many working days to add. Zero or less returns
            ``start`` unchanged.
        weekend: The days that are not working days. It must leave at least
            one working day, as :class:`OwnerCalendar` guarantees.

    Returns:
        The resulting date, which is never a weekend day when ``working_days``
        is positive.
    """
    moved = start
    remaining = working_days
    while remaining > 0:
        moved += timedelta(days=1)
        if moved.weekday() not in weekend:
            remaining -= 1
    return moved


def follow_up_date(
    waiting_on: WaitingOn,
    timing: ContactTiming,
    now: datetime,
    calendar: OwnerCalendar,
) -> date | None:
    """Work out when a person should be chased, when the assistant gave no date.

    Args:
        waiting_on: Who owes the next move.
        timing: When each side last wrote.
        now: The current instant.
        calendar: The owner's time zone and weekend.

    Returns:
        The date to act on, on the owner's calendar, or ``None`` when nobody
        owes anything.
    """
    if waiting_on is WaitingOn.NOBODY:
        return None
    today = calendar.day_of(now)
    if waiting_on is WaitingOn.ME:
        return today
    last_contact = calendar.day_of(timing.last_message_at) if timing.last_message_at else today
    return add_working_days(last_contact, FOLLOW_UP_AFTER_WORKING_DAYS, calendar.weekend)


def needs_review(values: VerdictValues) -> bool:
    """Say whether the owner has to be asked about this person.

    Args:
        values: The assistant's answer.

    Returns:
        ``True`` when the verdict is unsure or its confidence is below
        :data:`REVIEW_THRESHOLD`.
    """
    return values.relevance is Relevance.UNSURE or values.confidence < REVIEW_THRESHOLD


def decide(
    values: VerdictValues,
    timing: ContactTiming,
    corrections: OwnerCorrections,
    now: datetime,
    calendar: OwnerCalendar,
    *,
    kept_by_owner: bool = False,
) -> AssessedState:
    """Turn one verdict into the state Threadline stores.

    Args:
        values: The assistant's answer about the person.
        timing: When each side last wrote.
        corrections: What the owner set by hand.
        now: The current instant.
        calendar: The owner's time zone and weekend.
        kept_by_owner: Whether the owner has already judged this person, so a
            noise verdict keeps them and asks instead of dropping them.

    Returns:
        The state to store, with the owner's corrections already applied. A
        noise verdict about a person the owner has not judged comes back as
        the assistant gave it, because that person is dropped.
    """
    state = AssessedState(
        status=values.status,
        waiting_on=values.waiting_on,
        signal=values.signal,
        confidence=values.confidence,
        person_type=values.person_type,
        next_action=values.next_action,
        due_date=values.due_date,
        summary=values.summary,
        is_noise=values.relevance is Relevance.NOISE,
        needs_review=needs_review(values),
    )
    if state.is_noise and not kept_by_owner:
        return state
    if state.is_noise:
        state = replace(state, needs_review=True)
    state = _apply_gone_quiet(state, timing, now)
    # The owner's corrections come before the date is filled in: a date worked
    # out for "waiting on them" would be wrong for a person the owner says is
    # waiting on him. An owner-set due date is already on the state by then, so
    # it is never replaced.
    state = _apply_corrections(state, corrections)
    return _fill_due_date(state, timing, now, calendar)


def _apply_gone_quiet(state: AssessedState, timing: ContactTiming, now: datetime) -> AssessedState:
    """Set the status by date when the owner's last message went unanswered."""
    if state.status in _DATE_RULE_NEVER_OVERRIDES or not has_gone_quiet(timing, now):
        return state
    return replace(state, status=ContactStatus.GONE_QUIET, waiting_on=WaitingOn.THEM)


def _fill_due_date(
    state: AssessedState,
    timing: ContactTiming,
    now: datetime,
    calendar: OwnerCalendar,
) -> AssessedState:
    """Give the person a date to act on when the assistant left it out."""
    if state.due_date is not None:
        return state
    return replace(state, due_date=follow_up_date(state.waiting_on, timing, now, calendar))


def _apply_corrections(state: AssessedState, corrections: OwnerCorrections) -> AssessedState:
    """Put the owner's manual values back over the assessment's."""
    return replace(
        state,
        status=corrections.status or state.status,
        waiting_on=corrections.waiting_on or state.waiting_on,
        next_action=corrections.next_action or state.next_action,
        due_date=corrections.due_date or state.due_date,
        person_type=corrections.person_type or state.person_type,
    )
