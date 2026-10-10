"""The short list at the end of ``tracker setup``: what was chosen, and how to change it.

It is read back from what the set-up left behind (``.env``, the workflow file,
the database), not from what this run asked, so a run that carried on from an
earlier one, or skipped finished steps, still lists every choice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from tracker.services.setup.context import SetupContext
from tracker.services.setup.mail_sources import saved_sources
from tracker.services.setup.models import StepName
from tracker.services.setup.step_dashboard import ADDRESS as DASHBOARD_ADDRESS
from tracker.services.setup.step_mailbox import IMAP_PROVIDER, IMAP_USERNAME
from tracker.services.setup.step_time_zone import OWNER_TIME_ZONE
from tracker.services.setup.workflow_schedule import read_schedule
from tracker.shared.constants.dashboard import HOSTED_DASHBOARD_URL
from tracker.shared.constants.mailbox import IMAP_PRESETS, ImapProvider, MailSource
from tracker.shared.constants.profile import DEFAULT_PRESET
from tracker.shared.errors import DatabaseUnavailableError, SourceAuthError, ValidationFailedError
from tracker.shared.logging import get_logger

_log = get_logger(__name__)

#: How the owner types the set-up, as every message names it.
_COMMAND: Final[str] = "uv run tracker setup"

#: What a choice nothing was saved for is called.
_NOT_SET: Final[str] = "not set yet"


@dataclass(frozen=True, slots=True)
class Chosen:
    """One line of the list.

    Attributes:
        label: What was chosen, such as ``Time zone``.
        value: The choice, in plain words.
        step: The step that changes it.
    """

    label: str
    value: str
    step: StepName


def say_summary(ctx: SetupContext, login: str | None) -> None:
    """Say every choice on one line each, with the command that changes it.

    Args:
        ctx: The set-up's context.
        login: The dashboard login's address, or ``None`` when Supabase could not say.
    """
    ctx.io.say("What was chosen, and the command that changes each:")
    for chosen in chosen_settings(ctx, login):
        ctx.io.say(f"  {chosen.label}: {chosen.value}. Change: {_COMMAND} {chosen.step}")


def chosen_settings(ctx: SetupContext, login: str | None) -> tuple[Chosen, ...]:
    """Read every choice back from what the set-up saved.

    Args:
        ctx: The set-up's context.
        login: The dashboard login's address, or ``None`` when Supabase could not say.

    Returns:
        The choices, in the order the steps make them.
    """
    sources = saved_sources(ctx) or ()
    return (
        Chosen("Mailbox", _mailbox(ctx, sources), StepName.MAILBOX),
        Chosen("Outlook", _outlook(sources), StepName.MICROSOFT),
        Chosen("Categories", _categories(ctx), StepName.CATEGORIES),
        Chosen("Time zone", ctx.env.get(OWNER_TIME_ZONE) or _NOT_SET, StepName.TIME_ZONE),
        Chosen("Daily run", _daily_time(ctx), StepName.SCHEDULE),
        Chosen("Dashboard", _dashboard(ctx), StepName.DASHBOARD),
        Chosen("Dashboard login", login or "not known", StepName.LOGIN),
    )


def _mailbox(ctx: SetupContext, sources: tuple[MailSource, ...]) -> str:
    """The mailbox read with an app password, or Outlook when that is the only one."""
    if MailSource.IMAP in sources:
        address = ctx.env.get(IMAP_USERNAME) or _NOT_SET
        return f"{address} ({_provider_label(ctx.env.get(IMAP_PROVIDER))})"
    return "Outlook" if MailSource.OUTLOOK in sources else _NOT_SET


def _provider_label(saved: str | None) -> str:
    """The provider's name as the set-up shows it."""
    providers = {provider.value: provider for provider in ImapProvider}
    provider = providers.get((saved or "").strip().lower(), ImapProvider.CUSTOM)
    return IMAP_PRESETS[provider].label


def _outlook(sources: tuple[MailSource, ...]) -> str:
    """Whether the Outlook mailbox and calendar are read."""
    return "connected" if MailSource.OUTLOOK in sources else "not connected"


def _categories(ctx: SetupContext) -> str:
    """The list of categories chosen, or the usual one."""
    try:
        preset = ctx.choices().chosen_preset()
    except (DatabaseUnavailableError, SourceAuthError, ValidationFailedError) as error:
        _log.warning("chosen_categories_unavailable", code=error.code)
        return "not known"
    name = (preset or DEFAULT_PRESET).replace("_", "-")
    return f"the {name} list" if preset else f"the usual {name} list"


def _daily_time(ctx: SetupContext) -> str:
    """When the daily run starts, as the workflow file says."""
    try:
        schedule = read_schedule(ctx.gateways.workflow.read())
    except FileNotFoundError:
        return _NOT_SET
    return f"every day at {schedule.describe()}" if schedule is not None else _NOT_SET


def _dashboard(ctx: SetupContext) -> str:
    """The shared dashboard, or the address of the owner's own copy."""
    address = ctx.env.get(DASHBOARD_ADDRESS)
    if address is None:
        return _NOT_SET
    return "Threadline's shared dashboard" if address == HOSTED_DASHBOARD_URL else address
