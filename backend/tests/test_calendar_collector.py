"""The Microsoft calendar as a source: meetings with people, and nothing else."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
import respx
from pydantic import SecretStr

from tests.assessment_world import make_message, make_person, make_thread
from tests.conftest import JOB_SEARCH_RULES, TEST_ENCRYPTION_KEY, FakeSupabaseClient
from tests.test_microsoft import mock_renewal
from tracker.domain.enums import Channel, Direction
from tracker.domain.models import Organisation, PersonIdentity
from tracker.infrastructure.secret_store import MICROSOFT_REFRESH_TOKEN, SecretStore
from tracker.repositories import Repositories
from tracker.services.collection.calendar_collector import CalendarCollector
from tracker.shared.clock import FixedClock
from tracker.shared.config import Settings
from tracker.shared.constants.collection import MICROSOFT_GRAPH_URL

CALENDAR_URL = f"{MICROSOFT_GRAPH_URL}/me/calendarView"
OWNER = "sam.rivera@mailbox.example"
SHARED_CALENDAR = "c_0000example@group.calendar.google.com"


def graph_event(
    event_id: str,
    *,
    subject: str = "Operations Associate - Intro Call",
    organizer: tuple[str, str] = ("hanna.keller@northwind.example", "Hanna Keller"),
    attendees: tuple[tuple[str, str], ...] = ((OWNER, "Sam"),),
    changed: str = "2026-09-15T10:00:00Z",
    cancelled: bool = False,
    ical_uid: str | None = None,
    is_organizer: bool = False,
) -> dict[str, Any]:
    """Build one made-up calendar event as Graph returns it."""
    return {
        "id": event_id,
        "iCalUId": ical_uid or f"uid-{event_id}",
        "subject": subject,
        "start": {"dateTime": "2026-09-24T09:00:00.0000000", "timeZone": "UTC"},
        "end": {"dateTime": "2026-09-24T09:45:00.0000000", "timeZone": "UTC"},
        "organizer": {"emailAddress": {"address": organizer[0], "name": organizer[1]}},
        "attendees": [
            {"emailAddress": {"address": address, "name": name}} for address, name in attendees
        ],
        "isCancelled": cancelled,
        "isOrganizer": is_organizer,
        "responseStatus": {"response": "accepted"},
        "createdDateTime": "2026-09-14T10:00:00Z",
        "lastModifiedDateTime": changed,
    }


def collect(
    repositories: Repositories,
    settings: Settings,
    clock: FixedClock,
    events: list[dict[str, Any]],
) -> respx.Route:
    """Run the calendar collector against a made-up calendar."""
    SecretStore(repositories.app_secrets, SecretStr(TEST_ENCRYPTION_KEY), clock).put_secret(
        MICROSOFT_REFRESH_TOKEN, "old-long-lived-key"
    )
    with respx.mock:
        mock_renewal()
        route = respx.get(CALENDAR_URL).mock(
            return_value=httpx.Response(200, json={"value": events})
        )
        CalendarCollector(repositories, settings, clock, JOB_SEARCH_RULES).collect()
    return route


def rows(client: FakeSupabaseClient, table: str) -> list[dict[str, Any]]:
    """Read one table of the in-memory database."""
    return client.tables.get(table, [])


def test_a_meeting_is_filed_under_the_person_by_their_e_mail_address(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    collect(repositories, settings, clock, [graph_event("e-1")])

    (thread,) = rows(fake_client, "conversations")
    (identity,) = rows(fake_client, "person_identities")
    (message,) = rows(fake_client, "messages")
    assert thread["channel"] == Channel.CALENDAR.value
    assert str(thread["meeting_at"]).startswith("2026-09-24T09:00")
    assert thread["subject"] == "Operations Associate - Intro Call"
    assert identity["channel"] == Channel.EMAIL.value
    assert identity["identifier"] == "hanna.keller@northwind.example"
    assert message["direction"] == Direction.INBOUND.value
    assert "Thu 24 Sep 2026, 09:00–09:45 (UTC)" in message["body"]
    assert "Your answer: accepted" in message["body"]


def test_an_event_with_only_the_owner_is_never_stored(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    personal = graph_event("e-gym", subject="Gym", organizer=(OWNER, "Sam"), attendees=())

    collect(repositories, settings, clock, [personal])

    assert rows(fake_client, "conversations") == []
    assert rows(fake_client, "people") == []


def test_an_interview_the_owner_typed_himself_is_filed_under_its_company(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    entry = graph_event(
        "e-acme",
        subject="Video interview - Sam and Acme",
        organizer=(OWNER, "Sam"),
        attendees=(),
        is_organizer=True,
    )

    collect(repositories, settings, clock, [entry])

    (thread,) = rows(fake_client, "conversations")
    (person,) = rows(fake_client, "people")
    (organisation,) = rows(fake_client, "organisations")
    assert str(thread["meeting_at"]).startswith("2026-09-24T09:00")
    assert person["full_name"] == "Acme"
    assert organisation["name"] == "Acme"
    assert person["organisation_id"] == organisation["id"]


def test_a_preparation_block_for_an_interview_stays_private(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    prep = graph_event(
        "e-prep",
        subject="Prep for Acme interview",
        organizer=(OWNER, "Sam"),
        attendees=(),
        is_organizer=True,
    )

    collect(repositories, settings, clock, [prep])

    assert rows(fake_client, "conversations") == []


def test_a_shared_calendar_organiser_gives_way_to_the_people_invited(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    event = graph_event(
        "e-orbita",
        organizer=("c_0001example@group.calendar.google.com", "Orbita Interview Calendar"),
        attendees=((OWNER, "Sam"), ("lena.h@orbita.example", "Lena Hoffman-Adler")),
    )

    collect(repositories, settings, clock, [event])

    names = {row["full_name"] for row in rows(fake_client, "people")}
    assert names == {"Lena Hoffman-Adler"}


def test_a_moved_meeting_adds_a_message_and_a_second_run_changes_nothing(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    collect(repositories, settings, clock, [graph_event("e-1")])
    moved = graph_event("e-1", changed="2026-09-16T10:00:00Z", cancelled=True)

    collect(repositories, settings, clock, [moved])
    collect(repositories, settings, clock, [moved])

    assert len(rows(fake_client, "conversations")) == 1
    bodies = [row["body"] for row in rows(fake_client, "messages")]
    assert len(bodies) == 2
    assert any("This meeting was cancelled." in body for body in bodies)
    assert rows(fake_client, "conversations")[0]["meeting_at"] is None


def test_only_meeting_details_are_asked_for_never_the_description(
    repositories: Repositories,
    settings: Settings,
    clock: FixedClock,
) -> None:
    route = collect(repositories, settings, clock, [graph_event("e-1")])

    fields = route.calls[0].request.url.params["$select"].split(",")
    assert "body" not in fields
    assert "bodyPreview" not in fields
    assert route.calls[0].request.headers["Prefer"] == 'outlook.timezone="UTC"'


def test_a_meeting_organised_by_a_shared_calendar_joins_the_person_who_sent_its_invitation(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    """The event names only the owner; the e-mailed invitation named Hanna."""
    hanna = make_person("Hanna Keller")
    repositories.people.bulk_upsert([hanna])
    repositories.person_identities.bulk_upsert(
        [
            PersonIdentity(
                person_id=hanna.id,
                channel=Channel.EMAIL,
                identifier="hanna.keller@northwind.example",
                display_name="Hanna Keller",
            )
        ]
    )
    invitation = make_thread(hanna, source="t-invite", channel=Channel.EMAIL)
    repositories.conversations.bulk_upsert([invitation])
    repositories.messages.bulk_upsert(
        [
            make_message(
                invitation, direction=Direction.INBOUND, sent_at=clock.now(), body="Invitation"
            ).model_copy(update={"sender_identifier": SHARED_CALENDAR})
        ]
    )
    event = graph_event(
        "e-northwind",
        organizer=(SHARED_CALENDAR, "Interviews"),
        attendees=((OWNER, "Sam"), (SHARED_CALENDAR, "Interviews")),
    )

    collect(repositories, settings, clock, [event])

    meeting = next(
        row for row in rows(fake_client, "conversations") if row["channel"] == "calendar"
    )
    assert meeting["person_id"] == str(hanna.id)
    assert not str(meeting["subject"]).startswith("[group]")
    assert len(rows(fake_client, "people")) == 1


def _acme_entry() -> dict[str, Any]:
    """SmartRecruiters' invitation, imported as an entry the owner organises alone."""
    return graph_event(
        "e-acme",
        subject="Video interview - Sam and Acme",
        organizer=(OWNER, "Sam"),
        attendees=(),
        is_organizer=True,
    )


