"""What the assistant threw away as noise comes back when the owner shows it matters.

The owner's answers always win over the assistant's. Writing to somebody, or
somebody starting a new conversation that the rules do not call noise, sends the
assistant's noise back to be judged. Anything the owner decided himself (the
dashboard's "Not relevant", a "no" or a "yes", a correction) is never undone,
and a newsletter arriving in a thread that is already noise changes nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from tests.assessment_world import (
    make_answer,
    make_override,
    make_person,
    moment,
    seed,
    verdict_payload,
)
from tests.test_assessment_importer import build_chain, talkative_person
from tests.test_collectors import MAILBOX, collect_email
from tests.test_microsoft import graph_message
from tracker.domain.enums import (
    Channel,
    Direction,
    Relevance,
    RelevanceDecidedBy,
    ReviewAnswer,
)
from tracker.domain.models import Conversation, Message, Person, PersonIdentity
from tracker.domain.noise_return import (
    PersonRuling,
    ThreadRuling,
    person_ruled_out_by_assistant,
    thread_comes_back,
)
from tracker.repositories import Repositories
from tracker.schemas.assessment import parse_batch
from tracker.services.assessment.exporter import AssessmentExporter
from tracker.services.collection.models import RawConversation, RawMessage, RawParticipant
from tracker.services.collection.writer import ConversationWriter
from tracker.shared.clock import FixedClock
from tracker.shared.config import Settings

ADDRESS = "anna.vermeer@northwind.example"
KEY = (Channel.EMAIL, ADDRESS)
OWNER = "sam.rivera@mailbox.example"
THREAD = "t-1"


def raw_message(
    source: str,
    direction: Direction,
    day: int,
    body: str | None = "Made-up text.",
) -> RawMessage:
    """One collected message."""
    return RawMessage(
        source_message_id=source,
        sent_at=moment(day),
        direction=direction,
        sender_identifier=OWNER if direction is Direction.OUTBOUND else ADDRESS,
        body=body,
    )


def raw_thread(
    *messages: RawMessage,
    source: str = THREAD,
    relevance: Relevance = Relevance.UNSURE,
) -> RawConversation:
    """A collected thread with Anna in it."""
    return RawConversation(
        channel=Channel.EMAIL,
        source_conversation_id=source,
        subject="Made-up subject",
        relevance=relevance,
        participants=(RawParticipant(Channel.EMAIL, ADDRESS, "Anna Vermeer"),),
        messages=messages,
    )


def stored_thread(
    person: Person | None,
    *,
    relevance: Relevance = Relevance.NOISE,
    decided_by: RelevanceDecidedBy | None = RelevanceDecidedBy.AI,
    source: str = THREAD,
) -> Conversation:
    """A thread already in the database: one message in on the 12th, one out on the 13th."""
    return Conversation(
        person_id=person.id if person else None,
        channel=Channel.EMAIL,
        source_conversation_id=source,
        subject=None if relevance is Relevance.NOISE else "Made-up subject",
        relevance=relevance,
        relevance_decided_by=decided_by,
        first_message_at=moment(12),
        last_message_at=moment(13),
        last_inbound_at=moment(12),
        last_outbound_at=moment(13),
    )


def stored_messages(thread: Conversation, *, body: str | None = None) -> list[Message]:
    """The two messages the stored thread holds."""
    return [
        Message(
            conversation_id=thread.id,
            source_message_id="m-in",
            direction=Direction.INBOUND,
            sent_at=moment(12),
            sender_identifier=ADDRESS,
            body=body,
        ),
        Message(
            conversation_id=thread.id,
            source_message_id="m-out",
            direction=Direction.OUTBOUND,
            sent_at=moment(13),
            sender_identifier=OWNER,
            body=body,
        ),
    ]


def known_messages() -> tuple[RawMessage, RawMessage]:
    """The two messages the stored thread holds, as the collector reads them again."""
    return (
        raw_message("m-in", Direction.INBOUND, 12),
        raw_message("m-out", Direction.OUTBOUND, 13),
    )


def write(repositories: Repositories, person_id: UUID, *threads: RawConversation) -> None:
    """Store collected threads the way a collector does, for Anna."""
    ConversationWriter(repositories).write(Channel.EMAIL, list(threads), {KEY: person_id})


def assistant_noise(
    repositories: Repositories,
    *,
    linked: bool = True,
) -> tuple[Person, Conversation]:
    """Anna, whom the assistant threw away as noise together with her one thread."""
    person = make_person(relevance=Relevance.NOISE)
    thread = stored_thread(person if linked else None)
    seed(repositories, people=[person], threads=[thread], messages=stored_messages(thread))
    return person, thread


def owner_hidden(repositories: Repositories) -> Person:
    """Anna, taken off the list by the owner: she is noise, her live thread is not."""
    person = make_person(relevance=Relevance.NOISE)
    thread = stored_thread(person, relevance=Relevance.UNSURE, decided_by=None)
    seed(
        repositories,
        people=[person],
        threads=[thread],
        messages=stored_messages(thread, body="Made-up text."),
    )
    return person


def relevance_of(repositories: Repositories, person: Person) -> Relevance:
    """Anna's stored relevance."""
    stored = repositories.people.get(person.id)
    assert stored is not None
    return stored.relevance


