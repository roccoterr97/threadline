"""Read access to the ``people_overview`` view."""

from __future__ import annotations

from typing import ClassVar

from supabase import Client

from tracker.domain.models import PersonOverview
from tracker.repositories.base import SupabaseReader


class PeopleOverviewRepository(SupabaseReader[PersonOverview]):
    """One row per relevant person, with overrides already applied.

    This is what the dashboard and the morning e-mail read. It is a view, so it
    is read-only: corrections are written to ``person_overrides`` instead.
    """

    table_name: ClassVar[str] = "people_overview"
    order_column: ClassVar[str] = "last_contact_at"

    def __init__(self, client: Client) -> None:
        """Bind the repository to the shared Supabase client."""
        super().__init__(client, PersonOverview)
