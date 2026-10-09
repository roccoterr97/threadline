"""The owner's private copy on GitHub, which the daily run needs before anything else.

GitHub runs Threadline from the owner's own copy of the project, and its
settings are saved into that copy. So before the GitHub step saves anything it
makes sure this folder is linked to such a copy, and offers to create one with
the GitHub CLI after an explicit yes. Without the CLI it says how to make one on
the website, and stops.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from tracker.services.setup import values
from tracker.services.setup.context import SetupContext
from tracker.services.setup.models import StepName
from tracker.shared.constants.github import DEFAULT_COPY_NAME, GITHUB_CLI_PAGE, TEMPLATE_REMOTE
from tracker.shared.errors import ValidationFailedError

#: ``owner/name`` in a GitHub link, over https or ssh, with or without ``.git``.
_GITHUB_ORIGIN: Final[re.Pattern[str]] = re.compile(
    r"github\.com[:/]([A-Za-z0-9-]+)/([A-Za-z0-9._-]+?)(?:\.git)?/?$"
)


@dataclass(frozen=True, slots=True)
class LinkedCopy:
    """The owner's copy on GitHub that this folder is linked to.

    Attributes:
        name: The copy, as ``owner/name``.
        confirmed: ``True`` when the GitHub CLI showed it is a private
            repository the owner administers; ``False`` when, without the CLI,
            only the link could be read.
    """

    name: str
    confirmed: bool


def linked_copy(ctx: SetupContext) -> LinkedCopy | None:
    """Name the owner's copy this folder is linked to, without creating one.

    With the GitHub CLI signed in, only a private repository the owner
    administers counts, as in the GitHub step — never the public template.
    Without it, the GitHub link is all that can be seen.

    Args:
        ctx: The set-up's context.

    Returns:
        The copy, or ``None`` when there is none to be seen.
    """
    origin = ctx.gateways.git.origin_url()
    if origin is None:
        return None
    if not ctx.gateways.github.ready():
        name = repository_from_origin(origin)
        return LinkedCopy(name, confirmed=False) if name else None
    linked = ctx.gateways.github.repository()
    if linked is None or not linked.is_own_private_copy:
        return None
    return LinkedCopy(linked.name, confirmed=True)


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
    linked = ctx.gateways.github.repository() if origin is not None else None
    if linked is not None and linked.is_own_private_copy:
        return linked.name
    ctx.io.say("GitHub can only run Threadline from your own private copy of this project.")
    if linked is not None:
        ctx.io.say(
            f"This folder is linked to {linked.name}, which is not a private copy you "
            "administer, so nothing is saved there."
        )
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
    """Tell whether this folder is linked to the owner's own copy that git can push to.

    With the GitHub CLI signed in, the link must lead to a private repository
    the owner administers — never the public template. Without it, a link is
    all that can be seen.
    """
    if ctx.gateways.git.origin_url() is None:
        return False
    if not ctx.gateways.github.ready():
        return True
    linked = ctx.gateways.github.repository()
    return linked is not None and linked.is_own_private_copy


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
    created = ctx.gateways.github.repository()
    repository = created.name if created is not None else None
    ctx.io.say(f"Created your private copy {repository or name} and uploaded this folder to it.")
    return repository


def _explain_by_hand(ctx: SetupContext, *, gh_installed: bool) -> None:
    """Say how to make the copy on github.com."""
    io = ctx.io
    io.say("To make it on github.com:")
    io.say("  1. Open this project's page and click 'Use this template' >")
    io.say("     'Create a new repository'.")
    io.say("  2. Give it a name, choose Private, and click 'Create repository'.")
    io.say("  3. Download your copy ('git clone' its address), move the hidden file .env")
    io.say("     from the top folder of this project into the top folder of the new copy,")
    io.say(f"     and run 'uv run tracker setup {StepName.GITHUB}' in its backend folder.")
    if not gh_installed:
        io.say(f"Or install the GitHub CLI from {GITHUB_CLI_PAGE}, sign in with")
        io.say("'gh auth login', and run this step again: it can then create the copy for you.")