def only_thread(repositories: Repositories, source: str = THREAD) -> Conversation:
    """The stored thread with the given source identifier."""
    found = repositories.conversations.find_by_source(Channel.EMAIL, source)
    assert found is not None
    return found


# --- the rules ----------------------------------------------------------------


def test_only_a_thread_the_assistant_threw_away_comes_back_when_the_owner_writes() -> None:
    assistant = ThreadRuling(Relevance.NOISE, RelevanceDecidedBy.AI)

    assert thread_comes_back(assistant, owner_wrote_again=True)
    assert not thread_comes_back(assistant, owner_wrote_again=False)
    assert not thread_comes_back(
        ThreadRuling(Relevance.NOISE, RelevanceDecidedBy.OWNER), owner_wrote_again=True
    )
    assert not thread_comes_back(
        ThreadRuling(Relevance.NOISE, RelevanceDecidedBy.RULE), owner_wrote_again=True
    )
    assert not thread_comes_back(
        ThreadRuling(Relevance.UNSURE, RelevanceDecidedBy.AI), owner_wrote_again=True
    )


def test_a_person_is_the_assistants_when_everything_stored_about_them_is() -> None:
    ruling = PersonRuling(
        relevance=Relevance.NOISE,
        threads=(ThreadRuling(Relevance.NOISE, RelevanceDecidedBy.AI),),
    )

    assert person_ruled_out_by_assistant(ruling)


def test_a_person_whose_threads_were_all_let_go_of_is_still_the_assistants() -> None:
    assert person_ruled_out_by_assistant(PersonRuling(relevance=Relevance.NOISE))


def test_a_person_with_a_live_thread_was_hidden_by_the_owner() -> None:
    ruling = PersonRuling(
        relevance=Relevance.NOISE,
        threads=(ThreadRuling(Relevance.UNSURE, None),),
    )

    assert not person_ruled_out_by_assistant(ruling)


def test_an_answer_or_a_correction_makes_the_owner_the_one_who_decided() -> None:
    assert not person_ruled_out_by_assistant(
        PersonRuling(relevance=Relevance.NOISE, owner_answered=True)
    )
    assert not person_ruled_out_by_assistant(
        PersonRuling(relevance=Relevance.NOISE, owner_corrected=True)
    )


def test_somebody_who_is_not_noise_is_not_ruled_out() -> None:
    assert not person_ruled_out_by_assistant(PersonRuling(relevance=Relevance.UNSURE))


# --- the owner writes ---------------------------------------------------------


