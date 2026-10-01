"""Builders for a small made-up world the assessment tests run against."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from tracker.domain.categories import UNKNOWN_CATEGORY, UNKNOWN_CATEGORY_KEY, ColourSlot
from tracker.domain.enums import (
    Channel,
    ContactStatus,
    Direction,
    Relevance,
    RelevanceDecidedBy,
    ReviewAnswer,
    ReviewKind,
    Signal,
    WaitingOn,
)
from tracker.domain.models import (
    CategoryRecord,
    Conversation,
    Message,
    Person,
    PersonOverride,
    PersonState,
    ReviewItem,
)
from tracker.domain.profile import Wording
from tracker.repositories import Repositories
from tracker.services.profile.loader import preset_path, read_profile

NOW = datetime(2026, 9, 18, 7, 0, tzinfo=UTC)

#: The owner's wording in this world: the job-search preset's.
WORDING: Wording = read_profile(preset_path("job_search")).wording

#: The owner's categories in this world: exactly what 0009_categories.sql seeds.
CATEGORIES: tuple[CategoryRecord, ...] = (
    CategoryRecord(
        key="startup",
        label="Startup",
        group_label="Startups",
        description=(
            "Someone who works at a startup: founder, executive, employee, in-house recruiter."
        ),
        colour=ColourSlot.VIOLET,
        sort_order=10,
    ),
    CategoryRecord(
        key="vc",
        label="Investor",
        group_label="Investors",
        description="Someone at a fund: talent or people partner, investor, platform team.",
        colour=ColourSlot.CYAN,
        sort_order=20,
    ),
    CategoryRecord(
        key="network",
        label="Network",
        group_label="Network",
        description=(
            "A friend, a former colleague, anyone who can introduce you rather than hire you."
        ),
        colour=ColourSlot.ORANGE,
        sort_order=30,
    ),
    CategoryRecord(**UNKNOWN_CATEGORY.model_dump()),
)


def moment(day: int, hour: int = 9) -> datetime:
    """A fixed instant in September 2026."""
    return datetime(2026, 9, day, hour, 0, tzinfo=UTC)


def make_person(
    name: str = "Anna Vermeer",
    *,
    relevance: Relevance = Relevance.RELEVANT,
    person_type: str = UNKNOWN_CATEGORY_KEY,
) -> Person:
    """One person."""
    return Person(full_name=name, relevance=relevance, person_type=person_type)


def make_thread(
    person: Person,
    *,
    source: str = "thread-1",
    channel: Channel = Channel.LINKEDIN,
    relevance: Relevance = Relevance.UNSURE,
    decided_by: RelevanceDecidedBy | None = None,
    last_inbound: datetime | None = None,
    last_outbound: datetime | None = None,
    subject: str | None = None,
    meeting_at: datetime | None = None,
) -> Conversation:
    """One thread belonging to a person."""
    moments = [value for value in (last_inbound, last_outbound) if value is not None]
    return Conversation(
        person_id=person.id,
        channel=channel,
        source_conversation_id=source,
        subject=subject,
        relevance=relevance,
        relevance_decided_by=decided_by,
        first_message_at=min(moments) if moments else None,
        last_message_at=max(moments) if moments else None,
        last_inbound_at=last_inbound,
        last_outbound_at=last_outbound,
        meeting_at=meeting_at,
    )


def make_message(
    thread: Conversation,
    *,
    direction: Direction,
    sent_at: datetime,
    body: str,
    source: str = "message-1",
) -> Message:
    """One message inside a thread."""
    return Message(
        conversation_id=thread.id,
        source_message_id=source,
        direction=direction,
        sent_at=sent_at,
        body=body,
    )


def make_state(
    person: Person,
    *,
    assessed_through: datetime,
    assessed_at: datetime | None = None,
    status: ContactStatus = ContactStatus.IN_CONVERSATION,
) -> PersonState:
    """A previous assessment of a person."""
    return PersonState(
        person_id=person.id,
        status=status,
        waiting_on=WaitingOn.THEM,
        next_action="Wait for the reply",
        summary="Talking about a role.",
        signal=Signal.NEUTRAL,
        confidence=Decimal("0.90"),
        assessed_at=assessed_at or assessed_through,
        assessed_through=assessed_through,
    )


def make_override(
    person: Person,
    *,
    status: ContactStatus | None = None,
    waiting_on: WaitingOn | None = None,
    next_action: str | None = None,
    due_date: date | None = None,
    person_type: str | None = None,
) -> PersonOverride:
    """A manual correction on a person."""
    return PersonOverride(
        person_id=person.id,
        status=status,
        waiting_on=waiting_on,
        next_action=next_action,
        due_date=due_date,
        person_type=person_type,
    )


def make_answer(
    person: Person,
    thread: Conversation | None = None,
    *,
    answer: ReviewAnswer = ReviewAnswer.NO,
    answered_at: datetime = NOW,
) -> ReviewItem:
    """A question the owner has already answered."""
    return ReviewItem(
        kind=ReviewKind.RELEVANCE,
        person_id=person.id,
        conversation_id=thread.id if thread else None,
        question=f"Is {person.full_name} part of your job search?",
        answer=answer,
        answered_at=answered_at,
    )


def seed(
    repositories: Repositories,
    *,
    people: list[Person] | None = None,
    threads: list[Conversation] | None = None,
    messages: list[Message] | None = None,
    states: list[PersonState] | None = None,
    overrides: list[PersonOverride] | None = None,
    review_items: list[ReviewItem] | None = None,
) -> None:
    """Write a made-up world into the in-memory database, with its categories."""
    repositories.categories.save(CATEGORIES)
    repositories.people.bulk_upsert(people or [])
    repositories.conversations.bulk_upsert(threads or [])
    repositories.messages.bulk_upsert(messages or [])
    repositories.person_states.bulk_upsert(states or [])
    repositories.person_overrides.bulk_upsert(overrides or [])
    repositories.review_items.bulk_upsert(review_items or [])


def verdict_payload(person_id: UUID, **overrides: object) -> dict[str, object]:
    """A complete, valid verdict for one person."""
    payload: dict[str, object] = {
        "person_id": str(person_id),
        "relevance": "relevant",
        "person_type": "startup",
        "organisation_name": "Northwind Robotics",
        "role_title": "Head of Talent",
        "status": "in_conversation",
        "waiting_on": "them",
        "next_action": "Wait for the interview slots",
        "due_date": "2026-09-24",
        "summary": "She is lining up a first call.",
        "signal": "positive",
        "confidence": 0.9,
    }
    payload.update(overrides)
    return payload


def verdict_file(batch_id: str, *verdicts: dict[str, object]) -> str:
    """The JSON text of a verdict file."""
    return json.dumps({"batch_id": batch_id, "verdicts": list(verdicts)})


def unknown_person_id() -> UUID:
    """An identifier that belongs to nobody."""
    return uuid4()
