"""The commands around the assessment.

``tracker ai export`` writes the questions, a Claude Code session answers them in
files, and ``tracker ai import`` checks those answers, saves them and removes
the files it applied. ``tracker ai clean`` removes whatever is left. No command
here calls an AI service: the judging happens inside the session, on the owner's
Claude subscription.

With ``--record``, ``export`` and ``import`` also record the assessment as its
step of the run, which the daily recipe used to do with a command of its own.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Final
from uuid import UUID

import typer

from tracker.domain.models import RunLog
from tracker.domain.profile import Wording
from tracker.infrastructure.database import create_database_client
from tracker.repositories import Repositories, build_repositories
from tracker.services.assessment.exporter import AssessmentExporter
from tracker.services.assessment.importer import AssessmentImporter
from tracker.services.assessment.run_step import record_assessment
from tracker.services.assessment.work_files import clean_work_directory
from tracker.services.identity.matcher import read_every
from tracker.services.profile.loader import load_profile
from tracker.services.runs.run_recorder import RunRecorder, unconfigured_steps
from tracker.shared.clock import Clock, SystemClock
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

RecordOption = Annotated[
    bool,
    typer.Option("--record", help="Record the assessment as its step of the run."),
]

RunOption = Annotated[
    UUID | None,
    typer.Option("--run", help="With --record: record into this run, not the one still open."),
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
    results: ResultDirectoryOption = RESULT_DIRECTORY,
    record: RecordOption = False,
    run: RunOption = None,
) -> None:
    """Write one file per group of people who still need a verdict."""
    settings = get_settings()
    repositories = _repositories(settings)
    clock = SystemClock(settings.owner_zone)
    recorder = _recorder(settings, repositories, clock)
    target = _run_to_record(recorder, run, record=record)
    result = AssessmentExporter(repositories, clock, batches).export(limit=limit)
    if result.batch_paths:
        # The verdicts are written by a helper that can only read and write
        # files, so the directory they go in has to be there before it starts.
        results.mkdir(parents=True, exist_ok=True)
    for path in result.batch_paths:
        typer.echo(str(path))
    typer.echo(f"{result.people} people in {len(result.batch_paths)} batch files")
    if target is not None and not result.people:
        # Nothing to judge means no import will follow to record the step.
        _record(recorder, target, assessed=0, sent_to_review=0)


@ai_app.command("import")
def import_results(
    results: ResultDirectoryOption = RESULT_DIRECTORY,
    batches: BatchDirectoryOption = BATCH_DIRECTORY,
    record: RecordOption = False,
    run: RunOption = None,
) -> None:
    """Check the verdict files and save the ones that pass."""
    settings = get_settings()
    repositories = _repositories(settings)
    clock = SystemClock(settings.owner_zone)
    recorder = _recorder(settings, repositories, clock)
    target = _run_to_record(recorder, run, record=record)
    importer = AssessmentImporter(
        repositories,
        clock,
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
    if target is not None:
        _record(recorder, target, assessed=outcome.assessed, sent_to_review=outcome.sent_to_review)


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


def _recorder(settings: Settings, repositories: Repositories, clock: Clock) -> RunRecorder:
    """Build the run recorder, leaving out the steps of sources not set up."""
    return RunRecorder(repositories, clock, unconfigured_steps(settings))


def _run_to_record(recorder: RunRecorder, run: UUID | None, *, record: bool) -> RunLog | None:
    """Find the run the step is recorded into, when recording was asked for.

    It is looked up before any work is done, so a run that does not exist is
    reported straight away rather than after the export or the import.
    """
    return recorder.resolve(run) if record else None


def _record(recorder: RunRecorder, target: RunLog, *, assessed: int, sent_to_review: int) -> None:
    """Record the assessment step and say so."""
    record_assessment(recorder, target.id, assessed=assessed, sent_to_review=sent_to_review)
    typer.echo("step recorded")


def _wording(repositories: Repositories) -> Wording:
    """The owner's profile wording: their file, else their chosen preset."""
    chosen = repositories.app_settings.read_preset()
    return load_profile(chosen_preset=chosen).profile.wording