def test_a_new_message_from_the_owner_brings_a_noise_thread_back(
    repositories: Repositories,
) -> None:
    person, _ = assistant_noise(repositories)

    write(
        repositories,
        person.id,
        raw_thread(*known_messages(), raw_message("m-new", Direction.OUTBOUND, 15)),
    )

    thread = only_thread(repositories)
    assert thread.relevance is Relevance.UNSURE
    assert thread.relevance_decided_by is None
    assert thread.subject == "Made-up subject"
    assert thread.person_id == person.id
    assert thread.last_outbound_at == moment(15)
    assert relevance_of(repositories, person) is Relevance.UNSURE


def test_the_text_of_a_returned_thread_is_stored_again(repositories: Repositories) -> None:
    person, thread = assistant_noise(repositories)

    write(
        repositories,
        person.id,
        raw_thread(*known_messages(), raw_message("m-new", Direction.OUTBOUND, 15)),
    )

    bodies = {
        m.source_message_id: m.body
        for m in repositories.messages.list_for_conversations([thread.id])
    }
    assert bodies == {"m-in": "Made-up text.", "m-out": "Made-up text.", "m-new": "Made-up text."}


def test_a_thread_that_lost_its_person_is_filed_under_her_again(
    repositories: Repositories,
) -> None:
    person, _ = assistant_noise(repositories, linked=False)

    write(
        repositories,
        person.id,
        raw_thread(*known_messages(), raw_message("m-new", Direction.OUTBOUND, 15)),
    )

    assert only_thread(repositories).person_id == person.id
    assert relevance_of(repositories, person) is Relevance.UNSURE


def test_a_message_from_them_alone_does_not_bring_a_noise_thread_back(
    repositories: Repositories,
) -> None:
    person, thread = assistant_noise(repositories)

    write(
        repositories,
        person.id,
        raw_thread(*known_messages(), raw_message("m-new", Direction.INBOUND, 15)),
    )

    stored = only_thread(repositories)
    assert stored.relevance is Relevance.NOISE
    assert stored.relevance_decided_by is RelevanceDecidedBy.AI
    assert stored.subject is None
    assert relevance_of(repositories, person) is Relevance.NOISE
    bodies = [m.body for m in repositories.messages.list_for_conversations([thread.id])]
    assert bodies == [None, None, None]


def test_a_message_of_the_owner_that_is_already_stored_changes_nothing(
    repositories: Repositories,
) -> None:
    person, _ = assistant_noise(repositories)

    write(repositories, person.id, raw_thread(*known_messages()))

    assert only_thread(repositories).relevance is Relevance.NOISE
    assert relevance_of(repositories, person) is Relevance.NOISE


def test_an_older_message_of_the_owner_found_late_changes_nothing(
    repositories: Repositories,
) -> None:
    person, _ = assistant_noise(repositories)

    write(
        repositories,
        person.id,
        raw_thread(*known_messages(), raw_message("m-old", Direction.OUTBOUND, 11)),
    )

    assert only_thread(repositories).relevance is Relevance.NOISE


def test_a_thread_the_owner_threw_away_himself_stays_away_when_he_writes(
    repositories: Repositories,
) -> None:
    person = make_person(relevance=Relevance.NOISE)
    thread = stored_thread(person, decided_by=RelevanceDecidedBy.OWNER)
    seed(repositories, people=[person], threads=[thread], messages=stored_messages(thread))

    write(
        repositories,
        person.id,
        raw_thread(*known_messages(), raw_message("m-new", Direction.OUTBOUND, 15)),
    )

    assert only_thread(repositories).relevance is Relevance.NOISE
    assert relevance_of(repositories, person) is Relevance.NOISE


def test_writing_to_somebody_the_owner_hid_leaves_them_hidden(
    repositories: Repositories,
) -> None:
    person = owner_hidden(repositories)

    write(
        repositories,
        person.id,
        raw_thread(*known_messages(), raw_message("m-new", Direction.OUTBOUND, 15)),
    )

    assert relevance_of(repositories, person) is Relevance.NOISE


def test_a_no_answer_keeps_the_person_hidden_even_when_the_owner_writes(
    repositories: Repositories,
) -> None:
    person, _ = assistant_noise(repositories)
    repositories.review_items.bulk_upsert([make_answer(person, answer=ReviewAnswer.NO)])

    write(
        repositories,
        person.id,
        raw_thread(*known_messages(), raw_message("m-new", Direction.OUTBOUND, 15)),
    )

    assert relevance_of(repositories, person) is Relevance.NOISE


