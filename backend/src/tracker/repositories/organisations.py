"""Data access for ``organisations``."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from itertools import batched
from typing import ClassVar

from supabase import Client

from tracker.domain.models import Organisation
from tracker.repositories.base import ALL_COLUMNS, SupabaseRepository
from tracker.shared.constants.collection import DATABASE_BATCH_SIZE, NAME_LOOKUP_BATCH_SIZE

#: Characters the client sends as they are inside a list of values, where the
#: database reads them as punctuation. A name holding one is looked up alone.
_UNLISTABLE_CHARACTERS = frozenset('"\\')


class OrganisationRepository(SupabaseRepository[Organisation]):
    """Companies and funds the owner's contacts belong to."""

    table_name: ClassVar[str] = "organisations"

    def __init__(self, client: Client) -> None:
        """Bind the repository to the shared Supabase client."""
        super().__init__(client, Organisation)

    def list_by_email_domains(self, email_domains: Sequence[str]) -> list[Organisation]:
        """Fetch several organisations by their e-mail domains in one request.

        Args:
            email_domains: The domains to look up. An empty sequence is a no-op.

        Returns:
            The organisations already known for those domains.
        """
        wanted = [domain.strip().lower() for domain in email_domains if domain.strip()]
        found: list[Organisation] = []
        for batch in batched(wanted, DATABASE_BATCH_SIZE):
            rows = self._select_every(
                lambda query, values=list(batch): query.in_("email_domain", values),
                "list_by_email_domains",
            )
            found.extend(self._to_models(rows))
        return found

    def find_by_name(self, name: str) -> Organisation | None:
        """Look an organisation up by the name it is written under.

        Args:
            name: The organisation's name, as the assessment reported it.

        Returns:
            The organisation, or ``None`` when no row carries that name.
        """
        rows = self._run(
            lambda: self._table().select(ALL_COLUMNS).eq("name", name.strip()).limit(1).execute(),
            "find_by_name",
        )
        return self._first(rows)

    def find_by_names(self, names: Sequence[str]) -> dict[str, Organisation]:
        """Look several organisations up by name, in one request where the names allow.

        Nothing stops two organisations carrying one name. :meth:`find_by_name`
        leaves the choice between them to the database, which answers with the
        row it stored first. Here the choice is written down: the oldest row
        wins, and the lowest identifier settles two rows of the same age.

        Args:
            names: The names to look up, as the assessment reported them.
                Blank names are ignored.

        Returns:
            The organisation stored under each name that has one, by that name.
        """
        wanted = list(dict.fromkeys(name.strip() for name in names if name.strip()))
        alone = [name for name in wanted if _UNLISTABLE_CHARACTERS.intersection(name)]
        together = [name for name in wanted if name not in alone]
        stored: list[Organisation] = []
        for batch in batched(together, NAME_LOOKUP_BATCH_SIZE):
            rows = self._select_every(
                lambda query, values=list(batch): query.in_("name", values),
                "find_by_names",
            )
            stored.extend(self._to_models(rows))
        found: dict[str, Organisation] = {}
        for organisation in sorted(stored, key=_oldest_first):
            found.setdefault(organisation.name, organisation)
        for name in alone:
            existing = self.find_by_name(name)
            if existing is not None:
                found[name] = existing
        return found

    def find_by_email_domain(self, email_domain: str) -> Organisation | None:
        """Look an organisation up by its e-mail domain.

        Args:
            email_domain: The domain part of an address, lower-case.

        Returns:
            The organisation, or ``None`` when the domain is unknown.
        """
        rows = self._run(
            lambda: self._table()
            .select(ALL_COLUMNS)
            .eq("email_domain", email_domain.strip().lower())
            .limit(1)
            .execute(),
            "find_by_email_domain",
        )
        return self._first(rows)


def _oldest_first(organisation: Organisation) -> tuple[bool, datetime | None, str]:
    """Sort key putting the row stored first ahead of a later one of the same name.

    The database stamps every row it stores. A row built in memory has no stamp
    yet and sorts ahead of the stamped ones.
    """
    return (organisation.created_at is not None, organisation.created_at, str(organisation.id))
