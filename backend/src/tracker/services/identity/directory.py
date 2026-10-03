"""The plain list of everybody the collectors have found.

``people_overview`` is the dashboard's read model and shows only people the
assessment has already judged relevant. Before any AI has run, the owner still
needs to see who came out of the collection, so this service builds the simpler
list: name, channels, message count and last contact.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final
from uuid import UUID

from tracker.domain.enums import Channel
from tracker.domain.models import Person
from tracker.repositories import Repositories

#: Sorts people Threadline has no message for below everybody else.
_NEVER: Final[datetime] = datetime.min.replace(tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class DirectoryEntry:
    """One person, as the command line shows them.

    Attributes:
        full_name: The person's name.
        channels: Where Threadline has met them.
        message_count: How many messages are stored across their threads.
        last_contact_at: When the most recent message was sent, if any.
    """

    full_name: str
    channels: tuple[Channel, ...]
    message_count: int
    last_contact_at: datetime | None


class PeopleDirectory:
    """Builds the plain list of collected people."""

    def __init__(self, repositories: Repositories) -> None:
        """Bind the directory to the repositories it reads.

        Args:
            repositories: The repository container.
        """
        self._repositories = repositories

    def list_people(self) -> list[DirectoryEntry]:
        """List everybody, most recently contacted first.

        Returns:
            One entry per person the collectors have created.
        """
        people = self._repositories.people.list_every()
        if not people:
            return []
        channels = self._channels_of(people)
        conversations = self._repositories.conversations.list_for_people(
            [person.id for person in people]
        )
        counts = self._repositories.messages.count_by_conversation(
            [conversation.id for conversation in conversations]
        )
        messages_by_person: dict[UUID, int] = {}
        last_by_person: dict[UUID, datetime] = {}
        for conversation in conversations:
            owner = conversation.person_id
            if owner is None:
                continue
            messages_by_person[owner] = messages_by_person.get(owner, 0) + counts.get(
                conversation.id, 0
            )
            last = conversation.last_message_at
            if last is not None:
                last_by_person[owner] = max(last, last_by_person.get(owner, last))
        entries = [
            DirectoryEntry(
                full_name=person.full_name,
                channels=tuple(sorted(channels.get(person.id, set()))),
                message_count=messages_by_person.get(person.id, 0),
                last_contact_at=last_by_person.get(person.id),
            )
            for person in people
        ]
        return sorted(entries, key=_recency, reverse=True)

    def _channels_of(self, people: list[Person]) -> dict[UUID, set[Channel]]:
        """Map each person to the channels they are reachable on."""
        known = {person.id for person in people}
        channels: dict[UUID, set[Channel]] = {}
        for identity in self._repositories.person_identities.list_every():
            if identity.person_id in known:
                channels.setdefault(identity.person_id, set()).add(identity.channel)
        return channels


def _recency(entry: DirectoryEntry) -> datetime:
    """Sort key placing people with no contact date last."""
    return entry.last_contact_at or _NEVER
