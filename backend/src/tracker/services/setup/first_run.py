"""The first daily run on GitHub, started by the set-up once the settings are saved.

With the GitHub CLI signed in, the GitHub step makes sure the workflow may run
and starts it in ``daily`` mode after one yes, so the first summary e-mail is
on its way before the set-up ends. When GitHub refuses, or without the CLI,
the step names the page where 'Run workflow' is pressed by hand instead. The
wizard's closing words read how it went from :class:`FirstRun`.

The run does nothing without the Claude key on GitHub, and sends no e-mail
without a mailbox that has an app password, so the step starts it only when
the key is there, and offers it with a default of no when no e-mail can come.
An express run starts it without asking, since it fills the dashboard either way.

Once started, the run is followed for up to two minutes. It is found by its
title and by when it was made, so a refresh or an on-time start that GitHub
began a few seconds later is never followed in its place. A key Claude refuses
stops it within the first minute, and the workflow then leaves one line saying
why (titled ``CLAUDE_STOPPED_TITLE``), which is read back and said here, so a
problem is not left for the owner to find the next morning. A run still going
after that is left to finish on its own.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from tracker.infrastructure.github_cli import WorkflowRun
from tracker.services.setup.context import SetupContext
from tracker.services.setup.models import StepName
from tracker.shared.constants.claude import CLAUDE_STOPPED_TITLE
from tracker.shared.constants.github import (
    CLAUDE_TOKEN_SECRET,
    DAILY_RUN_TITLE,
    FIRST_RUN_CLOCK_SKEW_SECONDS,
    FIRST_RUN_POLL_SECONDS,
    FIRST_RUN_WATCH_SECONDS,
    FIRST_SUMMARY_MINUTES,
    WORKFLOW_DISPLAY_NAME,
    WORKFLOW_PAGE,
    WorkflowMode,
)
from tracker.shared.errors import (
    SourceUnavailableError,
    WorkflowNotEnabledError,
    WorkflowNotStartedError,
)
from tracker.shared.logging import get_logger

_log = get_logger(__name__)

#: Where the workflow's page is when the repository's name is not known.
_WORKFLOW_PAGE_BY_HAND: Final[str] = f"your copy on github.com > Actions > {WORKFLOW_DISPLAY_NAME}"


@dataclass(frozen=True, slots=True)
class FirstRun:
    """How the first daily run was left when the GitHub step ended.

    Attributes:
        started: Whether the set-up started it on GitHub.
        page: The workflow's page: where to watch the run, or to start it by hand.
        summary_by_email: Whether GitHub can send the morning e-mail, which
            needs a mailbox with an app password.
        needs_claude_key: Whether the run was held back because GitHub does not
            have the Claude key it needs.
        stopped: Whether the run was seen to stop with a problem while the
            set-up followed it.
    """

    started: bool
    page: str
    summary_by_email: bool = True
    needs_claude_key: bool = False
    stopped: bool = False


def workflow_page(repository: str | None) -> str:
    """Name the workflow's page on GitHub.

    Args:
        repository: The copy as ``owner/name``, or ``None`` when it is not known.

    Returns:
        The page's address, or how to find it when the copy's name is unknown.
    """
    if repository is None:
        return _WORKFLOW_PAGE_BY_HAND
    return WORKFLOW_PAGE.format(repository=repository)


async def start_first_run(
    ctx: SetupContext,
    repository: str,
    *,
    summary_by_email: bool,
    claude_key_on_github: bool | None,
) -> FirstRun:
    """Offer to start the first daily run with the GitHub CLI, start it after a yes, and follow it.

    GitHub refusing is not the end of the set-up: the settings are saved, and
    pressing the button by hand is all that is left, so the refusal is said
    in one line with the page to press it on.

    Args:
        ctx: The set-up's context.
        repository: The copy, as ``owner/name``.
        summary_by_email: Whether GitHub can send the morning e-mail; when it
            cannot, the offer defaults to no and says so.
        claude_key_on_github: Whether GitHub holds the Claude key; ``None`` when
            that could not be checked. Without it the run would do nothing, so
            it is not offered.

    Returns:
        How the first run was left.
    """
    io = ctx.io
    page = workflow_page(repository)
    if claude_key_on_github is not True:
        _say_key_needed(ctx, checked=claude_key_on_github is False)
        return FirstRun(
            started=False, page=page, summary_by_email=summary_by_email, needs_claude_key=True
        )
    question = (
        "Start the first daily run on GitHub now?"
        if summary_by_email
        else "Start the first daily run on GitHub now? It fills the dashboard, but no e-mail comes"
    )
    if not ctx.session.express and not io.confirm(question, default=summary_by_email):
        say_first_run_by_hand(ctx, repository)
        return FirstRun(started=False, page=page, summary_by_email=summary_by_email)
    earlier = _runs_before(ctx, repository)
    started_at = ctx.gateways.clock.now()
    try:
        ctx.gateways.github.enable_workflow(repository)
        ctx.gateways.github.start_workflow(repository, WorkflowMode.DAILY)
    except (WorkflowNotEnabledError, WorkflowNotStartedError) as error:
        _log.warning("first_run_not_started", code=error.code)
        io.say(f"{error.message}.")
        return FirstRun(started=False, page=page, summary_by_email=summary_by_email)
    io.say("The first run has started.")
    run = await _follow(ctx, repository, earlier, started_at) if earlier is not None else None
    if run is not None and run.finished and not run.succeeded:
        _say_stopped(ctx, repository, run)
        return FirstRun(
            started=True, page=run.url or page, summary_by_email=summary_by_email, stopped=True
        )
    _say_going(ctx, page, finished=run is not None and run.succeeded, by_email=summary_by_email)
    return FirstRun(started=True, page=page, summary_by_email=summary_by_email)


def _runs_before(ctx: SetupContext, repository: str) -> frozenset[int] | None:
    """The newest runs before the first one, so the new run can be told apart.

    Returns:
        Their numbers, none when there is none; ``None`` when GitHub could not
        say, and the new run then cannot be followed.
    """
    try:
        runs = ctx.gateways.github.recent_runs(repository)
    except SourceUnavailableError:
        return None
    return frozenset(run.id for run in runs)


def _the_set_ups_run(
    runs: Iterable[WorkflowRun], earlier: frozenset[int], started_at: datetime
) -> WorkflowRun | None:
    """Pick the daily run the set-up started out of the newest runs.

    Args:
        runs: The newest runs started with 'Run workflow'.
        earlier: The runs that were there before it.
        started_at: When the set-up asked GitHub to start it, by this computer's clock.

    Returns:
        The run, or ``None`` when GitHub does not show it yet.
    """
    since = started_at - timedelta(seconds=FIRST_RUN_CLOCK_SKEW_SECONDS)
    daily_runs_since = [
        run
        for run in runs
        if run.id not in earlier
        and run.title == DAILY_RUN_TITLE
        and run.created_at is not None
        and run.created_at >= since
    ]
    # GitHub numbers runs in the order it makes them, so a daily run started a
    # moment later (the on-time start) has a higher number than the set-up's.
    return min(daily_runs_since, key=lambda run: run.id, default=None)


async def _follow(
    ctx: SetupContext, repository: str, earlier: frozenset[int], started_at: datetime
) -> WorkflowRun | None:
    """Follow the run just started for a short while, until it ends.

    Args:
        ctx: The set-up's context.
        repository: The copy, as ``owner/name``.
        earlier: The runs that were there before it.
        started_at: When the set-up asked GitHub to start it.

    Returns:
        The run as last seen, or ``None`` when GitHub did not show it.
    """
    minutes = FIRST_RUN_WATCH_SECONDS // 60
    ctx.io.say(f"Watching it for up to {minutes} minutes, to catch a problem early...")
    github = ctx.gateways.github
    run: WorkflowRun | None = None
    for _ in range(FIRST_RUN_WATCH_SECONDS // FIRST_RUN_POLL_SECONDS):
        await ctx.gateways.sleep(FIRST_RUN_POLL_SECONDS)
        try:
            run = (
                github.workflow_run(repository, run.id)
                if run
                else _the_set_ups_run(github.recent_runs(repository), earlier, started_at)
            )
        except SourceUnavailableError:
            return run
        if run is not None and run.finished:
            return run
    return run


def _say_stopped(ctx: SetupContext, repository: str, run: WorkflowRun) -> None:
    """Say that the first run stopped, why, and what to do."""
    _log.warning("first_run_stopped", conclusion=run.conclusion)
    try:
        notes = ctx.gateways.github.run_notes(repository, run.id, CLAUDE_STOPPED_TITLE)
    except SourceUnavailableError:
        notes = ()
    io = ctx.io
    if notes:
        io.say(f"The first run stopped with a problem. {notes[0]}")
        return
    io.say("The first run stopped with a problem. To see why, open this page and click the")
    io.say(f"step marked with a red cross: {run.url or workflow_page(repository)}")


def _say_going(ctx: SetupContext, page: str, *, finished: bool, by_email: bool) -> None:
    """Say that the first run is going, or finished well, and what comes of it."""
    io = ctx.io
    if finished:
        io.say("The first run has finished.")
        io.say("The summary e-mail is on its way." if by_email else "Your dashboard is filled in.")
        return
    if by_email:
        io.say(f"It is running; the summary e-mail comes in about {FIRST_SUMMARY_MINUTES} minutes.")
    else:
        io.say(f"It is running; the dashboard fills in about {FIRST_SUMMARY_MINUTES} minutes.")
        io.say("No summary e-mail will come: GitHub can only send it from a mailbox with an")
        io.say("app password.")
    io.say(f"You can watch it here, or close this window: {page}")


def _say_key_needed(ctx: SetupContext, *, checked: bool) -> None:
    """Say why the first run is not started, and what to do about the missing key."""
    io = ctx.io
    if checked:
        io.say(f"The first run is not started: GitHub does not have {CLAUDE_TOKEN_SECRET} yet,")
        io.say("so the run would do nothing.")
    else:
        io.say("The first run is not started: GitHub could not be asked whether it has")
        io.say(f"{CLAUDE_TOKEN_SECRET}, and without it the run would do nothing.")
    io.say("Make the key in a new terminal window with 'claude setup-token', then run")
    io.say(
        f"'uv run tracker setup {StepName.GITHUB}' and paste it. The first run starts after that."
    )


def say_first_run_by_hand(ctx: SetupContext, repository: str | None) -> None:
    """Say how to start the first run on github.com.

    Args:
        ctx: The set-up's context.
        repository: The copy as ``owner/name``, or ``None`` when it is not known.
    """
    ctx.io.say(f"To start the first run yourself: open {workflow_page(repository)},")
    ctx.io.say(
        f"click 'Run workflow', keep mode {WorkflowMode.DAILY}, and click the green "
        "'Run workflow' button."
    )
