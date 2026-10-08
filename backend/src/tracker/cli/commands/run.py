"""The commands the daily recipe is made of.

``tracker run start`` opens the run, ``tracker run step`` records what each part
of it did, ``tracker summary build`` writes the morning summary to a file and
``tracker run finish`` closes the run with the status its steps add up to.
``tracker summary send`` sends that file from the owner's own mailbox, when
the summary goes by SMTP rather than through the Gmail connector.

Each handler does the same three things and nothing else: build the service,
call one method, print the result. Nothing here chooses the recipient or the
words: both are the ones in the file, checked against the settings.

Two options fold the small commands around a run into its first and last step,
because every step of the recipe costs the session the same few seconds
whatever it does. ``run start --prepare`` goes on to the health check and
``profile apply``; ``run finish --clean`` goes on to ``ai clean`` once the run
is closed. Each folded command prints what it prints on its own.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Final
from uuid import UUID

import typer

from tracker.cli.commands._parts import attempt
from tracker.cli.commands.ai import clean as clean_work_files
from tracker.cli.commands.profile import apply as apply_profile
from tracker.cli.commands.system import healthcheck
from tracker.domain.enums import RunStep, RunTrigger
from tracker.infrastructure.database import create_database_client
from tracker.infrastructure.secret_store import SecretStore
from tracker.infrastructure.smtp import SmtpMailer
from tracker.repositories import Repositories, build_repositories
from tracker.schemas.summary import SummaryEmail
from tracker.services.collection.mailboxes import imap_account, saved_app_password
from tracker.services.collection.models import NOT_CONFIGURED_LINE
from tracker.services.runs.owner_settings import publish_owner_settings
from tracker.services.runs.run_recorder import (
    RunRecorder,
    StepOutcome,
    StepResult,
    unconfigured_steps,
)
from tracker.services.summary.builder import SummaryBuilder
from tracker.services.summary.once_a_day import OnceADay, skipped_line
from tracker.services.summary.send_once import SendOnce
from tracker.services.summary.sender import SkippedSummary, SummarySender, smtp_account
from tracker.shared.clock import SystemClock
from tracker.shared.config import Settings, get_settings, in_project
from tracker.shared.constants.summary import SUMMARY_FILE
from tracker.shared.errors import DatabaseUnavailableError, TrackerError

#: Panel the root help groups these commands under.
HELP_PANEL: Final[str] = "daily run"

#: What ``run finish --clean`` prints instead of cleaning when the run stays open.
WORK_FILES_KEPT: Final[str] = "work files kept · the run could not be closed"

run_app = typer.Typer(
    help="Record what today's run did, step by step.",
    no_args_is_help=True,
)

summary_app = typer.Typer(
    help="Build the morning summary from what is in the database.",
    no_args_is_help=True,
)

TriggerOption = Annotated[
    RunTrigger,
    typer.Option("--trigger", help="What started this run."),
]

PrepareOption = Annotated[
    bool,
    typer.Option(
        "--prepare",
        help="Also run the health check and 'profile apply', and say whether the run can go on.",
    ),
]

CleanOption = Annotated[
    bool,
    typer.Option("--clean", help="Also remove the exchanged work files, as 'ai clean' does."),
]

StepOption = Annotated[
    RunStep,
    typer.Option("--step", help="Which part of the run this was.", show_default=False),
]

ResultOption = Annotated[
    StepResult,
    typer.Option("--result", help="Whether that part finished.", show_default=False),
]

FoundOption = Annotated[
    int | None,
    typer.Option("--found", min=0, help="How many items the step looked at.", show_default=False),
]

NewOption = Annotated[
    int | None,
    typer.Option("--new", min=0, help="How many of them were new.", show_default=False),
]

ErrorCodeOption = Annotated[
    str | None,
    typer.Option("--error-code", help="Stable code behind a failure.", show_default=False),
]

ErrorDetailOption = Annotated[
    str | None,
    typer.Option(
        "--error-detail",
        help="Short technical note for the run page. Never message text.",
        show_default=False,
    ),
]

RunOption = Annotated[
    UUID | None,
    typer.Option("--run", help="Act on this run instead of the one still open."),
]

RefreshRunOption = Annotated[
    bool,
    typer.Option("--refresh", help="Act on the refresh that is open, not the daily run."),
]

ReportedRunOption = Annotated[
    UUID | None,
    typer.Option("--run", help="Report on this run instead of the most recent one."),
]

OutOption = Annotated[
    Path,
    typer.Option(
        "--out",
        help=f"Where to write the summary (default: {in_project(SUMMARY_FILE)}).",
        show_default=False,
    ),
]

FileOption = Annotated[
    Path,
    typer.Option(
        "--file",
        help=f"The summary file 'summary build' wrote (default: {in_project(SUMMARY_FILE)}).",
        show_default=False,
    ),
]

SendAgainOption = Annotated[
    bool,
    typer.Option(
        "--send-again",
        help="Build or send it even though another daily run already sent today's summary.",
    ),
]


def register(cli: typer.Typer) -> None:
    """Attach the daily-run commands to the root application.

    Args:
        cli: The root Typer application.
    """
    cli.add_typer(run_app, name="run", rich_help_panel=HELP_PANEL)
    cli.add_typer(summary_app, name="summary", rich_help_panel=HELP_PANEL)


@run_app.command("start")
def start_run(trigger: TriggerOption = RunTrigger.CLOUD, prepare: PrepareOption = False) -> None:
    """Open today's run, print its identifier, and pass the owner's time zone on."""
    settings = get_settings()
    repositories = _repositories(settings)
    run = _recorder(settings, repositories).start(trigger)
    typer.echo(f"run {run.id} started · trigger {trigger.value}")
    typer.echo(_time_zone_line(repositories, settings))
    if prepare:
        typer.echo(f"ready: {'yes' if _prepare() else 'no'}")


@run_app.command("step")
def record_step(
    step: StepOption,
    result: ResultOption,
    found: FoundOption = None,
    new: NewOption = None,
    error_code: ErrorCodeOption = None,
    error_detail: ErrorDetailOption = None,
    run: RunOption = None,
    refresh: RefreshRunOption = False,
) -> None:
    """Record what one part of the run did."""
    recorder = _recorder(get_settings())
    target = recorder.resolve(run, refresh=refresh)
    outcome = StepOutcome(
        step=step,
        result=result,
        items_found=found,
        items_new=new,
        error_code=error_code,
        error_detail=error_detail,
    )
    recorded = recorder.record_step(target.id, outcome)
    if recorded is None:
        typer.echo(f"{step.value}: {NOT_CONFIGURED_LINE} · nothing recorded")
        return
    typer.echo(f"{recorded.step.value}: {recorded.status.value}")


@run_app.command("finish")
def finish_run(
    run: RunOption = None, clean: CleanOption = False, refresh: RefreshRunOption = False
) -> None:
    """Close the run with the status its steps add up to."""
    try:
        _close(run, refresh=refresh)
    except TrackerError:
        # A run that could not be closed may also have been unable to take an
        # earlier step, so verdict files may still wait to be imported. They are
        # kept for 'tracker ai import'; the next closed run cleans up.
        if clean:
            typer.echo(WORK_FILES_KEPT)
        raise
    if clean:
        attempt("ai clean", clean_work_files)


@summary_app.command("build")
def build_summary(
    out: OutOption = SUMMARY_FILE,
    run: ReportedRunOption = None,
    send_again: SendAgainOption = False,
) -> None:
    """Write the morning summary to a file, ready for the session to send."""
    settings = get_settings()
    repositories = _repositories(settings)
    clock = SystemClock(settings.owner_zone)
    builder = SummaryBuilder(repositories, settings, clock)
    target = builder.run_to_report(run)
    once = SendOnce(_recorder(settings, repositories), out)
    once.refuse_a_new_summary(target)
    today = OnceADay(repositories, clock)
    earlier = once.skip_when_sent_today(target, today, send_again=send_again)
    if earlier is not None:
        typer.echo(skipped_line(earlier))
        return
    email = builder.build_for(target)
    _write(email, out)
    typer.echo(str(out))
    typer.echo(f"to: {email.recipient}")
    typer.echo(f"subject: {email.subject}")
    typer.echo(_counts(email))
    typer.echo(f"delivery: {settings.summary_route.value}")


@summary_app.command("send")
def send_summary(
    file: FileOption = SUMMARY_FILE, run: RunOption = None, send_again: SendAgainOption = False
) -> None:
    """Send the summary file from your own mailbox, and record that it went."""
    settings = get_settings()
    repositories = _repositories(settings)

    def mailer() -> SmtpMailer:
        store = SecretStore(repositories.app_secrets, settings.token_encryption_key, SystemClock())
        password = saved_app_password(store, imap_account(settings))
        return SmtpMailer(smtp_account(settings), password)

    once_a_day = OnceADay(repositories, SystemClock(settings.owner_zone))
    sender = SummarySender(settings, mailer, _recorder(settings, repositories), once_a_day)
    sent = sender.send(file, run, send_again=send_again)
    if isinstance(sent, SkippedSummary):
        typer.echo(skipped_line(sent.earlier))
        return
    typer.echo(f"summary sent · to: {sent.summary.recipient}")
    if sent.step_error_code is not None:
        typer.echo(f"step not recorded · code={sent.step_error_code}")


def _time_zone_line(repositories: Repositories, settings: Settings) -> str:
    """Copy the owner's time zone into the database and say how that went."""
    try:
        zone = publish_owner_settings(repositories, settings)
    except DatabaseUnavailableError:
        # The run itself is open and every later step still works; only the
        # dashboard keeps measuring "today" in the zone it had before.
        return "time zone not saved · the dashboard keeps its previous time zone"
    return f"time zone: {zone}"


