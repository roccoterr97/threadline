"""Step: put the settings into the GitHub repository, where the daily run reads them.

Each setting becomes an Actions *secret* (hidden in every log) or, when it is
neither secret nor personal, an Actions *variable*; ``shared/constants/github.py``
decides which. It first makes sure a private copy exists on GitHub (``github_copy``), since
the settings are saved into it. With the GitHub CLI signed in, the step saves them all after one
yes, handing each value to ``gh`` on its standard input, then offers once to delete
the settings emptied in ``.env`` that GitHub still holds, and last starts the
first daily run (``first_run``). Without it, the step lists the names and opens
the page, can copy each value to the clipboard, and says where to press 'Run
workflow' by hand.

The Claude subscription key from ``claude setup-token`` is asked for here
(``claude_key`` checks it was copied whole) and goes straight to GitHub: it is
never written to ``.env`` or anywhere else.
"""

from __future__ import annotations

from typing import Final

from pydantic import SecretStr

from tracker.services.setup.claude_key import ask_claude_key
from tracker.services.setup.context import SetupContext
from tracker.services.setup.first_run import (
    FirstRun,
    say_first_run_by_hand,
    start_first_run,
    workflow_page,
)
from tracker.services.setup.github_copy import find_or_create_copy
from tracker.services.setup.github_values import save_on_github
from tracker.services.setup.mail_sources import saved_sources, summary_route
from tracker.services.setup.models import StepGroup, StepName
from tracker.services.setup.step_cloud import (
    cloud_setting_names,
    cloud_variable_names,
    copy_values,
)
from tracker.services.setup.step_mailbox import MailboxStep
from tracker.services.setup.workflow_schedule import offer_unsent_change
from tracker.shared.constants.github import (
    ACTIONS_SECRETS_PAGE,
    CLAUDE_TOKEN_SECRET,
    REQUIRED_SECRETS,
    VARIABLE_SETTINGS,
    WORKFLOW_FIXED_SETTINGS,
)
from tracker.shared.constants.mailbox import DeliveryRoute, MailSource
from tracker.shared.errors import SourceUnavailableError, ValidationFailedError

#: Where the page is when the repository's name is not known.
_PAGE_BY_HAND: Final[str] = (
    "your repository on github.com > Settings > Secrets and variables > Actions"
)


class GitHubStep:
    """Saves the settings as the repository's Actions secrets and variables."""

    name = StepName.GITHUB
    title = "The settings on GitHub"

    def __init__(self) -> None:
        """Start with no first run: it is known once the step has run."""
        #: How the first daily run was left; ``None`` until the step has run.
        self.first_run: FirstRun | None = None

    async def is_done(self, ctx: SetupContext) -> bool:
        """Never skipped: GitHub cannot be asked what it holds, only told."""
        return False

    async def run(self, ctx: SetupContext) -> None:
        """Collect the key, save everything with gh and start the first run, or show how to."""
        split_settings(ctx)
        ctx.io.say("GitHub runs Threadline every day on your own copy of this project.")
        by_email = await _settle_summary_route(ctx)
        secrets, variables = split_settings(ctx)
        repository = find_or_create_copy(ctx)
        if repository is not None:
            offer_unsent_change(ctx)
        ctx.io.say("It needs your settings: secret ones as 'secrets', the rest as 'variables'.")
        token = ask_claude_key(ctx)
        if repository is not None and ctx.io.confirm(
            f"Save {len(secrets) + (token is not None)} secrets and {len(variables)} variables "
            f"in {repository} with the GitHub CLI now?",
            default=True,
        ):
            self.first_run = await _save_with_cli(
                ctx, repository, secrets, variables, token, by_email
            )
            return
        _show_by_hand(ctx, repository, secrets, variables, token)
        say_first_run_by_hand(ctx, repository)
        self.first_run = FirstRun(
            started=False, page=workflow_page(repository), summary_by_email=by_email
        )


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


