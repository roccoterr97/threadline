"""Saving the owner's category choice and putting the profile into effect.

Both ``tracker profile choose`` and the set-up's categories step end here, so a
choice is saved the same way whichever of them asked for it: the preset is
remembered, the categories replace the owner's list, the stage labels and
suggestions are written, and the assessment guide is rendered again.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tracker.domain.categories import Category
from tracker.domain.profile import Profile
from tracker.repositories import Repositories
from tracker.services.profile.applier import ApplyReport, CategoryChanges, ProfileApplier
from tracker.services.profile.guide import write_guide
from tracker.services.profile.loader import load_profile


@dataclass(frozen=True, slots=True)
class Choice:
    """What the owner chose.

    Attributes:
        preset: The preset's name.
        profile: The preset itself: its wording, stage labels and guidance.
        categories: The categories to use, in order, ``unknown`` last.
    """

    preset: str
    profile: Profile
    categories: tuple[Category, ...]


@dataclass(frozen=True, slots=True)
class Effect:
    """What putting a profile into effect wrote.

    Attributes:
        applied: The stage labels and suggestions written.
        guide: The assessment guide written.
    """

    applied: ApplyReport
    guide: Path


@dataclass(frozen=True, slots=True)
class SavedChoice:
    """What saving a choice changed.

    Attributes:
        changes: How the owner's categories changed.
        effect: The stage labels, suggestions and guide written.
        profile_file_wins: True when a profile file exists, so its wording and
            stage labels are used instead of the chosen preset's.
    """

    changes: CategoryChanges
    effect: Effect
    profile_file_wins: bool


@dataclass(frozen=True, slots=True)
class ProfileFiles:
    """Where the profile's files are.

    Attributes:
        profile: The owner's own profile file, which wins over any preset.
        guide_template: The template the assessment guide is rendered from.
        guide: Where the rendered guide goes.
    """

    profile: Path
    guide_template: Path
    guide: Path


def put_into_effect(applier: ProfileApplier, profile: Profile, files: ProfileFiles) -> Effect:
    """Write the stage labels and suggestions, then render the guide.

    Args:
        applier: Writes to the database.
        profile: The profile to put into effect.
        files: Where the guide template is and where the guide goes.

    Returns:
        What was written.
    """
    applied = applier.apply(profile)
    guide = write_guide(profile, applier.current_categories(), files.guide_template, files.guide)
    return Effect(applied=applied, guide=guide)


class ChoiceSaver:
    """Reads and saves the owner's category choice in the database."""

    def __init__(
        self, repositories: Repositories, applier: ProfileApplier, files: ProfileFiles
    ) -> None:
        """Bind the saver to the database and the profile's files.

        Args:
            repositories: The repository container.
            applier: Writes categories, stage labels and suggestions.
            files: Where the profile's files are.
        """
        self._repositories = repositories
        self._applier = applier
        self._files = files

    def chosen_preset(self) -> str | None:
        """Return the preset the owner chose, or ``None`` when none was chosen yet."""
        return self._repositories.app_settings.read_preset()

    def save(self, choice: Choice) -> SavedChoice:
        """Replace the categories, remember the preset and put the profile into effect.

        The preset is remembered only once the categories are in, because a
        remembered preset is what tells the set-up its categories step is
        done: a choice that could not be saved must be asked for again.

        Args:
            choice: What the owner chose.

        Returns:
            What changed.

        Raises:
            ValidationFailedError: If two of the categories share a name.
            DatabaseUnavailableError: If the database could not be written.
        """
        changes = self._applier.replace_categories(choice.categories)
        self._repositories.app_settings.save_preset(choice.preset)
        loaded = load_profile(self._files.profile, chosen_preset=choice.preset)
        effect = put_into_effect(self._applier, loaded.profile, self._files)
        return SavedChoice(
            changes=changes,
            effect=effect,
            profile_file_wins=loaded.source == self._files.profile,
        )
