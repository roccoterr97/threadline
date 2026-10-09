"""One person per address, and the cautious rule for joining two channels."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from tests.conftest import JOB_SEARCH_RULES, FakeSupabaseClient
from tracker.domain.enums import Channel, ReviewKind
from tracker.repositories import Repositories
from tracker.services.collection.models import RawParticipant
from tracker.services.identity.directory import PeopleDirectory
from tracker.services.identity.matcher import IdentityMatcher

ELODIE_PROFILE = "linkedin.com/in/elodie-martin"
MARCO_ONE = "linkedin.com/in/marco-rossi-1"
MARCO_TWO = "linkedin.com/in/marco-rossi-2"


def participant(channel: Channel, identifier: str, name: str) -> RawParticipant:
    """Build one collected participant."""
    return RawParticipant(channel=channel, identifier=identifier, display_name=name)


def rows(client: FakeSupabaseClient, table: str) -> list[dict[str, Any]]:
    """Read one table of the in-memory database."""
    return client.tables.get(table, [])


@pytest.fixture
def matcher(repositories: Repositories) -> IdentityMatcher:
    """A matcher on the in-memory database."""
    return IdentityMatcher(repositories, JOB_SEARCH_RULES)


def test_a_name_that_matches_on_one_side_only_is_merged(
    matcher: IdentityMatcher,
    fake_client: FakeSupabaseClient,
) -> None:
    matcher.resolve([participant(Channel.LINKEDIN, ELODIE_PROFILE, "Élodie  Martin")])

    result = matcher.resolve(
        [participant(Channel.EMAIL, "elodie.martin@acme.example", "elodie martin")]
    )

    assert len(rows(fake_client, "people")) == 1
    assert len(rows(fake_client, "person_identities")) == 2
    assert result.people_created == 0
    assert rows(fake_client, "review_items") == []


def test_two_people_with_one_name_are_never_merged_silently(
    matcher: IdentityMatcher,
    fake_client: FakeSupabaseClient,
) -> None:
    matcher.resolve(
        [
            participant(Channel.LINKEDIN, MARCO_ONE, "Marco Rossi"),
            participant(Channel.LINKEDIN, MARCO_TWO, "Marco Rossi"),
        ]
    )

    result = matcher.resolve(
        [participant(Channel.EMAIL, "marco.rossi@acme.example", "Marco Rossi")]
    )

    questions = rows(fake_client, "review_items")
    assert len(rows(fake_client, "people")) == 3
    assert result.people_created == 1
    assert len(questions) == 1
    assert questions[0]["kind"] == ReviewKind.SAME_PERSON.value
    assert questions[0]["other_person_id"] is not None


def test_a_name_already_stored_on_this_channel_is_not_merged_silently(
    matcher: IdentityMatcher,
    fake_client: FakeSupabaseClient,
) -> None:
    # Two stored LinkedIn Marcos and one e-mail Marco, all separate people. A
    # third LinkedIn Marco has one candidate on the other side, but the name is
    # already taken twice on this side, so it cannot be told which is which.
    matcher.resolve(
        [
            participant(Channel.LINKEDIN, MARCO_ONE, "Marco Rossi"),
            participant(Channel.LINKEDIN, MARCO_TWO, "Marco Rossi"),
        ]
    )
    matcher.resolve([participant(Channel.EMAIL, "marco.rossi@acme.example", "Marco Rossi")])
    people_before = len(rows(fake_client, "people"))
    questions_before = len(rows(fake_client, "review_items"))

    result = matcher.resolve(
        [participant(Channel.LINKEDIN, "linkedin.com/in/marco-rossi-3", "Marco Rossi")]
    )

    questions = rows(fake_client, "review_items")
    assert result.people_created == 1
    assert len(rows(fake_client, "people")) == people_before + 1
    assert len(questions) == questions_before + 1
    assert questions[-1]["kind"] == ReviewKind.SAME_PERSON.value


def test_a_stored_name_on_the_other_side_only_still_merges(
    matcher: IdentityMatcher,
    fake_client: FakeSupabaseClient,
) -> None:
    matcher.resolve([participant(Channel.LINKEDIN, MARCO_ONE, "Marco Rossi")])
    matcher.resolve([participant(Channel.LINKEDIN, ELODIE_PROFILE, "Elodie Martin")])

    result = matcher.resolve(
        [participant(Channel.EMAIL, "marco.rossi@acme.example", "Marco Rossi")]
    )

    assert result.people_created == 0
    assert len(rows(fake_client, "people")) == 2


def test_the_same_question_is_never_asked_twice(
    matcher: IdentityMatcher,
    fake_client: FakeSupabaseClient,
) -> None:
    matcher.resolve(
        [
            participant(Channel.LINKEDIN, MARCO_ONE, "Marco Rossi"),
            participant(Channel.LINKEDIN, MARCO_TWO, "Marco Rossi"),
        ]
    )
    matcher.resolve([participant(Channel.EMAIL, "marco.rossi@acme.example", "Marco Rossi")])

    matcher.resolve([participant(Channel.EMAIL, "marco.rossi2@acme.example", "Marco Rossi")])

    assert len(rows(fake_client, "review_items")) == 2


def test_an_ambiguous_name_inside_one_run_is_not_merged_either(
    matcher: IdentityMatcher,
    fake_client: FakeSupabaseClient,
) -> None:
    matcher.resolve([participant(Channel.LINKEDIN, MARCO_ONE, "Marco Rossi")])

    matcher.resolve(
        [
            participant(Channel.EMAIL, "marco@acme.example", "Marco Rossi"),
            participant(Channel.EMAIL, "m.rossi@other.example", "Marco Rossi"),
        ]
    )

    assert len(rows(fake_client, "people")) == 3


def test_an_identity_already_known_is_reused(
    matcher: IdentityMatcher,
    fake_client: FakeSupabaseClient,
) -> None:
    first = matcher.resolve([participant(Channel.LINKEDIN, ELODIE_PROFILE, "Élodie Martin")])

    second = matcher.resolve([participant(Channel.LINKEDIN, ELODIE_PROFILE, "Elodie Martin")])

    assert second.people_created == 0
    assert second.person_by_identity == first.person_by_identity
    assert len(rows(fake_client, "people")) == 1


def test_an_employer_domain_creates_an_organisation(
    matcher: IdentityMatcher,
    fake_client: FakeSupabaseClient,
) -> None:
    matcher.resolve([participant(Channel.EMAIL, "someone@acme.example", "Someone Else")])

    organisations = rows(fake_client, "organisations")
    assert [row["name"] for row in organisations] == ["Acme"]
    assert rows(fake_client, "people")[0]["organisation_id"] == organisations[0]["id"]


@pytest.mark.parametrize(
    "address",
    ["friend@gmail.com", "friend@hotmail.it", "friend@hotmail.com", "friend@outlook.com"],
)
def test_a_free_mail_address_creates_no_organisation(
    matcher: IdentityMatcher,
    fake_client: FakeSupabaseClient,
    address: str,
) -> None:
    matcher.resolve([participant(Channel.EMAIL, address, "A Friend")])

    assert rows(fake_client, "organisations") == []
    assert rows(fake_client, "people")[0]["organisation_id"] is None


def test_a_participant_without_an_identifier_is_ignored(matcher: IdentityMatcher) -> None:
    result = matcher.resolve([participant(Channel.EMAIL, "   ", "Nobody")])

    assert result.person_by_identity == {}
    assert result.people_created == 0


def test_the_people_list_is_empty_before_anything_is_collected(
    repositories: Repositories,
) -> None:
    assert PeopleDirectory(repositories).list_people() == []


def test_a_new_person_without_a_name_is_shown_by_the_name_their_address_spells(
    matcher: IdentityMatcher,
    fake_client: FakeSupabaseClient,
) -> None:
    matcher.resolve([participant(Channel.EMAIL, "alessia.conti@quick-solve.example", "")])

    assert rows(fake_client, "people")[0]["full_name"] == "Alessia Conti"


def test_a_new_person_whose_address_spells_no_name_is_shown_by_the_address(
    matcher: IdentityMatcher,
    fake_client: FakeSupabaseClient,
) -> None:
    matcher.resolve([participant(Channel.EMAIL, "jeanmarc@acmedata.example", "")])

    assert rows(fake_client, "people")[0]["full_name"] == "jeanmarc@acmedata.example"


# --- how often the database is asked ------------------------------------------------


def test_when_nobody_is_new_the_people_are_not_read(
    matcher: IdentityMatcher,
    fake_client: FakeSupabaseClient,
) -> None:
    """Everybody is found by their address; there is nobody to compare names for."""
    seen = [
        participant(Channel.LINKEDIN, ELODIE_PROFILE, "Élodie Martin"),
        participant(Channel.EMAIL, "marco.rossi@acme.example", "Marco Rossi"),
    ]
    first = matcher.resolve(seen)
    stored = copy.deepcopy(fake_client.tables)
    fake_client.executed.clear()

    second = matcher.resolve(seen)

    assert fake_client.executed == [("person_identities", "select")] * 2
    assert second.person_by_identity == first.person_by_identity
    assert (second.people_created, second.review_items_created) == (0, 0)
    assert fake_client.tables == stored


def test_when_somebody_is_new_everybody_is_read_once_and_compared_as_before(
    matcher: IdentityMatcher,
    fake_client: FakeSupabaseClient,
) -> None:
    """A new address still meets the people stored on earlier runs."""
    known = participant(Channel.LINKEDIN, ELODIE_PROFILE, "Élodie Martin")
    first = matcher.resolve([known, participant(Channel.LINKEDIN, MARCO_ONE, "Marco Rossi")])
    fake_client.executed.clear()

    second = matcher.resolve(
        [
            known,
            participant(Channel.EMAIL, "elodie.martin@acme.example", "Elodie Martin"),
            participant(Channel.EMAIL, "mrossi@gmail.com", ""),
            participant(Channel.EMAIL, "hello@harbour.example", "Inès Faure"),
        ]
    )

    reads = [table for table, operation in fake_client.executed if operation == "select"]
    assert reads.count("people") == 1
    # Once to find who is known by address on each channel, once for everybody.
    assert reads.count("person_identities") == 3
    elodie = first.person_by_identity[known.key]
    marco = first.person_by_identity[(Channel.LINKEDIN, MARCO_ONE)]
    assert second.person_by_identity[(Channel.EMAIL, "elodie.martin@acme.example")] == elodie
    assert (second.people_created, second.review_items_created) == (2, 1)
    assert sorted(row["full_name"] for row in rows(fake_client, "people")) == [
        "Inès Faure",
        "Marco Rossi",
        "mrossi@gmail.com",
        "Élodie Martin",
    ]
    [question] = rows(fake_client, "review_items")
    by_address = second.person_by_identity[(Channel.EMAIL, "mrossi@gmail.com")]
    assert (question["person_id"], question["other_person_id"]) == (str(by_address), str(marco))
    assert question["question"] == (
        "Is mrossi@gmail.com on email the same person as Marco Rossi on linkedin?"
    )
    assert sorted(row["name"] for row in rows(fake_client, "organisations")) == [
        "Acme",
        "Harbour",
    ]


def test_each_run_reads_the_people_afresh(
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
) -> None:
    """Two collectors never share what one of them read: the other's people would be missing."""
    linkedin = IdentityMatcher(repositories, JOB_SEARCH_RULES)
    mailbox = IdentityMatcher(repositories, JOB_SEARCH_RULES)
    mailbox.resolve([participant(Channel.EMAIL, "someone@acme.example", "Somebody Else")])
    linkedin.resolve([participant(Channel.LINKEDIN, ELODIE_PROFILE, "Élodie Martin")])

    mailbox.resolve([participant(Channel.EMAIL, "elodie.martin@acme.example", "Elodie Martin")])

    assert len(rows(fake_client, "people")) == 2
    assert rows(fake_client, "review_items") == []
