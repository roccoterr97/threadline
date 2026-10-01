"""Data access for ``organisations``."""

from __future__ import annotations

from collections.abc import Sequence
from itertools import batched
from typing import ClassVar

from supabase import Client

from tracker.domain.models import Organisation
from tracker.repositories.base import ALL_COLUMNS, SupabaseRepository
from tracker.shared.constants.collection import DATABASE_BATCH_SIZE


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
                lambda values=list(batch): self._table()
                .select(ALL_COLUMNS)
                .in_("email_domain", values),
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
