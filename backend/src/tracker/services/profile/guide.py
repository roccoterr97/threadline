"""Render the assessment guide from its template and the owner's profile.

``docs/assessment-guide.md`` is what the assessment helper reads. Most of it is
fixed — what "waiting on" means, how confidence works, what the helper never
does — and lives in ``profile/assessment-guide.template.md``. The parts that
depend on what the owner tracks are filled in from the profile:

``{{subject}}``, ``{{relevant_means}}``
    The profile's wording.
``{{stage_table}}``, ``{{category_table}}``
    The six stages and the owner's categories, as tables. The categories are
    the ones in the database — what the owner set on the dashboard — so a
    change there reaches the helper the next time the guide is rendered.
``{{stage_examples}}``, ``{{summary_example}}``, ``{{relevance_guidance}}``
    The profile's guidance paragraphs.
``{{stage:<status>}}``
    One stage's label, such as ``{{stage:in_process}}``. Also allowed inside
    the profile's guidance, so renaming a stage renames it everywhere.
``{{generated_notice}}``
    A comment saying where the page comes from.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Final

from tracker.domain.categories import Category
from tracker.domain.enums import ContactStatus
from tracker.domain.profile import Profile
from tracker.shared.errors import ConfigurationError

#: ``{{name}}`` or ``{{name:argument}}``.
_PLACEHOLDER: Final[re.Pattern[str]] = re.compile(r"\{\{\s*([a-z_]+)(?::([a-z_]+))?\s*\}\}")

#: The one placeholder that takes an argument.
_STAGE: Final[str] = "stage"

#: Said after the owner's description of "gone quiet", whatever it is: the stage
#: is set by a date rule, never by the helper.
_GONE_QUIET_RULE: Final[str] = (
    "**Threadline sets this one by date — the helper never has to.** A first message "
    "nobody ever answered is *not* this; it is still {contacted}."
)

_STAGE_TABLE_HEAD: Final[str] = (
    "| Status | On screen | It means |\n|--------|-----------|----------|"
)
_CATEGORY_TABLE_HEAD: Final[str] = (
    "| Value | On screen | It means |\n|-------|-----------|----------|"
)


def render_guide(
    template: str,
    profile: Profile,
    categories: Sequence[Category],
    *,
    template_name: str,
) -> str:
    """Fill a guide template in from a profile and the owner's categories.

    Args:
        template: The template's text.
        profile: The owner's profile.
        categories: The categories the helper may choose from, in order.
        template_name: How the template is named in the generated notice.

    Returns:
        The guide, ready to write.

    Raises:
        ConfigurationError: If the template or the profile's guidance uses a
            placeholder that does not exist.
    """
    guidance = profile.guidance
    values = {
        "generated_notice": _notice(profile, template_name),
        "subject": profile.wording.subject,
        "relevant_means": _cell(profile.wording.relevant_means),
        "stage_table": _stage_table(profile),
        "category_table": _category_table(categories),
        "stage_examples": _fill(guidance.status_examples, profile, {}),
        "summary_example": _fill(guidance.summary_example, profile, {}),
        "relevance_guidance": _fill(guidance.relevance, profile, {}),
    }
    return _fill(template, profile, values)


def write_guide(
    profile: Profile,
    categories: Sequence[Category],
    template_file: Path,
    guide_file: Path,
) -> Path:
    """Render the guide and write it where the assessment helper reads it.

    Args:
        profile: The owner's profile.
        categories: The categories the helper may choose from, in order.
        template_file: The template to render.
        guide_file: Where the guide goes.

    Returns:
        The file written.

    Raises:
        ConfigurationError: If the template is missing or broken.
    """
    try:
        template = template_file.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        message = f"guide template {template_file.name} not found"
        raise ConfigurationError(message) from error
    guide = render_guide(template, profile, categories, template_name=template_file.name)
    guide_file.write_text(guide, encoding="utf-8")
    return guide_file


def _fill(text: str, profile: Profile, values: Mapping[str, str]) -> str:
    """Replace every placeholder in one text."""
    return _PLACEHOLDER.sub(_replacer(profile, values), text)


def _replacer(profile: Profile, values: Mapping[str, str]) -> Callable[[re.Match[str]], str]:
    """Build the function that turns one placeholder into its text."""

    def replace(match: re.Match[str]) -> str:
        name, argument = match.group(1), match.group(2)
        if name == _STAGE and argument in ContactStatus:
            return profile.stage(ContactStatus(argument)).label
        if argument is None and name in values:
            return values[name]
        message = f"unknown placeholder {match.group(0)} in the guide or the profile"
        raise ConfigurationError(message)

    return replace


def _stage_table(profile: Profile) -> str:
    """The six stages: key, label and meaning."""
    contacted = profile.stage(ContactStatus.CONTACTED_NO_REPLY).label
    rows = [_STAGE_TABLE_HEAD]
    for status in ContactStatus:
        stage = profile.stage(status)
        meaning = _cell(stage.description)
        if status is ContactStatus.GONE_QUIET:
            meaning = f"{meaning} {_GONE_QUIET_RULE.format(contacted=_cell(contacted))}"
        rows.append(f"| `{status.value}` | {_cell(stage.label)} | {meaning} |")
    return "\n".join(rows)


def _category_table(categories: Sequence[Category]) -> str:
    """Every category: key, label and who belongs there."""
    rows = [_CATEGORY_TABLE_HEAD]
    rows.extend(
        f"| `{category.key}` | {_cell(category.label)} | {_cell(category.description)} |"
        for category in categories
    )
    return "\n".join(rows)


def _notice(profile: Profile, template_name: str) -> str:
    """The comment at the top of the generated page."""
    return (
        f"<!-- Generated by `tracker profile apply` from profile/{template_name}, the "
        f'"{profile.title}" profile and your categories (Settings page of the dashboard). '
        "Edit those, not this page. -->"
    )


def _cell(text: str) -> str:
    """Make text safe inside one Markdown table cell."""
    return " ".join(text.split()).replace("|", "\\|")
