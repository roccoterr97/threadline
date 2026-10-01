"""Domain models carry the rules the database also enforces."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from tracker.domain.enums import Channel, ContactStatus, Relevance, WaitingOn
from tracker.domain.models import Conversation, Organisation, PersonIdentity, PersonState


def test_row_drops_timestamps_the_database_fills_in() -> None:
    row = Organisation(name="Northwind Robotics").to_row()

    assert "created_at" not in row
    assert "updated_at" not in row
    assert row["name"] == "Northwind Robotics"


def test_row_is_json_safe() -> None:
    row = Organisation(name="Northwind Robotics").to_row()

    assert isinstance(row["id"], str)


def test_email_identifiers_are_lowercased() -> None:
    identity = PersonIdentity(
        person_id=uuid4(),
        channel=Channel.EMAIL,
        identifier="  Anna.Vermeer@Example.COM ",
    )

    assert identity.identifier == "anna.vermeer@example.com"


def test_linkedin_identifiers_keep_their_case() -> None:
    identity = PersonIdentity(
        person_id=uuid4(),
        channel=Channel.LINKEDIN,
        identifier="https://www.linkedin.com/in/AnnaVermeer",
    )

    assert identity.identifier == "https://www.linkedin.com/in/AnnaVermeer"


def test_a_thread_judged_noise_keeps_no_subject() -> None:
    conversation = Conversation(
        channel=Channel.EMAIL,
        source_conversation_id="thread-1",
        subject="Your weekly newsletter",
        relevance=Relevance.NOISE,
    )

    assert conversation.subject is None


def test_a_relevant_thread_keeps_its_subject() -> None:
    conversation = Conversation(
        channel=Channel.EMAIL,
        source_conversation_id="thread-2",
        subject="Interview follow-up",
        relevance=Relevance.RELEVANT,
    )

    assert conversation.subject == "Interview follow-up"


def test_confidence_outside_zero_to_one_is_refused() -> None:
    with pytest.raises(ValidationError):
        PersonState(
            person_id=uuid4(),
            status=ContactStatus.IN_CONVERSATION,
            waiting_on=WaitingOn.ME,
            confidence=Decimal("1.5"),
            assessed_at=datetime(2026, 9, 18, tzinfo=UTC),
            assessed_through=datetime(2026, 9, 17, tzinfo=UTC),
        )
