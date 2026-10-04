"""Entities, one per database table, plus the read model behind the dashboard.

These models are the only shape data travels in between layers: repositories
return them, services consume them, the command line prints them. Identifiers
are generated in Python so a record can be written, re-written and cleared with
the same primary key, which is what makes every write idempotent.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Final, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tracker.domain.categories import UNKNOWN_CATEGORY_KEY, Category, CategoryKey, ColourSlot
from tracker.domain.enums import (
    Channel,
    ContactStatus,
    Direction,
    OrganisationKind,
    Relevance,
    RelevanceDecidedBy,
    ReviewAnswer,
    ReviewKind,
    RunStatus,
    RunStep,
    RunTrigger,
    Signal,
    WaitingOn,
)

#: Columns the database fills in itself; never sent on a write when unset.
SERVER_MANAGED_FIELDS: Final[frozenset[str]] = frozenset({"created_at", "updated_at"})


class Record(BaseModel):
    """Fields every table shares."""

    model_config = ConfigDict(extra="ignore")

    id: UUID = Field(default_factory=uuid4)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_row(self) -> dict[str, Any]:
        """Render the record as a JSON-safe row for the database client.

        Returns:
            A dictionary with the server-managed timestamps dropped when unset,
            so the database applies its own defaults.
        """
        row = self.model_dump(mode="json")
        for field_name in SERVER_MANAGED_FIELDS:
            if row.get(field_name) is None:
                row.pop(field_name, None)
        return row


class Organisation(Record):
    """A company or fund a person belongs to."""

    name: str
    kind: OrganisationKind | None = None
    email_domain: str | None = None


class Person(Record):
    """Someone the owner is in touch with about the job search."""

    full_name: str
    person_type: CategoryKey = UNKNOWN_CATEGORY_KEY
    role_title: str | None = None
    organisation_id: UUID | None = None
    relevance: Relevance = Relevance.UNSURE


class PersonIdentity(Record):
    """One address a person can be reached at on one channel."""

    person_id: UUID
    channel: Channel
    identifier: str
    display_name: str | None = None

    @model_validator(mode="after")
    def _normalise_identifier(self) -> Self:
        """Lower-case e-mail identifiers so the unique key cannot be fooled by case."""
        if self.channel is Channel.EMAIL:
            self.identifier = self.identifier.strip().lower()
        return self


class Conversation(Record):
    """One thread on one channel."""

    person_id: UUID | None = None
    channel: Channel
    source_conversation_id: str
    subject: str | None = None
    relevance: Relevance = Relevance.UNSURE
    relevance_decided_by: RelevanceDecidedBy | None = None
    first_message_at: datetime | None = None
    last_message_at: datetime | None = None
    last_inbound_at: datetime | None = None
    last_outbound_at: datetime | None = None
    meeting_at: datetime | None = None

    @model_validator(mode="after")
    def _forget_subject_of_noise(self) -> Self:
        """Keep no subject for a thread judged noise.

        A thread that is not part of the job search is remembered only by its
        identifier and its decision, so it is never processed twice and nothing
        private is stored.
        """
        if self.relevance is Relevance.NOISE:
            self.subject = None
        return self


class Message(Record):
    """One message inside a conversation."""

    conversation_id: UUID
    source_message_id: str
    direction: Direction
    sent_at: datetime
    sender_identifier: str | None = None
    body: str | None = None


class PersonState(Record):
    """The assessment's current view of one person."""

    person_id: UUID
    status: ContactStatus
    waiting_on: WaitingOn
    next_action: str | None = None
    due_date: date | None = None
    summary: str | None = None
    signal: Signal = Signal.NEUTRAL
    confidence: Decimal = Field(ge=Decimal(0), le=Decimal(1))
    assessed_at: datetime
    assessed_through: datetime