# --- a new conversation -------------------------------------------------------


def test_a_new_conversation_brings_the_person_back(repositories: Repositories) -> None:
    person, old = assistant_noise(repositories)

    write(
        repositories,
        person.id,
        raw_thread(raw_message("n-1", Direction.INBOUND, 16), source="t-offer"),
    )

    assert relevance_of(repositories, person) is Relevance.UNSURE
    assert only_thread(repositories, "t-offer").person_id == person.id
    assert only_thread(repositories, "t-offer").relevance is Relevance.UNSURE
    assert only_thread(repositories, old.source_conversation_id).relevance is Relevance.NOISE


def test_a_new_conversation_the_rules_call_noise_changes_nothing(
    repositories: Repositories,
) -> None:
    person, _ = assistant_noise(repositories)

    write(
        repositories,
        person.id,
        raw_thread(
            raw_message("n-1", Direction.INBOUND, 16, body=None),
            source="t-news",
            relevance=Relevance.NOISE,
        ),
    )

    assert relevance_of(repositories, person) is Relevance.NOISE


def test_a_new_conversation_from_a_person_the_owner_hid_leaves_them_hidden(
    repositories: Repositories,
) -> None:
    person = owner_hidden(repositories)

    write(
        repositories,
        person.id,
        raw_thread(raw_message("n-1", Direction.INBOUND, 16), source="t-offer"),
    )

    assert relevance_of(repositories, person) is Relevance.NOISE


def test_a_yes_answer_a_no_answer_or_a_correction_keeps_the_person_hidden(
    repositories: Repositories,
) -> None:
    yes, _ = assistant_noise(repositories)
    repositories.review_items.bulk_upsert([make_answer(yes, answer=ReviewAnswer.YES)])
    corrected = make_person("Ben Corrected", relevance=Relevance.NOISE)
    repositories.people.bulk_upsert([corrected])
    repositories.person_overrides.bulk_upsert([make_override(corrected, next_action="Call him")])

    write(
        repositories, yes.id, raw_thread(raw_message("n-1", Direction.INBOUND, 16), source="t-1b")
    )
    write(
        repositories,
        corrected.id,
        raw_thread(raw_message("n-2", Direction.INBOUND, 16), source="t-2"),
    )

    assert relevance_of(repositories, yes) is Relevance.NOISE
    assert relevance_of(repositories, corrected) is Relevance.NOISE


def test_a_first_conversation_with_somebody_new_is_left_as_it_is(
    repositories: Repositories,
) -> None:
    person = make_person(relevance=Relevance.UNSURE)
    repositories.people.bulk_upsert([person])

    write(repositories, person.id, raw_thread(raw_message("n-1", Direction.INBOUND, 16)))

    assert relevance_of(repositories, person) is Relevance.UNSURE


# --- the whole way round ------------------------------------------------------


def test_a_person_the_assistant_dropped_is_sent_to_it_again_after_the_owner_writes(
    repositories: Repositories,
    clock: FixedClock,
    tmp_path: Path,
) -> None:
    person = talkative_person(repositories, subject="Weekly digest")
    chain = build_chain(repositories, clock, tmp_path, [person])
    chain.answer(verdict_payload(person.id, relevance="noise"))
    chain.importer.import_all()
    assert AssessmentExporter(repositories, clock, tmp_path / "again").pending_people() == 0
    newest = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)
    stored = {
        m.source_message_id: m
        for m in repositories.messages.list_for_conversations(
            [t.id for t in repositories.conversations.list_for_person(person.id)]
        )
    }

    ConversationWriter(repositories).write(
        Channel.LINKEDIN,
        [
            RawConversation(
                channel=Channel.LINKEDIN,
                source_conversation_id="thread-1",
                subject="Weekly digest",
                relevance=Relevance.UNSURE,
                participants=(RawParticipant(Channel.LINKEDIN, "anna", "Anna Vermeer"),),
                messages=(
                    *(
                        RawMessage(
                            message.source_message_id,
                            message.sent_at,
                            message.direction,
                            None,
                            "Made-up text.",
                        )
                        for message in stored.values()
                    ),
                    RawMessage(
                        "thread-1-m3", newest, Direction.OUTBOUND, None, "Yes, let us talk."
                    ),
                ),
            )
        ],
        {(Channel.LINKEDIN, "anna"): person.id},
    )

    exporter = AssessmentExporter(repositories, clock, tmp_path / "again")
    result = exporter.export()
    batch = parse_batch(result.batch_paths[0].read_text(encoding="utf-8"))
    assert [dossier.person_id for dossier in batch.people] == [person.id]
    assert [thread.subject for thread in batch.people[0].threads] == ["Weekly digest"]


