"""Undo what treating a shared sender as a person did to the stored records.

Until the collector learnt to look behind shared senders (see
:mod:`tracker.domain.relay`), a hiring system's no-reply address became one
"person" holding every company that wrote through it, and a shared calendar
address joined whoever used it first. This repair releases those threads so
the next mailbox read files each one under its real person or company:

- every thread that came from a shared address is detached from its person, and
  an AI "noise" decision on it is reset, so its text is read again;
- the shared address stops being anybody's identity;
- a person left with no address at all is hidden (marked noise), never deleted;
- a person who keeps real addresses loses the saved assessment, so the AI looks
  again at what is left, and a name like "Ann Lee via Docusign" is cleaned;
- a hiring system's thread the AI already threw away as noise while it sat
  under no person is given back its "unsure", so its text is read again.

Owner corrections and owner decisions are never touched. Running it twice
changes nothing the second time.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from uuid import UUID

from tracker.domain.enums import Channel, Relevance, RelevanceDecidedBy
from tracker.domain.models import Conversation, Person, PersonIdentity
from tracker.domain.prefilter import is_relay_sender, is_work_system_sender
from tracker.domain.relay import clean_via_name
from tracker.domain.rules import RulePack
from tracker.repositories import Repositories
from tracker.shared.constants.collection import RELAY_VIA_MARKER
from tracker.shared.logging import get_logger

_log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class UntangleReport:
    """What one run of the repair changed."""

    identities_removed: int = 0
    conversations_released: int = 0
    people_hidden: int = 0
    people_to_reassess: int = 0
    noise_verdicts_reset: int = 0


class RelayUntangler:
    """Releases the threads that were filed under a shared sender."""

    def __init__(self, repositories: Repositories, rules: RulePack) -> None:
        """Bind the repair to the database.

        Args:
            repositories: The repository container.
            rules: The owner's collection rules, which name the shared systems.
        """
        self._repositories = repositories
        self._rules = rules

    def untangle(self) -> UntangleReport:
        """Run the repair once.

        Returns:
            What was changed; all zero when there was nothing left to repair.
        """
        report = replace(self._split_shared_identities(), noise_verdicts_reset=self._unfile_noise())
        _log.info(
            "relay_senders_untangled",
            identities_removed=report.identities_removed,
            conversations_released=report.conversations_released,
            people_hidden=report.people_hidden,
            people_to_reassess=report.people_to_reassess,
            noise_verdicts_reset=report.noise_verdicts_reset,
        )
        return report

    def _split_shared_identities(self) -> UntangleReport:
        """Remove every shared address from the people holding it."""
        identities = self._repositories.person_identities.list_every()
        shared = [
            identity
            for identity in identities
            if identity.channel is Channel.EMAIL
            and is_relay_sender(identity.identifier, self._rules)
        ]
        if not shared:
            return UntangleReport()
        released = self._release_threads(shared)
        self._repositories.person_identities.delete_by_ids([item.id for item in shared])
        affected = {identity.person_id for identity in shared}
        shared_ids = {identity.id for identity in shared}
        remaining = {
            identity.person_id for identity in identities if identity.id not in shared_ids
        } & affected
        hidden = self._hide(affected - remaining)
        self._reset(remaining)
        return UntangleReport(
            identities_removed=len(shared),
            conversations_released=released,
            people_hidden=hidden,
            people_to_reassess=len(remaining),
        )

    def _unfile_noise(self) -> int:
        """Give back "unsure" to work-system threads the AI threw away unfiled."""
        orphans = [
            conversation
            for conversation in self._repositories.conversations.list_every()
            if conversation.person_id is None
            and conversation.channel is Channel.EMAIL
            and conversation.relevance is Relevance.NOISE
            and conversation.relevance_decided_by is RelevanceDecidedBy.AI
        ]
        senders = self._repositories.messages.list_senders([item.id for item in orphans])
        systems = {
            thread for thread, sender in senders if is_work_system_sender(sender, self._rules)
        }
        reset = [_released(item) for item in orphans if item.id in systems]
        self._repositories.conversations.bulk_upsert(reset)
        return len(reset)

    def _release_threads(self, shared: list[PersonIdentity]) -> int:
        """Detach every thread a shared address sent from the person holding it."""
        address_of: dict[UUID, set[str]] = defaultdict(set)
        for identity in shared:
            address_of[identity.person_id].add(identity.identifier.strip().lower())
        conversations = self._repositories.conversations.list_for_people(list(address_of))
        person_of = {item.id: item.person_id for item in conversations}
        senders = self._repositories.messages.list_senders(list(person_of))
        from_shared = {
            thread
            for thread, sender in senders
            if (person := person_of.get(thread)) is not None
            and sender.strip().lower() in address_of[person]
        }
        released = [_released(item) for item in conversations if item.id in from_shared]
        self._repositories.conversations.bulk_upsert(released)
        return len(released)

    def _hide(self, person_ids: set[UUID]) -> int:
        """Mark people who have no address left as noise, so nothing shows them."""
        people = self._repositories.people.list_by_ids(sorted(person_ids))
        hidden = [
            person.model_copy(update={"relevance": Relevance.NOISE})
            for person in people
            if person.relevance is not Relevance.NOISE
        ]
        self._repositories.people.bulk_upsert(hidden)
        return len(hidden)

    def _reset(self, person_ids: set[UUID]) -> None:
        """Drop the saved assessment of people whose threads changed; tidy names."""
        if not person_ids:
            return
        states = self._repositories.person_states.list_for_people(sorted(person_ids))
        self._repositories.person_states.delete_by_ids([state.id for state in states])
        people = self._repositories.people.list_by_ids(sorted(person_ids))
        self._repositories.people.bulk_upsert(
            [_with_clean_name(person) for person in people if RELAY_VIA_MARKER in person.full_name]
        )


def _released(conversation: Conversation) -> Conversation:
    """A thread with no person, and without an AI "noise" verdict to keep."""
    update: dict[str, object] = {"person_id": None}
    if conversation.relevance_decided_by is RelevanceDecidedBy.AI:
        update |= {"relevance": Relevance.UNSURE, "relevance_decided_by": None}
    return conversation.model_copy(update=update)


def _with_clean_name(person: Person) -> Person:
    """The same person without "via <service>" in their name."""
    return person.model_copy(update={"full_name": clean_via_name(person.full_name)})
