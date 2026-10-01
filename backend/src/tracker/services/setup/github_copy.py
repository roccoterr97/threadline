"""The owner's private copy on GitHub, which the daily run needs before anything else.

GitHub runs Threadline from the owner's own copy of the project, and its
settings are saved into that copy. So before the GitHub step saves anything it
makes sure this folder is linked to such a copy, and offers to create one with
the GitHub CLI after an explicit yes. Without the CLI it says how to make one on
the website, and stops.
"""

from __future__ import annotations

import re
from typing import Final

from tracker.services.setup import values
from tracker.services.setup.context import SetupContext
from tracker.services.setup.models import StepName
from tracker.shared.constants.github import DEFAULT_COPY_NAME, TEMPLATE_REMOTE
from tracker.shared.errors import ValidationFailedError

#: ``owner/name`` in a GitHub link, over https or ssh, with or without ``.git``.
_GITHUB_ORIGIN: Final[re.Pattern[str]] = re.compile(
    r"github\.com[:/]([A-Za-z0-9-]+)/([A-Za-z0-9._-]+?)(?:\.git)?/?$"
)


def find_or_create_copy(ctx: SetupContext) -> str | None:
    """Name the owner's copy on GitHub, creating it first when there is none.

    Args:
        ctx: The set-up's context.

    Returns:
        The copy as ``owner/name``, or ``None`` when this folder is linked to
        GitHub but the GitHub CLI is not there to read the copy's name.

    Raises:
        ValidationFailedError: If there is no copy and none was created.
        SourceUnavailableError: If the GitHub CLI could not create it.
    """
    origin = ctx.gateways.git.origin_url()
    ready = ctx.gateways.github.ready()
    if origin is not None and not ready:
        return None
    repository = ctx.gateways.github.repository() if origin is not None else None
    if repository is not None:
        return repository
    ctx.io.say("GitHub can only run Threadline from your own private copy of this project.")
    ctx.io.say("This folder is not linked to a copy of yours on GitHub yet, so that comes first.")
    if ready and ctx.io.confirm(
        "Create your private copy now with the GitHub CLI, and upload this folder to it?",
        default=False,
    ):
        return _create(ctx, has_origin=origin is not None)
    _explain_by_hand(ctx, gh_installed=ready)
    message = (
        "there is no private copy on GitHub yet - make it, then run "
        f"'uv run tracker setup {StepName.GITHUB}' again"
    )
    raise ValidationFailedError(message)


def repository_from_origin(origin: str | None) -> str | None:
    """Read ``owner/name`` from where ``origin`` points, without the GitHub CLI.

    Args:
        origin: The link, such as ``https://github.com/you/threadline.git``.

    Returns:
        The copy as ``owner/name``, or ``None`` when it is not a GitHub link.
    """
    found = _GITHUB_ORIGIN.search(origin.strip()) if origin else None
    return f"{found.group(1)}/{found.group(2)}" if found else None


def has_copy(ctx: SetupContext) -> bool:
    """Tell whether this folder is linked to a copy on GitHub that git can push to."""
    return ctx.gateways.git.origin_url() is not None


def _create(ctx: SetupContext, *, has_origin: bool) -> str | None:
    """Create the private copy with the GitHub CLI and push this folder to it."""
    name = ctx.ask_until_valid(
        lambda: ctx.io.ask("Name for your copy", default=DEFAULT_COPY_NAME),
        values.repository_name,
    )
    if has_origin:
        ctx.gateways.git.rename_origin(TEMPLATE_REMOTE)
        ctx.io.say(f"This folder's old link to GitHub is kept under the name '{TEMPLATE_REMOTE}'.")
    ctx.gateways.github.create_private_copy(name)
    repository = ctx.gateways.github.repository()
    ctx.io.say(f"Created your private copy {repository or name} and uploaded this folder to it.")
    return repository


def _explain_by_hand(ctx: SetupContext, *, gh_installed: bool) -> None:
    """Say how to make the copy on github.com."""
    io = ctx.io
    io.say("To make it on github.com:")
    io.say("  1. Open this project's page and click 'Use this template' >")
    io.say("     'Create a new repository'.")
    io.say("  2. Give it a name, choose Private, and click 'Create repository'.")
    io.say("  3. Download your copy as in part 1 of docs/setup-your-accounts.md, move the file")
    io.say("     backend/.env from this folder into the new copy's backend folder, and run")
    io.say(f"     'uv run tracker setup {StepName.GITHUB}' there.")
    if not gh_installed:
        io.say("Or install the GitHub CLI ('brew install gh'), sign in with 'gh auth login',")
        io.say("and run this step again: it can then create the copy for you.")
