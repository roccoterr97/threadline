"""The commands around the assessment.

``tracker ai export`` writes the questions, a Claude Code session answers them in
files, and ``tracker ai import`` checks those answers, saves them and removes
the files it applied. ``tracker ai clean`` removes whatever is left. No command
here calls an AI service: the judging happens inside the session, on the owner's
Claude subscription.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Final

import typer

from tracker.domain.profile import Wording
from tracker.infrastructure.database import create_database_client
from tracker.repositories import Repositories, build_repositories
from tracker.services.assessment.exporter import AssessmentExporter
from tracker.services.assessment.importer import AssessmentImporter
from tracker.services.assessment.work_files import clean_work_directory
from tracker.services.identity.matcher import read_every
from tracker.services.profile.loader import load_profile
from tracker.shared.clock import SystemClock
from tracker.shared.config import Settings, get_settings
from tracker.shared.constants.assessment import BATCH_DIRECTORY, RESULT_DIRECTORY

#: Panel the root help groups these commands under.
HELP_PANEL: Final[str] = "assessment"

ai_app = typer.Typer(
    help="Prepare people for assessment, then save what came back.",
    no_args_is_help=True,
)

BatchDirectoryOption = Annotated[
    Path,
    typer.Option("--batches", help="Directory the batch files live in."),
]

ResultDirectoryOption = Annotated[
    Path,
    typer.Option("--results", help="Directory the verdict files live in."),
]

LimitOption = Annotated[
    int | None,
    typer.Option("--limit", min=1, help="Export at most this many people.", show_default=False),
]


def register(cli: typer.Typer) -> None:
    """Attach the assessment commands to the root application.

    Args:
        cli: The root Typer application.
    """
    cli.add_typer(ai_app, name="ai", rich_help_panel=HELP_PANEL)


@ai_app.command("export")
def export(
    limit: LimitOption = None,
    batches: BatchDirectoryOption = BATCH_DIRECTORY,
) -> None:
    """Write one file per group of people who still need a verdict."""
    settings = get_settings()
    clock = SystemClock(settings.owner_zone)
    exporter = AssessmentExporter(_repositories(settings), clock, batches)
    result = exporter.export(limit=limit)
    for path in result.batch_paths:
        typer.echo(str(path))
    typer.echo(f"{result.people} people in {len(result.batch_paths)} batch files")


@ai_app.command("import")
def import_results(
    results: ResultDirectoryOption = RESULT_DIRECTORY,
    batches: BatchDirectoryOption = BATCH_DIRECTORY,
) -> None:
    """Check the verdict files and save the ones that pass."""
    settings = get_settings()
    repositories = _repositories(settings)
    importer = AssessmentImporter(
        repositories,
        SystemClock(settings.owner_zone),
        settings.owner_weekend_days,
        batches,
        results,
        wording=_wording(repositories),
    )
    outcome = importer.import_all()
    for rejected in outcome.rejected:
        typer.echo(f"rejected {rejected.path.name}: {rejected.reason}")
    typer.echo(
        f"{outcome.assessed} people assessed, "
        f"{outcome.sent_to_review} sent to review, "
        f"{outcome.marked_noise} marked noise, "
        f"{len(outcome.rejected)} rejected files"
    )


@ai_app.command("status")
def status(
    results: ResultDirectoryOption = RESULT_DIRECTORY,
    batches: BatchDirectoryOption = BATCH_DIRECTORY,
) -> None:
    """Show what is waiting: people to judge, files to import, questions to answer."""
    settings = get_settings()
    repositories = _repositories(settings)
    clock = SystemClock(settings.owner_zone)
    pending = AssessmentExporter(repositories, clock, batches).pending_people()
    waiting_files = AssessmentImporter(
        repositories,
        clock,
        settings.owner_weekend_days,
        batches,
        results,
        wording=_wording(repositories),
    ).result_files()
    questions = read_every(repositories.review_items.list_unanswered)
    typer.echo(f"people needing assessment: {pending}")
    typer.echo(f"verdict files waiting to be imported: {len(waiting_files)}")
    typer.echo(f"questions waiting for your answer: {len(questions)}")


@ai_app.command("clean")
def clean() -> None:
    """Remove every exchanged file, including batches that were never answered."""
    result = clean_work_directory()
    typer.echo(f"{result.removed_files} files removed from the work directory")


def _repositories(settings: Settings) -> Repositories:
    """Build the repositories on a fresh database client."""
    return build_repositories(create_database_client(settings))


def _wording(repositories: Repositories) -> Wording:
    """The owner's profile wording: their file, else their chosen preset."""
    chosen = repositories.app_settings.read_preset()
    return load_profile(chosen_preset=chosen).profile.wording
