"""The first daily run on GitHub, started by the set-up once the settings are saved.

With the GitHub CLI signed in, the GitHub step makes sure the workflow may run
and starts it in ``daily`` mode after one yes, so the first summary e-mail is
on its way before the set-up ends. When GitHub refuses, or without the CLI,
the step names the page where 'Run workflow' is pressed by hand instead. The
wizard's closing words read how it went from :class:`FirstRun`.

The run does nothing without the Claude key on GitHub, and sends no e-mail
without a mailbox that has an app password, so the step starts it only when
the key is there, and offers it with a default of no when no e-mail can come.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from tracker.services.setup.context import SetupContext
from tracker.services.setup.models import StepName
from tracker.shared.constants.github import (
    CLAUDE_TOKEN_SECRET,
    FIRST_SUMMARY_MINUTES,
    WORKFLOW_DISPLAY_NAME,
    WORKFLOW_PAGE,
    WorkflowMode,
)
from tracker.shared.errors import WorkflowNotEnabledError, WorkflowNotStartedError
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
    """

    started: bool
    page: str
    summary_by_email: bool = True
    needs_claude_key: bool = False


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


def start_first_run(
    ctx: SetupContext,
    repository: str,
    *,
    summary_by_email: bool,
    claude_key_on_github: bool | None,
) -> FirstRun:
    """Offer to start the first daily run with the GitHub CLI, and do so after a yes.

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
    if not io.confirm(question, default=summary_by_email):
        say_first_run_by_hand(ctx, repository)
        return FirstRun(started=False, page=page, summary_by_email=summary_by_email)
    try:
        ctx.gateways.github.enable_workflow(repository)
        ctx.gateways.github.start_workflow(repository, WorkflowMode.DAILY)
    except (WorkflowNotEnabledError, WorkflowNotStartedError) as error:
        _log.warning("first_run_not_started", code=error.code)
        io.say(f"{error.message}.")
        return FirstRun(started=False, page=page, summary_by_email=summary_by_email)
    io.say(f"The first run has started. You can watch it here, or close this window: {page}")
    if summary_by_email:
        io.say(f"The summary e-mail arrives in about {FIRST_SUMMARY_MINUTES} minutes.")
    else:
        io.say(f"The dashboard fills in about {FIRST_SUMMARY_MINUTES} minutes. No summary e-mail")
        io.say("will come: GitHub can only send it from a mailbox with an app password.")
    return FirstRun(started=True, page=page, summary_by_email=summary_by_email)


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