def _on_record(repositories: Repositories, name: str, identifier: str, company: str) -> UUID:
    """Store one person at a company, as an earlier mailbox run would have."""
    organisation = Organisation(name=company)
    person = make_person(name).model_copy(update={"organisation_id": organisation.id})
    repositories.organisations.bulk_upsert([organisation])
    repositories.people.bulk_upsert([person])
    repositories.person_identities.bulk_upsert(
        [PersonIdentity(person_id=person.id, channel=Channel.EMAIL, identifier=identifier)]
    )
    return person.id


def test_an_own_interview_entry_joins_the_company_record_its_mail_created(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    record = _on_record(
        repositories, "Acme Hiring Team", "no-reply@acmecareers.example#acme", "Acme"
    )

    collect(repositories, settings, clock, [_acme_entry()])

    (meeting,) = rows(fake_client, "conversations")
    assert meeting["person_id"] == str(record)
    assert len(rows(fake_client, "people")) == 1
    assert not any(
        "own-calendar" in str(row["identifier"]) for row in rows(fake_client, "person_identities")
    )


def test_an_own_interview_entry_joins_the_one_recruiter_of_that_company(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    chloe = _on_record(repositories, "Chloe Garner", "chloe.garner@acmegroup.example", "Acmegroup")

    collect(repositories, settings, clock, [_acme_entry()])

    (meeting,) = rows(fake_client, "conversations")
    assert meeting["person_id"] == str(chloe)
    assert len(rows(fake_client, "people")) == 1


def test_an_own_interview_entry_for_a_company_nobody_is_at_gets_its_own_record(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    other = _on_record(
        repositories, "Hanna Keller", "hanna.keller@northwind.example", "Northwind AI"
    )

    collect(repositories, settings, clock, [_acme_entry()])

    (meeting,) = rows(fake_client, "conversations")
    assert meeting["person_id"] != str(other)
    identifiers = {str(row["identifier"]) for row in rows(fake_client, "person_identities")}
    assert "own-calendar#acme" in identifiers


# --- The owner's settings (Plan 18) -------------------------------------------

ANONYMOUS_OWNER = "jd123@inbox.example"


def test_meeting_times_are_shown_in_the_owners_zone_and_labelled_with_it(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
) -> None:
    rome = FixedClock(datetime(2026, 9, 18, 7, 0, tzinfo=UTC), ZoneInfo("Europe/Rome"))

    collect(repositories, settings, rome, [graph_event("e-1")])

    (message,) = rows(fake_client, "messages")
    assert "Thu 24 Sep 2026, 11:00–11:45 (Europe/Rome)" in message["body"]
    assert "(UTC)" not in message["body"]


def _entry_by_anonymous_owner() -> dict[str, Any]:
    return graph_event(
        "e-acme",
        subject="Video interview - Jordan Doe and Acme",
        organizer=(ANONYMOUS_OWNER, "JD"),
        attendees=(),
        is_organizer=True,
    )


def test_the_configured_display_name_is_left_out_of_the_company_name(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    named = settings.model_copy(
        update={
            "owner_email_addresses": (ANONYMOUS_OWNER,),
            "owner_display_name": "Jordan Doe",
        }
    )

    collect(repositories, named, clock, [_entry_by_anonymous_owner()])

    (person,) = rows(fake_client, "people")
    assert person["full_name"] == "Acme"


def test_without_a_display_name_an_address_that_spells_none_cannot_help(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    settings: Settings,
    clock: FixedClock,
) -> None:
    unnamed = settings.model_copy(update={"owner_email_addresses": (ANONYMOUS_OWNER,)})

    collect(repositories, unnamed, clock, [_entry_by_anonymous_owner()])

    (person,) = rows(fake_client, "people")
    assert person["full_name"] == "Jordan Doe Acme"