class PersonOverride(Record):
    """What the owner set by hand. Any value here beats the assessment."""

    person_id: UUID
    status: ContactStatus | None = None
    waiting_on: WaitingOn | None = None
    next_action: str | None = None
    due_date: date | None = None
    person_type: CategoryKey | None = None
    note: str | None = None


class PersonNote(Record):
    """A note the owner typed on a person's page of the dashboard.

    The note's text is deliberately not a field. The notes are for the
    dashboard only, and these models are the only shape data travels in between
    layers, so a note's text can reach neither the assessment nor the summary.
    """

    person_id: UUID


class ReviewItem(Record):
    """A yes/no question for the owner."""

    kind: ReviewKind
    question: str
    person_id: UUID | None = None
    conversation_id: UUID | None = None
    other_person_id: UUID | None = None
    answer: ReviewAnswer | None = None
    answered_at: datetime | None = None


class RunLog(Record):
    """One daily run."""

    started_at: datetime
    finished_at: datetime | None = None
    status: RunStatus
    trigger: RunTrigger


class RunStepLog(Record):
    """One step of a daily run. Holds counts and error codes, never content."""

    run_id: UUID
    step: RunStep
    status: RunStatus
    items_found: int | None = None
    items_new: int | None = None
    error_code: str | None = None
    error_detail: str | None = None


class AppSecret(Record):
    """An encrypted value the jobs need between runs, such as the mailbox key."""

    name: str
    encrypted_value: str
    rotated_at: datetime


class AppSettings(Record):
    """The one row of owner settings the database itself needs.

    Attributes:
        singleton: Always ``True``; the database allows exactly one row.
        time_zone: The owner's IANA time zone, which decides the database's
            "today" (see ``public.owner_today()``).
        preset: The preset the owner chose with ``tracker profile choose``;
            ``None`` means none was chosen.
    """

    singleton: bool = True
    time_zone: str
    preset: str | None = None


class CategoryRecord(Record):
    """One row of ``categories``: the owner's category, as the database holds it.

    Attributes:
        archived_at: When the owner removed the category while people still
            had it. An archived category still labels those people but is no
            longer offered to the AI or in the dashboard's choices.
    """

    key: CategoryKey
    label: str
    group_label: str
    description: str = ""
    colour: ColourSlot
    sort_order: int = 0
    archived_at: datetime | None = None

    @classmethod
    def of(cls, category: Category) -> CategoryRecord:
        """Build the row for a category that is in use.

        Args:
            category: The category.

        Returns:
            A row with no archive date.
        """
        return cls(**category.model_dump())

    def to_category(self) -> Category:
        """Return the category this row holds, without its bookkeeping."""
        return Category(
            key=self.key,
            label=self.label,
            group_label=self.group_label,
            description=self.description,
            colour=self.colour,
            sort_order=self.sort_order,
        )


class CategorySuggestion(Record):
    """One row of ``category_suggestions``: a category the chosen preset suggests."""

    key: CategoryKey
    label: str
    group_label: str
    description: str = ""
    colour: ColourSlot
    sort_order: int = 0


class StatusLabel(Record):
    """One row of ``status_labels``: what the dashboard calls one stage."""

    status: ContactStatus
    label: str


class PersonOverview(BaseModel):
    """One row of the ``people_overview`` view: the dashboard's read model."""

    model_config = ConfigDict(extra="ignore")

    person_id: UUID
    full_name: str
    organisation_name: str | None = None
    person_type: CategoryKey
    role_title: str | None = None
    status: ContactStatus | None = None
    waiting_on: WaitingOn | None = None
    next_action: str | None = None
    due_date: date | None = None
    summary: str | None = None
    signal: Signal | None = None
    confidence: Decimal | None = None
    assessed_at: datetime | None = None
    last_contact_at: datetime | None = None
    channels: tuple[Channel, ...] = ()
    message_count: int = 0
    is_overdue: bool = False
    has_override: bool = False
    is_chase_due: bool = False
