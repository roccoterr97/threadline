"""Giving a name to people recorded under an address that plainly spells one.

The matcher names new people this way as they arrive. This covers the records
stored before it did, and runs after the linker so that the questions the
linker asks about bare addresses are already in the review list.

Only the name shown changes: no identity, conversation or verdict is touched.
"""

from __future__ import annotations

from tracker.domain.identity import is_shown_as_address, shown_name_from_address
from tracker.domain.models import Person
from tracker.domain.relay import is_relay_identity
from tracker.domain.rules import RulePack
from tracker.repositories import Repositories
from tracker.shared.logging import get_logger

_log = get_logger(__name__)


class AddressNamer:
    """Replaces a shown address with the name it spells."""

    def __init__(self, repositories: Repositories, rules: RulePack) -> None:
        """Bind the namer to the database.

        Args:
            repositories: The repository container.
            rules: The owner's collection rules, which say which addresses are
                shared systems and spell nobody's name.
        """
        self._repositories = repositories
        self._rules = rules

    def name_all(self) -> int:
        """Name every stored person whose address plainly spells a name.

        Returns:
            How many people were given a name.
        """
        renamed = [
            named
            for person in self._repositories.people.list_every()
            if (named := _named(person, self._rules)) is not None
        ]
        if renamed:
            self._repositories.people.bulk_upsert(renamed)
            _log.info("people_named_from_address", named=len(renamed))
        return len(renamed)


def _named(person: Person, rules: RulePack) -> Person | None:
    """The person with a name, or ``None`` when there is nothing to change."""
    address = person.full_name.strip()
    if not is_shown_as_address(address) or is_relay_identity(address, rules):
        return None
    name = shown_name_from_address(address)
    return person.model_copy(update={"full_name": name}) if name else None