def _prepare() -> bool:
    """Check the plumbing, then put the owner's profile into effect.

    Returns:
        Whether the health check passed, which is what decides if the run goes
        on. The profile is not attempted after a failed check. A profile that
        could not be applied does not stop the run: the guide and the
        categories from the last successful apply are still in place.
    """
    if not attempt("healthcheck", healthcheck):
        return False
    attempt("profile apply", apply_profile)
    return True


def _close(run: UUID | None, *, refresh: bool) -> None:
    """Close the named run, or the open one of its kind, and print its status."""
    recorder = _recorder(get_settings())
    target = recorder.resolve(run, refresh=refresh)
    finished = recorder.finish(target.id)
    typer.echo(f"run {finished.id} finished · status {finished.status.value}")


def _write(email: SummaryEmail, out: Path) -> None:
    """Write the summary as JSON, creating the folder if it is missing.

    Args:
        email: The summary to store.
        out: Where to write it.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(email.model_dump_json(indent=2) + "\n", encoding="utf-8")


def _counts(email: SummaryEmail) -> str:
    """Render one line of numbers for the command line."""
    content = email.content
    return (
        f"status: {content.run_status.value} · "
        f"{content.do_today_total} for you · "
        f"{content.overdue_total} overdue · "
        f"{content.chase_total} to chase · "
        f"{content.replied_total} replied · "
        f"{content.open_questions} questions · "
        f"{len(content.problems)} problems"
    )


def _recorder(settings: Settings, repositories: Repositories | None = None) -> RunRecorder:
    """Build the run recorder, leaving out the steps of sources not set up."""
    return RunRecorder(
        repositories or _repositories(settings),
        SystemClock(settings.owner_zone),
        unconfigured_steps(settings),
    )


def _repositories(settings: Settings) -> Repositories:
    """Build the repositories on a fresh database client."""
    return build_repositories(create_database_client(settings))
