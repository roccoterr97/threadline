"""The commands around the assessment.

``tracker ai export`` writes the questions, a Claude Code session answers them in
files, and ``tracker ai import`` checks those answers, saves them and removes
the files it applied. ``tracker ai clean`` removes whatever is left. No command
here calls an AI service: the judging happens inside the session, on the owner's
Claude subscription.

With ``--record``, ``export`` and ``import`` also record the assessment as its
step of the run, which the daily recipe used to do with a command of its own.
``import`` saves the verdicts first and only then looks for the run, so a run
that can no longer be recorded into costs the step, never the verdicts.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Final
from uuid import UUID

import typer

from tracker.domain.models import RunLog
from tracker.domain.profile import Wording
from tracker.infrastructure.database import create_database_client
from tracker.repositories import Repositories, build_repositories
from tracker.services.assessment.exporter import AssessmentExporter
from tracker.services.assessment.importer import AssessmentImporter, ImportResult
from tracker.services.assessment.run_step import record_assessment
from tracker.services.assessment.work_files import clean_work_directory
from tracker.services.profile.loader import load_profile
from tracker.services.runs.run_recorder import RunRecorder, unconfigured_steps
from tracker.shared.clock import Clock, SystemClock
from tracker.shared.config import Settings, get_settings
from tracker.shared.constants.assessment import BATCH_DIRECTORY, RESULT_DIRECTORY
from tracker.shared.errors import TrackerError
from tracker.shared.logging import get_logger

#: Panel the root help groups these commands under.
HELP_PANEL: Final[str] = "assessment"

#: What an import with ``--record`` prints when it saved the verdicts but the
#: run could not take the step; the daily recipe reads it.
STEP_NOT_RECORDED: Final[str] = "verdicts saved, step not recorded"

_log = get_logger(__name__)

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

RefreshOption = Annotated[
    bool,
    typer.Option(
        "--refresh", help="With --record: record into the refresh that is open, not the daily run."
    ),
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
    refresh: RefreshOption = False,
) -> None:
    """Write one file per group of people who still need a verdict."""
    settings = get_settings()
    repositories = _repositories(settings)
    clock = SystemClock(settings.owner_zone)
    recorder = _recorder(settings, repositories, clock)
    target = recorder.resolve(run, refresh=refresh) if record else None
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
    refresh: RefreshOption = False,
) -> None:
    """Check the verdict files and save the ones that pass."""
    settings = get_settings()
    repositories = _repositories(settings)
    clock = SystemClock(settings.owner_zone)
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
    if record:
        recorder = _recorder(settings, repositories, clock)
        _record_import(lambda: recorder.resolve(run, refresh=refresh), recorder, outcome)


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
    questions = repositories.review_items.list_every_unanswered()
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


def _record(recorder: RunRecorder, target: RunLog, *, assessed: int, sent_to_review: int) -> None:
    """Record the assessment step and say so."""
    record_assessment(recorder, target.id, assessed=assessed, sent_to_review=sent_to_review)
    typer.echo("step recorded")


def _record_import(
    find_run: Callable[[], RunLog], recorder: RunRecorder, outcome: ImportResult
) -> None:
    """Record what the import saved, or say plainly that the run could not take it.

    The run is looked up only after the verdicts are saved: a run that can no
    longer be recorded into — closed by something else, or so old it counts as
    abandoned — must never cost the assessment itself, whose verdict files would
    otherwise be removed unimported at the end of the run.

    Args:
        find_run: Looks up the run to record into.
        recorder: Writes the run's steps.
        outcome: What the import saved.
    """
    try:
        target = find_run()
        _record(recorder, target, assessed=outcome.assessed, sent_to_review=outcome.sent_to_review)
    except TrackerError as error:
        _log.warning("assess_step_not_recorded", code=error.code, detail=error.message)
        # The reason is printed, not only logged: "no run is open" is what tells
        # the daily recipe to build and send no summary for this run.
        typer.echo(f"{STEP_NOT_RECORDED} · {error.message} · code={error.code}")


def _wording(repositories: Repositories) -> Wording:
    """The owner's profile wording: their file, else their chosen preset."""
    chosen = repositories.app_settings.read_preset()
    return load_profile(chosen_preset=chosen).profile.wording
