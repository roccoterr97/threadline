"""The conversation in which the owner chooses their categories.

The owner picks a preset, keeps the suggestions they use, adds their own, sees
the final list and confirms it. The questions go through the set-up's
conversation port, so ``tracker profile choose`` and ``tracker setup
categories`` ask exactly the same way, and both are tested without a terminal.
Nothing here writes anything: the answers come back as a
:class:`~tracker.services.profile.choice.Choice`. Typed answers are validated
with the same rules the database enforces, and a bad answer is asked again
rather than ending the conversation.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from pydantic import ValidationError

from tracker.domain.categories import (
    UNKNOWN_CATEGORY,
    UNKNOWN_CATEGORY_KEY,
    Category,
    ColourSlot,
    NameField,
    comparable_name,
    key_for,
    name_in,
)
from tracker.domain.profile import SORT_ORDER_STEP, Profile
from tracker.services.profile.choice import Choice
from tracker.services.profile.loader import (
    describe_problems,
    preset_names,
    preset_path,
    read_profile,
)
from tracker.services.setup.ports import SetupIO
from tracker.shared.constants.profile import DEFAULT_PRESET, MAX_CATEGORIES
from tracker.shared.errors import ValidationFailedError

#: Colours offered for a category of the owner's own, grey being for "unknown".
_OWN_COLOURS: Final[tuple[ColourSlot, ...]] = tuple(
    slot for slot in ColourSlot if slot is not ColourSlot.GREY
)

#: Added to a name to suggest its plural.
_PLURAL_SUFFIX: Final[str] = "s"

#: Separates the parts of one listed category.
_DOT: Final[str] = " · "


def category_line(category: Category) -> str:
    """Describe one category on one line, as every category list shows it.

    Args:
        category: The category.

    Returns:
        Its key, label, group label (when it differs) and colour, noting that
        ``unknown`` stays.
    """
    reserved = f"{_DOT}always there" if category.key == UNKNOWN_CATEGORY_KEY else ""
    group = "" if category.group_label == category.label else f" ({category.group_label})"
    return f"  {category.key}: {category.label}{group}{_DOT}{category.colour.value}{reserved}"


class CategoryChooser:
    """Asks which preset fits, which suggestions to keep and what to add."""

    def __init__(self, io: SetupIO) -> None:
        """Bind the chooser to the conversation.

        Args:
            io: Where the questions are asked.
        """
        self._io = io

    def choose(self, preset: str | None = None) -> Choice | None:
        """Walk the owner through choosing a preset and its categories.

        Args:
            preset: A preset already named; asked for if not.

        Returns:
            The confirmed choice, not yet saved, or ``None`` when the owner
            did not confirm the final list.
        """
        name = preset or self._ask_preset()
        profile = read_profile(preset_path(name))
        chosen = self._ask_own(self._ask_suggestions(profile))
        numbered = tuple(
            category.model_copy(update={"sort_order": (position + 1) * SORT_ORDER_STEP})
            for position, category in enumerate(chosen)
        )
        choice = Choice(preset=name, profile=profile, categories=(*numbered, UNKNOWN_CATEGORY))
        self._io.say("Your categories:")
        for category in choice.categories:
            self._io.say(category_line(category))
        if not self._io.confirm("Save these? They replace your current categories.", default=True):
            return None
        return choice

    def _ask_preset(self) -> str:
        """Ask which preset fits, by number."""
        names = preset_names()
        self._io.say("Which of these is closest to what you track?")
        for number, name in enumerate(names, start=1):
            self._io.say(f"  {number}. {read_profile(preset_path(name)).title}")
        default = str(names.index(DEFAULT_PRESET) + 1)
        while True:
            answer = self._io.ask("Number", default=default).strip()
            if answer.isdigit() and 1 <= int(answer) <= len(names):
                return names[int(answer) - 1]
            self._io.say(f"Please type a number from 1 to {len(names)}.")

    def _ask_suggestions(self, profile: Profile) -> list[Category]:
        """Offer every suggestion at once; ask one by one only when the owner wants to pick."""
        suggestions = list(profile.suggestions())
        self._io.say("Suggested categories for this purpose:")
        for category in suggestions:
            self._io.say(category_line(category))
        if self._io.confirm("Use all of them?", default=True):
            return suggestions
        self._io.say("Keep the ones you use:")
        return [
            category
            for category in suggestions
            if self._io.confirm(
                f'  Keep "{category.label}" ({category.description})?', default=True
            )
        ]

    def _ask_own(self, chosen: list[Category]) -> list[Category]:
        """Offer to add categories of the owner's own until they stop or the list is full."""
        while len(chosen) < MAX_CATEGORIES and self._io.confirm(
            "Add a category of your own?", default=False
        ):
            chosen = [*chosen, self._ask_one(chosen)]
        if len(chosen) >= MAX_CATEGORIES:
            self._io.say(f"That is {MAX_CATEGORIES} categories, the most the dashboard can show.")
        return chosen

    def _ask_one(self, chosen: Sequence[Category]) -> Category:
        """Ask for one category of the owner's own, again until it is valid."""
        used = {category.colour for category in chosen}
        colour = next((slot for slot in _OWN_COLOURS if slot not in used), _OWN_COLOURS[0])
        while True:
            label = self._io.ask("  Name (for example: Supplier)")
            group_label = self._io.ask(
                "  Name for a group", default=f"{label.strip()}{_PLURAL_SUFFIX}"
            )
            description = self._io.ask("  Who belongs here (the AI reads this)")
            picked = self._io.ask(
                f"  Colour ({', '.join(slot.value for slot in _OWN_COLOURS)})",
                default=colour.value,
            )
            try:
                return _own_category(chosen, label, group_label, description, picked)
            except ValidationFailedError as error:
                self._io.say(f"  That did not work: {error.message}. Please try again.")


def _own_category(
    chosen: Sequence[Category], label: str, group_label: str, description: str, colour: str
) -> Category:
    """Build one of the owner's categories, refusing a name the list already has.

    The name and the group name are each checked, as the database checks each
    against every other category's.

    Raises:
        ValidationFailedError: If a value breaks the database's rules, or the
            name or the group name is already taken.
    """
    taken = (*chosen, UNKNOWN_CATEGORY)
    _refuse_taken(taken, NameField.LABEL, label, "category")
    _refuse_taken(taken, NameField.GROUP_LABEL, group_label, "group")
    try:
        return Category.model_validate(
            {
                "key": key_for(label, {category.key for category in chosen}),
                "label": label,
                "group_label": group_label,
                "description": description,
                "colour": colour,
                "sort_order": 0,
            }
        )
    except ValidationError as error:
        raise ValidationFailedError(describe_problems(error)) from error


def _refuse_taken(taken: Sequence[Category], field: NameField, typed: str, wording: str) -> None:
    """Refuse a name one of ``taken`` already has, whatever its capitals and spaces.

    Raises:
        ValidationFailedError: If it is taken.
    """
    wanted = comparable_name(typed)
    if any(comparable_name(name_in(category, field)) == wanted for category in taken):
        message = f'you already have a {wording} called "{typed.strip()}"'
        raise ValidationFailedError(message)
