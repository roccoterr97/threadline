"""Put the owner's profile and category choices into the database.

After the first setup the database's ``categories`` table is the owner's list:
they edit it on the dashboard's Settings page, or with ``tracker profile
choose``. The profile file (or the preset the owner chose) keeps supplying what
the dashboard cannot edit — the stage labels, the wording, the AI guidance —
and the suggestions the dashboard offers. So:

* :meth:`ProfileApplier.apply` writes the stage labels and the suggestions and
  never touches the owner's categories — safe to run every morning;
* :meth:`ProfileApplier.replace_categories` makes the owner's list exactly a
  given one, and runs only when the owner asks for it.

A category dropped from the list is deleted when nobody has it, and archived
when somebody still does: deleting it would either fail (the database refuses)
or silently relabel people the owner sorted by hand. An archived category keeps
labelling those people but is no longer offered to the AI or to the owner.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from tracker.domain.categories import UNKNOWN_CATEGORY, UNKNOWN_CATEGORY_KEY, Category
from tracker.domain.models import CategoryRecord
from tracker.domain.profile import Profile
from tracker.repositories import Repositories
from tracker.shared.clock import Clock
from tracker.shared.logging import get_logger

_log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ApplyReport:
    """What applying a profile wrote.

    Attributes:
        stages: How many stage labels were written.
        suggestions: How many suggested categories are stored.
    """

    stages: int
    suggestions: int


@dataclass(frozen=True, slots=True)
class CategoryChanges:
    """What replacing the owner's categories changed.

    Attributes:
        saved: Keys of the categories now in use, in order.
        archived: Keys of the categories kept only because people have them.
        deleted: Keys of the categories removed.
    """

    saved: tuple[str, ...]
    archived: tuple[str, ...]
    deleted: tuple[str, ...]


class ProfileApplier:
    """Writes stage labels, suggestions and, when asked, the owner's categories."""

    def __init__(self, repositories: Repositories, clock: Clock) -> None:
        """Bind the applier to its dependencies.

        Args:
            repositories: The repository container.
            clock: Stamps the moment a category is archived.
        """
        self._repositories = repositories
        self._clock = clock

    def apply(self, profile: Profile) -> ApplyReport:
        """Write a profile's stage labels and suggested categories.

        The owner's own categories are left exactly as they are.

        Args:
            profile: The owner's profile.

        Returns:
            What was written.
        """
        labels = {status: stage.label for status, stage in profile.stages.items()}
        self._repositories.status_labels.save(labels)
        suggestions = self._repositories.category_suggestions.replace(profile.suggestions())
        _log.info("profile_applied", profile=profile.name, suggestions=suggestions)
        return ApplyReport(stages=len(labels), suggestions=suggestions)

    def current_categories(self) -> tuple[Category, ...]:
        """Return the owner's categories still in use, in order, ``unknown`` last.

        Returns:
            The categories the AI may choose from.
        """
        rows = self._repositories.categories.list_all()
        return tuple(row.to_category() for row in rows if row.archived_at is None)

    def replace_categories(self, categories: Sequence[Category]) -> CategoryChanges:
        """Make the owner's categories exactly the given ones.

        Dropped categories are archived or deleted first, so the list never
        holds more than the database allows at any moment.

        Args:
            categories: The new list. ``unknown`` is kept whether it is in the
                list or not.

        Returns:
            What changed.
        """
        if all(category.key != UNKNOWN_CATEGORY_KEY for category in categories):
            categories = (*categories, UNKNOWN_CATEGORY)
        wanted = [CategoryRecord.of(category) for category in categories]
        wanted_keys = {record.key for record in wanted}
        dropped = [
            row for row in self._repositories.categories.list_all() if row.key not in wanted_keys
        ]
        in_use = [row for row in dropped if self._in_use(row.key)]
        unused = tuple(row.key for row in dropped if row not in in_use)
        archived = [
            row.model_copy(update={"archived_at": row.archived_at or self._clock.now()})
            for row in in_use
        ]
        self._repositories.categories.save(archived)
        self._repositories.categories.delete_by_keys(unused)
        self._repositories.categories.save(wanted)
        changes = CategoryChanges(
            saved=tuple(record.key for record in wanted),
            archived=tuple(row.key for row in archived),
            deleted=unused,
        )
        _log.info(
            "categories_replaced",
            saved=len(changes.saved),
            archived=len(changes.archived),
            deleted=len(changes.deleted),
        )
        return changes

    def _in_use(self, key: str) -> bool:
        """Whether a person or an override still names a category."""
        people = self._repositories.people
        return people.uses_category(key) or self._repositories.person_overrides.uses_category(key)
