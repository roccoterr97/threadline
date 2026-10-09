"""The first daily run on GitHub, started by the set-up once the settings are saved.

With the GitHub CLI signed in, the GitHub step makes sure the workflow may run
and starts it in ``daily`` mode after one yes, so the first summary e-mail is
on its way before the set-up ends. When GitHub refuses, or without the CLI,
the step names the page where 'Run workflow' is pressed by hand instead. The
wizard's closing words read how it went from :class:`FirstRun`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from tracker.services.setup.context import SetupContext
from tracker.shared.constants.github import (
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
    """

    started: bool
    page: str


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


def start_first_run(ctx: SetupContext, repository: str) -> FirstRun:
    """Offer to start the first daily run with the GitHub CLI, and do so after a yes.

    GitHub refusing is not the end of the set-up: the settings are saved, and
    pressing the button by hand is all that is left, so the refusal is said
    in one line with the page to press it on.

    Args:
        ctx: The set-up's context.
        repository: The copy, as ``owner/name``.

    Returns:
        How the first run was left.
    """
    io = ctx.io
    page = workflow_page(repository)
    if not io.confirm("Start the first daily run on GitHub now?", default=True):
        say_first_run_by_hand(ctx, repository)
        return FirstRun(started=False, page=page)
    try:
        ctx.gateways.github.enable_workflow(repository)
        ctx.gateways.github.start_workflow(repository, WorkflowMode.DAILY)
    except (WorkflowNotEnabledError, WorkflowNotStartedError) as error:
        _log.warning("first_run_not_started", code=error.code)
        io.say(f"{error.message}.")
        return FirstRun(started=False, page=page)
    io.say(f"The first run has started. You can watch it here, or close this window: {page}")
    io.say(f"The summary e-mail arrives in about {FIRST_SUMMARY_MINUTES} minutes.")
    return FirstRun(started=True, page=page)


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