async def _settle_summary_route(ctx: SetupContext) -> bool:
    """Say whether GitHub can e-mail the summary, offering the mailbox that lets it.

    Args:
        ctx: The set-up's context.

    Returns:
        Whether the summary will be sent by e-mail from GitHub.
    """
    if summary_route(ctx) is DeliveryRoute.SMTP:
        return True
    _say_github_cannot_send(ctx)
    if MailSource.IMAP in (saved_sources(ctx) or ()):
        return False
    if ctx.io.confirm(
        "Connect a Gmail (or other) mailbox with an app password now, so the e-mail can come?",
        default=True,
    ):
        await MailboxStep().run(ctx)
    else:
        ctx.io.say("Without one, no summary e-mail will arrive. To add one later, run")
        ctx.io.say(
            f"'uv run tracker setup {StepName.MAILBOX}', then 'uv run tracker setup github'."
        )
    return summary_route(ctx) is DeliveryRoute.SMTP


def _say_github_cannot_send(ctx: SetupContext) -> None:
    """Warn that the run on GitHub will do everything but e-mail the summary."""
    io = ctx.io
    io.say("Note: with these settings the run on GitHub cannot e-mail you the morning summary.")
    if MailSource.IMAP in (saved_sources(ctx) or ()):
        io.say("  SUMMARY_DELIVERY is set to gmail_connector, which only a Claude cloud routine")
        io.say("  has. Remove that line from .env to send from your mailbox instead.")
    else:
        io.say("  The morning e-mail needs a mailbox with an app password: Gmail, iCloud, Yahoo,")
        io.say("  Fastmail or another standard (IMAP and SMTP) mailbox. Outlook alone has no app")
        io.say("  password to send with.")
    io.say("  Everything else still runs, and the dashboard is updated every morning.")
    io.say("  The other way to get the e-mail is the Claude cloud route:")
    io.say(f"  'uv run tracker setup {StepGroup.EXTRAS}'.")


async def _save_with_cli(
    ctx: SetupContext,
    repository: str,
    secrets: tuple[str, ...],
    variables: tuple[str, ...],
    token: SecretStr | None,
    summary_by_email: bool,
) -> FirstRun:
    """Save every value with the GitHub CLI, naming each one and showing none, then start."""
    save_on_github(ctx, repository, secrets, variables, token)
    _remove_emptied(ctx, repository, secrets, variables)
    ctx.io.say("Done. GitHub has everything it needs to run Threadline on your copy.")
    return await start_first_run(
        ctx,
        repository,
        summary_by_email=summary_by_email,
        claude_key_on_github=_claude_key_on_github(ctx, repository, token),
    )


def _claude_key_on_github(
    ctx: SetupContext, repository: str, token: SecretStr | None
) -> bool | None:
    """Whether GitHub holds the Claude key; ``None`` when it could not be asked."""
    if token is not None:
        return True
    try:
        return CLAUDE_TOKEN_SECRET in ctx.gateways.github.secret_names(repository)
    except SourceUnavailableError:
        return None


def _remove_emptied(
    ctx: SetupContext, repository: str, secrets: tuple[str, ...], variables: tuple[str, ...]
) -> None:
    """Offer, once, to delete the settings emptied in ``.env`` but still on GitHub.

    Only Threadline's own setting names are ever considered, never the Claude
    key (it is not kept in ``.env``) and never anything else in the repository.
    """
    github = ctx.gateways.github
    known = set(cloud_setting_names()) - WORKFLOW_FIXED_SETTINGS
    try:
        on_github_secrets = github.secret_names(repository)
        on_github_variables = github.variable_names(repository)
    except SourceUnavailableError as error:
        ctx.io.say(f"  {error.message}, so a setting you emptied may still be on GitHub.")
        return
    stale_secrets = sorted((on_github_secrets & (known - VARIABLE_SETTINGS)) - set(secrets))
    stale_variables = sorted((on_github_variables & known & VARIABLE_SETTINGS) - set(variables))
    if not stale_secrets and not stale_variables:
        return
    ctx.io.say("These settings are empty in your .env but still saved on GitHub:")
    for name in stale_secrets:
        ctx.io.say(f"  secret {name}")
    for name in stale_variables:
        ctx.io.say(f"  variable {name}")
    question = "Delete them on GitHub, so the daily run stops using them?"
    if not ctx.io.confirm(question, default=True):
        ctx.io.say("Kept them on GitHub.")
        return
    for name in stale_secrets:
        github.delete_secret(repository, name)
        ctx.io.say(f"  secret {name} deleted")
    for name in stale_variables:
        github.delete_variable(repository, name)
        ctx.io.say(f"  variable {name} deleted")


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
