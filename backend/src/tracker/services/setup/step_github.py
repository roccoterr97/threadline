"""Step: put the settings into the GitHub repository, where the daily run reads them.

Each setting becomes an Actions *secret* (hidden in every log) or, when it is
neither secret nor personal, an Actions *variable*; ``shared/constants/github.py``
decides which. It first makes sure a private copy exists on GitHub (``github_copy``), since
the settings are saved into it. With the GitHub CLI signed in, the step saves them all after one
yes, handing each value to ``gh`` on its standard input. Without it, the step
lists the names and opens the page, and can copy each value to the clipboard.

The Claude subscription key from ``claude setup-token`` is asked for here and
goes straight to GitHub: it is never written to ``.env`` or anywhere else.
"""

from __future__ import annotations

from typing import Final

from pydantic import SecretStr

from tracker.services.setup.context import SetupContext
from tracker.services.setup.github_copy import find_or_create_copy
from tracker.services.setup.models import StepName
from tracker.services.setup.step_cloud import cloud_variable_names, copy_values
from tracker.shared.constants.github import (
    ACTIONS_SECRETS_PAGE,
    CLAUDE_TOKEN_SECRET,
    REQUIRED_SECRETS,
    VARIABLE_SETTINGS,
    WORKFLOW_PAGE,
)
from tracker.shared.errors import ValidationFailedError

#: Where the page is when the repository's name is not known.
_PAGE_BY_HAND: Final[str] = (
    "your repository on github.com > Settings > Secrets and variables > Actions"
)


class GitHubStep:
    """Saves the settings as the repository's Actions secrets and variables."""

    name = StepName.GITHUB
    title = "The settings on GitHub"

    async def is_done(self, ctx: SetupContext) -> bool:
        """Never skipped: GitHub cannot be asked what it holds, only told."""
        return False

    async def run(self, ctx: SetupContext) -> None:
        """Collect the key, then save everything with gh or show how to by hand."""
        secrets, variables = split_settings(ctx)
        ctx.io.say("GitHub runs Threadline every day on your own copy of this project.")
        repository = find_or_create_copy(ctx)
        ctx.io.say("It needs your settings: secret ones as 'secrets', the rest as 'variables'.")
        token = _ask_token(ctx)
        if repository is not None and ctx.io.confirm(
            f"Save {len(secrets) + (token is not None)} secrets and {len(variables)} variables "
            f"in {repository} with the GitHub CLI now?",
            default=True,
        ):
            _save_with_cli(ctx, repository, secrets, variables, token)
            return
        _show_by_hand(ctx, repository, secrets, variables, token)


def split_settings(ctx: SetupContext) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Sort the saved settings into secrets and variables.

    Args:
        ctx: The set-up's context.

    Returns:
        The names to save as secrets, then those to save as variables.

    Raises:
        ValidationFailedError: If a setting every run needs is not saved yet.
    """
    names = cloud_variable_names(ctx)
    missing = [
        name for name in REQUIRED_SECRETS if name != CLAUDE_TOKEN_SECRET and name not in names
    ]
    if missing:
        message = f"{', '.join(missing)} not saved yet - run 'uv run tracker setup' first"
        raise ValidationFailedError(message)
    secrets = tuple(name for name in names if name not in VARIABLE_SETTINGS)
    variables = tuple(name for name in names if name in VARIABLE_SETTINGS)
    return secrets, variables


def _ask_token(ctx: SetupContext) -> SecretStr | None:
    """Ask for the Claude subscription key; it is kept in memory only."""
    io = ctx.io
    io.say("GitHub also needs a key to use your Claude subscription. To make it:")
    io.say("  Open a second Terminal window (⌘ + N), run claude setup-token, sign in in the")
    io.say("  browser, then copy the long key it prints back in that window (it starts with")
    io.say("  sk-ant-). It lasts one year.")
    raw = io.ask_secret(
        f"Paste that key for {CLAUDE_TOKEN_SECRET} (it is not shown), or press Enter to skip"
    )
    cleaned = "".join(raw.split())
    if not cleaned:
        io.say(f"Skipped: add {CLAUDE_TOKEN_SECRET} on GitHub yourself before the first run.")
        return None
    return SecretStr(cleaned)


def _save_with_cli(
    ctx: SetupContext,
    repository: str,
    secrets: tuple[str, ...],
    variables: tuple[str, ...],
    token: SecretStr | None,
) -> None:
    """Save every value with the GitHub CLI, naming each one and showing none."""
    github = ctx.gateways.github
    for name in secrets:
        github.set_secret(repository, name, SecretStr(ctx.env.get(name) or ""))
        ctx.io.say(f"  secret {name} saved")
    if token is not None:
        github.set_secret(repository, CLAUDE_TOKEN_SECRET, token)
        ctx.io.say(f"  secret {CLAUDE_TOKEN_SECRET} saved (it was not written anywhere else)")
    for name in variables:
        github.set_variable(repository, name, ctx.env.get(name) or "")
        ctx.io.say(f"  variable {name} saved")
    ctx.io.say(
        f"Done. Next, start the first run by hand: {WORKFLOW_PAGE.format(repository=repository)}"
    )


def _show_by_hand(
    ctx: SetupContext,
    repository: str | None,
    secrets: tuple[str, ...],
    variables: tuple[str, ...],
    token: SecretStr | None,
) -> None:
    """List the names, open the page, and offer to copy each value in turn."""
    io = ctx.io
    page = ACTIONS_SECRETS_PAGE.format(repository=repository) if repository else _PAGE_BY_HAND
    io.say(f"Add them on this page: {page}")
    io.say("On the Secrets tab, one 'New repository secret' each:")
    for name in (*secrets, CLAUDE_TOKEN_SECRET):
        io.say(f"  {name}")
    io.say("On the Variables tab, one 'New repository variable' each:")
    for name in variables:
        io.say(f"  {name}")
    if repository:
        io.open_page(page)
    if not io.confirm("Copy each value to the clipboard, one at a time?", default=True):
        return
    values = {name: ctx.env.get(name) or "" for name in (*secrets, *variables)}
    if token is not None:
        values[CLAUDE_TOKEN_SECRET] = token.get_secret_value()
    copy_values(ctx, values)
