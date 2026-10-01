"""The profile commands: check a profile, choose categories, put it all into effect.

``tracker profile check`` reads a profile and prints what it defines, touching
nothing. ``tracker profile choose`` asks, in the terminal, which preset fits and
which categories to keep or add, and saves the answers to the database.
``tracker profile apply`` writes the stage labels and the suggestions, and
renders ``docs/assessment-guide.md`` from the profile and the owner's
categories as the database holds them — so an edit made on the dashboard
reaches the AI helper the next time it runs. With no profile file and no chosen
preset, the job-search preset is used, and the commands say so.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Final

import typer

from tracker.domain.categories import Category
from tracker.domain.enums import ContactStatus
from tracker.domain.profile import Profile
from tracker.infrastructure.database import create_database_client
from tracker.infrastructure.terminal_io import TerminalIO
from tracker.repositories import Repositories, build_repositories
from tracker.services.profile.applier import CategoryChanges, ProfileApplier
from tracker.services.profile.choice import (
    ChoiceSaver,
    Effect,
    ProfileFiles,
    put_into_effect,
)
from tracker.services.profile.chooser import CategoryChooser, category_line
from tracker.services.profile.loader import (
    LoadedProfile,
    load_profile,
    preset_path,
    read_profile,
)
from tracker.shared.clock import SystemClock
from tracker.shared.config import REPOSITORY_ROOT, get_settings
from tracker.shared.constants.profile import (
    DEFAULT_PRESET,
    GUIDE_FILE,
    GUIDE_TEMPLATE_FILE,
    PROFILE_FILE,
)

#: Panel the root help groups these commands under.
HELP_PANEL: Final[str] = "profile"

#: Separates the parts of one printed line.
_DOT: Final[str] = " · "

profile_app = typer.Typer(
    help="Choose your categories, check your profile, and put it into effect.",
    no_args_is_help=True,
)

FileOption = Annotated[
    Path,
    typer.Option("--file", help="Profile file to use.", show_default=False),
]

PresetOption = Annotated[
    str | None,
    typer.Option("--preset", help="Use this shipped preset.", show_default=False),
]

GuideOption = Annotated[
    Path,
    typer.Option("--guide", help="Where to write the assessment guide.", show_default=False),
]

CategoriesOption = Annotated[
    bool,
    typer.Option(
        "--categories",
        help="Also replace your categories with the profile's list.",
        show_default=False,
    ),
]


def register(cli: typer.Typer) -> None:
    """Attach the profile commands to the root application.

    Args:
        cli: The root Typer application.
    """
    cli.add_typer(profile_app, name="profile", rich_help_panel=HELP_PANEL)


@profile_app.command("check")
def check(file: FileOption = PROFILE_FILE, preset: PresetOption = None) -> None:
    """Read a profile and print what it defines. Changes nothing."""
    loaded = _read(file, preset)
    _print_source(loaded)
    _print_categories("suggested categories:", loaded.profile.all_categories())
    _print_stages(loaded.profile)


@profile_app.command("apply")
def apply(
    file: FileOption = PROFILE_FILE,
    guide: GuideOption = GUIDE_FILE,
    categories: CategoriesOption = False,
) -> None:
    """Write the stage labels and suggestions, and render the assessment guide."""
    repositories = _repositories()
    applier = _applier(repositories)
    loaded = load_profile(file, chosen_preset=repositories.app_settings.read_preset())
    _print_source(loaded)
    if categories:
        _print_changes(applier.replace_categories(loaded.profile.all_categories()))
    _print_effect(put_into_effect(applier, loaded.profile, _files(file, guide)))


@profile_app.command("choose")
def choose(preset: PresetOption = None, guide: GuideOption = GUIDE_FILE) -> None:
    """Pick a preset, keep the suggestions you use, add your own. Saved to the database."""
    choice = CategoryChooser(TerminalIO()).choose(preset)
    if choice is None:
        typer.echo("nothing saved")
        return
    repositories = _repositories()
    saver = ChoiceSaver(repositories, _applier(repositories), _files(PROFILE_FILE, guide))
    saved = saver.save(choice)
    _print_changes(saved.changes)
    if saved.profile_file_wins:
        typer.echo(
            f"notice: {_shown(PROFILE_FILE)} exists, so its wording and stage labels are "
            "still used. Remove it to use the preset you chose."
        )
    _print_effect(saved.effect)


def _print_effect(effect: Effect) -> None:
    """Print what putting the profile into effect wrote."""
    typer.echo(f"stage labels saved: {effect.applied.stages}")
    typer.echo(f"suggestions saved: {effect.applied.suggestions}")
    typer.echo(f"guide written: {_shown(effect.guide)}")


def _files(profile: Path, guide: Path) -> ProfileFiles:
    """Name the profile file, the guide template and where the guide goes."""
    return ProfileFiles(profile=profile, guide_template=GUIDE_TEMPLATE_FILE, guide=guide)


def _read(file: Path, preset: str | None) -> LoadedProfile:
    """Read the named preset, or the profile file with its fallback."""
    if preset is None:
        return load_profile(file)
    path = preset_path(preset)
    return LoadedProfile(read_profile(path), path, is_default=False)


def _repositories() -> Repositories:
    """Build the repositories on a fresh database client."""
    return build_repositories(create_database_client(get_settings()))


def _applier(repositories: Repositories) -> ProfileApplier:
    """Build the applier with a clock in the owner's time zone."""
    return ProfileApplier(repositories, SystemClock(get_settings().owner_zone))


def _print_source(loaded: LoadedProfile) -> None:
    """Say which file the profile came from, and whether it is the fallback."""
    profile = loaded.profile
    typer.echo(f"profile: {profile.title} ({profile.name}) from {_shown(loaded.source)}")
    if loaded.is_default:
        typer.echo(
            f"notice: no {_shown(PROFILE_FILE)} and no chosen preset, so the {DEFAULT_PRESET} "
            "preset is used. Run `tracker profile choose` or see docs/customising.md."
        )


def _print_categories(title: str, categories: Sequence[Category]) -> None:
    """Print categories, one per line."""
    typer.echo(title)
    for category in categories:
        typer.echo(category_line(category))


def _print_stages(profile: Profile) -> None:
    """Print the label of each of the six stages."""
    typer.echo("stages:")
    for status in ContactStatus:
        typer.echo(f"  {status.value}: {profile.stage(status).label}")


def _print_changes(changes: CategoryChanges) -> None:
    """Print what replacing the categories changed."""
    typer.echo(
        f"categories saved: {len(changes.saved)}{_DOT}"
        f"archived: {_listed(changes.archived)}{_DOT}deleted: {_listed(changes.deleted)}"
    )


def _listed(keys: tuple[str, ...]) -> str:
    """Show a list of keys, or 'none'."""
    return ", ".join(keys) if keys else "none"


def _shown(path: Path) -> str:
    """Show a path relative to the repository when it is inside it."""
    if path.is_relative_to(REPOSITORY_ROOT):
        return str(path.relative_to(REPOSITORY_ROOT))
    return str(path)
