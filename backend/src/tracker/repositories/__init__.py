"""Data access layer: one repository per table, plus the dashboard view.

Everything that needs the database takes a :class:`Repositories` instance and
uses the repository it needs. A later plan that needs a new query adds a method
to the repository for the table it works with; nobody edits a shared list.
"""

from __future__ import annotations

from dataclasses import dataclass

from supabase import Client

from tracker.repositories.app_secrets import AppSecretRepository
from tracker.repositories.app_settings import AppSettingsRepository
from tracker.repositories.categories import CategoryRepository
from tracker.repositories.category_suggestions import CategorySuggestionRepository
from tracker.repositories.conversations import ConversationRepository
from tracker.repositories.messages import MessageRepository
from tracker.repositories.organisations import OrganisationRepository
from tracker.repositories.people import PersonRepository
from tracker.repositories.people_overview import PeopleOverviewRepository
from tracker.repositories.person_identities import PersonIdentityRepository
from tracker.repositories.person_notes import PersonNoteRepository
from tracker.repositories.person_overrides import PersonOverrideRepository
from tracker.repositories.person_states import PersonStateRepository
from tracker.repositories.review_items import ReviewItemRepository
from tracker.repositories.run_logs import RunLogRepository
from tracker.repositories.run_step_logs import RunStepLogRepository
from tracker.repositories.status_labels import StatusLabelRepository

__all__ = [
    "AppSecretRepository",
    "AppSettingsRepository",
    "CategoryRepository",
    "CategorySuggestionRepository",
    "ConversationRepository",
    "MessageRepository",
    "OrganisationRepository",
    "PeopleOverviewRepository",
    "PersonIdentityRepository",
    "PersonNoteRepository",
    "PersonOverrideRepository",
    "PersonRepository",
    "PersonStateRepository",
    "Repositories",
    "ReviewItemRepository",
    "RunLogRepository",
    "RunStepLogRepository",
    "StatusLabelRepository",
    "build_repositories",
]


@dataclass(frozen=True, slots=True)
class Repositories:
    """Every repository, built once and passed to the services that need them."""

    organisations: OrganisationRepository
    people: PersonRepository
    person_identities: PersonIdentityRepository
    conversations: ConversationRepository
    messages: MessageRepository
    person_states: PersonStateRepository
    person_overrides: PersonOverrideRepository
    person_notes: PersonNoteRepository
    review_items: ReviewItemRepository
    run_logs: RunLogRepository
    run_step_logs: RunStepLogRepository
    app_secrets: AppSecretRepository
    app_settings: AppSettingsRepository
    people_overview: PeopleOverviewRepository
    categories: CategoryRepository
    category_suggestions: CategorySuggestionRepository
    status_labels: StatusLabelRepository


def build_repositories(client: Client) -> Repositories:
    """Create every repository on top of one Supabase client.

    Args:
        client: The shared Supabase client.

    Returns:
        The repository container.
    """
    return Repositories(
        organisations=OrganisationRepository(client),
        people=PersonRepository(client),
        person_identities=PersonIdentityRepository(client),
        conversations=ConversationRepository(client),
        messages=MessageRepository(client),
        person_states=PersonStateRepository(client),
        person_overrides=PersonOverrideRepository(client),
        person_notes=PersonNoteRepository(client),
        review_items=ReviewItemRepository(client),
        run_logs=RunLogRepository(client),
        run_step_logs=RunStepLogRepository(client),
        app_secrets=AppSecretRepository(client),
        app_settings=AppSettingsRepository(client),
        people_overview=PeopleOverviewRepository(client),
        categories=CategoryRepository(client),
        category_suggestions=CategorySuggestionRepository(client),
        status_labels=StatusLabelRepository(client),
    )
