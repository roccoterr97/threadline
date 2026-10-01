"""The owner's profile: what they track, and the words used for it.

A profile is chosen from a preset (job search, sales outreach, fundraising…)
and may be edited by the owner. It holds:

* the wording of the product — what "relevant" means, the question asked when
  the AI is unsure;
* the categories it suggests people be sorted into (see
  :mod:`tracker.domain.categories`). They are suggestions: once set up, the
  owner's list lives in the database and is edited on the dashboard;
* a label and a description for each of the six fixed stages;
* the guidance paragraphs the assessment helper reads;
* the collection rules that only make sense for this kind of work (see
  :mod:`tracker.domain.rules`).

The six stages themselves are not the profile's to change: the rule that marks
a conversation "gone quiet", the active list and the stages a date never
overrides are built on them.
"""

from __future__ import annotations

from typing import Annotated, Final, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from tracker.domain.categories import (
    RESERVED_CATEGORY_KEYS,
    UNKNOWN_CATEGORY,
    Category,
    CategoryKey,
    ColourSlot,
    Description,
    Label,
)
from tracker.domain.enums import ContactStatus
from tracker.domain.rules import RulePack
from tracker.shared.constants.profile import MAX_CATEGORIES, MAX_GUIDANCE_LENGTH

#: The placeholder the relevance question must contain once.
NAME_PLACEHOLDER: Final[str] = "{name}"

#: Gap between two categories' sort orders, so one can later be slotted between.
SORT_ORDER_STEP: Final[int] = 10

_FROZEN: Final[ConfigDict] = ConfigDict(extra="forbid", frozen=True)

#: A paragraph of guidance or wording, in Markdown.
Text = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_GUIDANCE_LENGTH),
]


class Wording(BaseModel):
    """The product's words for what the owner tracks.

    Attributes:
        subject: What the owner is doing, as it reads after "part of", such
            as "your job search".
        relevance_question: The Yes/No question asked about a person the AI
            was unsure about. Contains ``{name}`` once.
        relevant_means: What makes a person relevant, one sentence.
    """

    model_config = _FROZEN

    subject: Label
    relevance_question: Text
    relevant_means: Text

    @model_validator(mode="after")
    def _question_names_the_person(self) -> Self:
        """Refuse a question that would not say who it is about."""
        if self.relevance_question.count(NAME_PLACEHOLDER) != 1:
            message = f"relevance_question must contain {NAME_PLACEHOLDER} exactly once"
            raise ValueError(message)
        return self

    def question_about(self, full_name: str) -> str:
        """Word the relevance question about one person.

        Args:
            full_name: The person's name.

        Returns:
            The question, ready to store.
        """
        return self.relevance_question.replace(NAME_PLACEHOLDER, full_name)


class StageWording(BaseModel):
    """What one of the six stages is called, and what it means."""

    model_config = _FROZEN

    label: Label
    description: Description = Field(min_length=1)


class Guidance(BaseModel):
    """The preset-specific paragraphs of the assessment guide, in Markdown.

    Attributes:
        status_examples: Example situations and the stage each one is.
        summary_example: One good summary, as the helper should write it.
        relevance: What counts as relevant and as noise for this kind of work,
            including any special cases such as mail from a hiring system.
    """

    model_config = _FROZEN

    status_examples: Text
    summary_example: Text
    relevance: Text


class CategoryEntry(BaseModel):
    """One category as the owner writes it in the profile file.

    The position in the file decides the order; ``unknown`` is added by the
    tracker and may not be written here.
    """

    model_config = _FROZEN

    key: CategoryKey
    label: Label
    group_label: Label
    description: Description = Field(min_length=1)
    colour: ColourSlot


class Profile(BaseModel):
    """A whole profile, validated.

    Attributes:
        name: The preset it started from, such as ``job_search``.
        title: A human name for it, such as "Job search".
        wording: The product's words.
        categories: The suggested categories, in order, without ``unknown``.
        stages: A label and a description for each of the six stages.
        guidance: The preset-specific paragraphs of the guide.
        rules: The collection rules this kind of work adds to the general
            ones; none when the profile has no ``[rules]`` part.
    """

    model_config = _FROZEN

    name: Label
    title: Label
    wording: Wording
    categories: tuple[CategoryEntry, ...] = Field(min_length=1, max_length=MAX_CATEGORIES)
    stages: dict[ContactStatus, StageWording]
    guidance: Guidance
    rules: RulePack = RulePack()

    @model_validator(mode="after")
    def _check_categories_and_stages(self) -> Self:
        """Refuse duplicate or reserved keys and a missing stage."""
        keys = [entry.key for entry in self.categories]
        reserved = sorted(RESERVED_CATEGORY_KEYS.intersection(keys))
        if reserved:
            message = f"these keys are reserved by Threadline: {', '.join(reserved)}"
            raise ValueError(message)
        duplicates = sorted({key for key in keys if keys.count(key) > 1})
        if duplicates:
            message = f"category keys must be unique: {', '.join(duplicates)}"
            raise ValueError(message)
        missing = [status.value for status in ContactStatus if status not in self.stages]
        if missing:
            message = f"every stage needs a label and a description: {', '.join(missing)}"
            raise ValueError(message)
        return self

    def suggestions(self) -> tuple[Category, ...]:
        """Return the suggested categories in file order, without ``unknown``.

        Returns:
            The suggestions, numbered in steps of :data:`SORT_ORDER_STEP`.
        """
        return tuple(
            Category(
                key=entry.key,
                label=entry.label,
                group_label=entry.group_label,
                description=entry.description,
                colour=entry.colour,
                sort_order=(position + 1) * SORT_ORDER_STEP,
            )
            for position, entry in enumerate(self.categories)
        )

    def all_categories(self) -> tuple[Category, ...]:
        """Return every suggestion and ``unknown`` last: a whole list to start from.

        Returns:
            The categories as the database would hold them.
        """
        return (*self.suggestions(), UNKNOWN_CATEGORY)

    def stage(self, status: ContactStatus) -> StageWording:
        """Return the wording of one stage.

        Args:
            status: The stage.

        Returns:
            Its label and description.
        """
        return self.stages[status]