# --- through the mailbox collector -------------------------------------------

ELODIE = "elodie.martin@acme.example"


def elodie_dropped(repositories: Repositories, *, stored: tuple[str, ...]) -> Person:
    """Élodie, dropped by the assistant with her mailbox thread; only some messages are stored."""
    person = make_person("Élodie Martin", relevance=Relevance.NOISE)
    thread = Conversation(
        person_id=person.id,
        channel=Channel.EMAIL,
        source_conversation_id="t-human",
        relevance=Relevance.NOISE,
        relevance_decided_by=RelevanceDecidedBy.AI,
        first_message_at=datetime(2026, 9, 10, 9, 30, tzinfo=UTC),
        last_message_at=datetime(2026, 9, 10, 9, 30, tzinfo=UTC),
        last_inbound_at=datetime(2026, 9, 10, 9, 30, tzinfo=UTC),
    )
    sent = {
        "m-human-1": (Direction.INBOUND, datetime(2026, 9, 10, 9, 30, tzinfo=UTC)),
        "m-human-2": (Direction.OUTBOUND, datetime(2026, 9, 10, 10, 0, tzinfo=UTC)),
    }
    seed(
        repositories,
        people=[person],
        threads=[thread],
        messages=[
            Message(
                conversation_id=thread.id,
                source_message_id=name,
                direction=sent[name][0],
                sent_at=sent[name][1],
            )
            for name in stored
        ],
    )
    repositories.person_identities.bulk_upsert(
        [PersonIdentity(person_id=person.id, channel=Channel.EMAIL, identifier=ELODIE)]
    )
    return person


def test_the_mailbox_run_brings_back_a_thread_the_owner_answered(
    repositories: Repositories,
    settings: Settings,
    clock: FixedClock,
) -> None:
    person = elodie_dropped(repositories, stored=("m-human-1",))

    collect_email(repositories, settings, clock)

    thread = only_thread(repositories, "t-human")
    assert thread.relevance is Relevance.UNSURE
    assert thread.relevance_decided_by is None
    assert thread.person_id == person.id
    assert relevance_of(repositories, person) is Relevance.UNSURE
    bodies = [m.body for m in repositories.messages.list_for_conversations([thread.id])]
    assert bodies == ["Made-up body text."] * 2


def test_the_mailbox_run_leaves_a_thread_alone_when_only_they_wrote(
    repositories: Repositories,
    settings: Settings,
    clock: FixedClock,
) -> None:
    person = elodie_dropped(repositories, stored=("m-human-1", "m-human-2"))
    later = graph_message(
        "m-human-3",
        conversation_id="t-human",
        address=ELODIE,
        name="Élodie Martin",
        subject="Coffee next week?",
        sent="2026-09-12T09:30:00Z",
    )

    collect_email(repositories, settings, clock, [*MAILBOX, later])

    thread = only_thread(repositories, "t-human")
    assert thread.relevance is Relevance.NOISE
    assert thread.relevance_decided_by is RelevanceDecidedBy.AI
    assert relevance_of(repositories, person) is Relevance.NOISE
    bodies = [m.body for m in repositories.messages.list_for_conversations([thread.id])]
    assert bodies == [None, None, None]
