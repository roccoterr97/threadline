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

No two categories may share a name or a group name, archived ones included,
because an archived category still shows as a column while somebody has it.
So when the new list gives a name to a category that another row still holds
(the job-search preset's `vc`, "Investor", when the fundraising preset brings
`investor`, "Investor"), that row is told apart first, the way migration 0015
tells existing clashes apart: "Investor (2)". Its key and its people stay as
they are, and doing it again changes nothing more.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from tracker.domain.categories import (
    UNKNOWN_CATEGORY,
    UNKNOWN_CATEGORY_KEY,
    Category,
    NameField,
    comparable_name,
    free_name,
    name_in,
    names_used_twice,
)
from tracker.domain.models import CategoryRecord
from tracker.domain.profile import Profile
from tracker.repositories import Repositories
from tracker.shared.clock import Clock
from tracker.shared.errors import ValidationFailedError
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
        renamed: Archived categories given a new name because the new list
            uses their old one, as they are now called.
    """

    saved: tuple[str, ...]
    archived: tuple[str, ...]
    deleted: tuple[str, ...]
    renamed: tuple[Category, ...] = ()


@dataclass(frozen=True, slots=True)
class _Replacement:
    """What replacing the categories writes before the new list itself.

    Attributes:
        deleted: Keys of the dropped categories nobody has.
        archived: Keys of the dropped categories somebody still has.
        set_aside: Rows to write first: the archived ones, and any row that
            must give up a name the new list hands to another category.
        renamed: The archived categories that got a new name.
    """

    deleted: tuple[str, ...]
    archived: tuple[str, ...]
    set_aside: list[CategoryRecord]
    renamed: tuple[Category, ...]


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

        Dropped categories are deleted or archived first, so the list never
        holds more than the database allows at any moment, and any row
        holding a name the new list gives another category is told apart
        first, so no write breaks the rule that names are unique. Nothing is
        written when the list itself names two categories alike, and a run
        that stopped half-way is finished by running it again.

        Args:
            categories: The new list. ``unknown`` is kept whether it is in the
                list or not.

        Returns:
            What changed.

        Raises:
            ValidationFailedError: If two categories in the list share a name
                or a group name.
            DatabaseUnavailableError: If the database could not be written.
        """
        if all(category.key != UNKNOWN_CATEGORY_KEY for category in categories):
            categories = (*categories, UNKNOWN_CATEGORY)
        _refuse_names_used_twice(categories)
        wanted = [CategoryRecord.of(category) for category in categories]
        replacement = self._prepare(wanted)
        self._repositories.categories.delete_by_keys(replacement.deleted)
        self._repositories.categories.save(replacement.set_aside)
        # The database seeds `unknown` and refuses any change to it, so writing
        # it would only fail once its words and this copy's differ.
        self._repositories.categories.save(
            [record for record in wanted if record.key != UNKNOWN_CATEGORY_KEY]
        )
        changes = CategoryChanges(
            saved=tuple(record.key for record in wanted),
            archived=replacement.archived,
            deleted=replacement.deleted,
            renamed=replacement.renamed,
        )
        _log.info(
            "categories_replaced",
            saved=len(changes.saved),
            archived=len(changes.archived),
            deleted=len(changes.deleted),
            renamed=len(changes.renamed),
        )
        return changes

    def _prepare(self, wanted: Sequence[CategoryRecord]) -> _Replacement:
        """Work out what to delete, archive and rename before the new list is written."""
        wanted_keys = {record.key for record in wanted}
        existing = self._repositories.categories.list_all()
        deleted = tuple(
            row.key for row in existing if row.key not in wanted_keys and not self._in_use(row.key)
        )
        staying = [
            row if row.key in wanted_keys else self._archived(row)
            for row in existing
            if row.key not in deleted
        ]
        archived = tuple(row.key for row in staying if row.key not in wanted_keys)
        moved = _out_of_the_way(staying, wanted)
        return _Replacement(
            deleted=deleted,
            archived=archived,
            set_aside=[
                moved.get(row.key, row)
                for row in staying
                if row.key in archived or row.key in moved
            ],
            renamed=tuple(moved[key].to_category() for key in archived if key in moved),
        )

    def _archived(self, row: CategoryRecord) -> CategoryRecord:
        """The row archived, keeping the moment it was first archived."""
        return row.model_copy(update={"archived_at": row.archived_at or self._clock.now()})

    def _in_use(self, key: str) -> bool:
        """Whether a person or an override still names a category."""
        people = self._repositories.people
        return people.uses_category(key) or self._repositories.person_overrides.uses_category(key)


def _refuse_names_used_twice(categories: Sequence[Category]) -> None:
    """Refuse a list the database would refuse, before anything is written.

    Raises:
        ValidationFailedError: If two categories share a name or a group name.
    """
    clashes = names_used_twice(categories)
    if not clashes:
        return
    names = ", ".join(f'"{name}"' for name in clashes)
    message = f"two categories in the list share a name: {names} - give each its own"
    raise ValidationFailedError(message)


def _out_of_the_way(
    rows: Sequence[CategoryRecord], wanted: Sequence[CategoryRecord]
) -> dict[str, CategoryRecord]:
    """Give each row holding a name the new list gives another category a free one.

    The database checks a unique index row by row, so even two categories of
    the new list swapping their names need one of them to let go first; the
    new list's own write then gives it its new name.

    Args:
        rows: The rows that stay while the new list is written.
        wanted: The new list.

    Returns:
        The rows that must change first, by key. ``unknown`` never changes.
    """
    moved: dict[str, CategoryRecord] = {}
    for field in NameField:
        claimed = {comparable_name(name_in(record, field)): record.key for record in wanted}
        taken = set(claimed) | {comparable_name(name_in(row, field)) for row in rows}
        for row in rows:
            current = moved.get(row.key, row)
            name = name_in(current, field)
            if (
                row.key == UNKNOWN_CATEGORY_KEY
                or claimed.get(comparable_name(name), row.key) == row.key
            ):
                continue
            new_name = free_name(name, taken)
            taken.add(comparable_name(new_name))
            moved[row.key] = current.model_copy(update={field.value: new_name})
    return moved
