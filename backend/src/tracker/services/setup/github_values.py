"""Putting saved settings into the repository's Actions secrets and variables.

The GitHub step saves every setting this way. An extra that adds settings
afterwards, such as LinkedIn, reuses the same save for just those settings, so
the daily run on GitHub does not keep running without them.
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import SecretStr

from tracker.services.setup.context import SetupContext
from tracker.services.setup.github_copy import linked_copy
from tracker.services.setup.models import StepName
from tracker.shared.constants.github import CLAUDE_TOKEN_SECRET, VARIABLE_SETTINGS
from tracker.shared.errors import SourceUnavailableError


def save_on_github(
    ctx: SetupContext,
    repository: str,
    secrets: Iterable[str],
    variables: Iterable[str],
    claude_key: SecretStr | None = None,
) -> None:
    """Save settings with the GitHub CLI, naming each one and showing none.

    Args:
        ctx: The set-up's context.
        repository: The copy, as ``owner/name``.
        secrets: Names to save as secrets, read from ``.env``.
        variables: Names to save as variables, read from ``.env``.
        claude_key: The Claude key, which is never in ``.env``.

    Raises:
        SourceUnavailableError: If the GitHub CLI did not save one of them.
    """
    github = ctx.gateways.github
    for name in secrets:
        github.set_secret(repository, name, SecretStr(ctx.env.get(name) or ""))
        ctx.io.say(f"  secret {name} saved")
    if claude_key is not None:
        github.set_secret(repository, CLAUDE_TOKEN_SECRET, claude_key)
        ctx.io.say(f"  secret {CLAUDE_TOKEN_SECRET} saved (it was not written anywhere else)")
    for name in variables:
        github.set_variable(repository, name, ctx.env.get(name) or "")
        ctx.io.say(f"  variable {name} saved")


def offer_to_send(ctx: SetupContext, names: Iterable[str]) -> None:
    """Offer to send settings an extra just saved to GitHub, or say the command that does.

    The GitHub step ran earlier, so GitHub does not know these settings, and
    the daily run reads them there rather than from ``.env``.

    Args:
        ctx: The set-up's context.
        names: The settings the extra saved; those left empty are ignored.
    """
    io = ctx.io
    saved = [name for name in names if ctx.env.get(name)]
    command = f"uv run tracker setup {StepName.GITHUB}"
    copy = linked_copy(ctx)
    if not saved or copy is None:
        return
    io.say("The daily run on GitHub reads its settings there, not from this computer, so")
    io.say("it does not have these yet.")
    if not copy.confirmed or not io.confirm(
        f"Send them to {copy.name} on GitHub now?", default=True
    ):
        io.say(f"To send them later, run: {command}")
        return
    try:
        save_on_github(
            ctx,
            copy.name,
            [name for name in saved if name not in VARIABLE_SETTINGS],
            [name for name in saved if name in VARIABLE_SETTINGS],
        )
    except SourceUnavailableError as error:
        io.say(f"{error.message}. To send them later, run: {command}")
