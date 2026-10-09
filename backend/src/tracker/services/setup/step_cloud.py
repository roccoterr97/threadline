"""The alternative route: what a Claude cloud routine needs. Names only, never values.

Threadline normally runs on GitHub Actions (the schedule and github steps).
A Claude cloud routine is the alternative, for an owner whose summary must go
through the Gmail connector, such as one who reads Outlook alone.
"""

from __future__ import annotations

from tracker.services.setup import values
from tracker.services.setup.context import SetupContext
from tracker.services.setup.mail_sources import saved_sources
from tracker.services.setup.models import StepName
from tracker.shared.config import Settings
from tracker.shared.constants.mailbox import IMAP_PRESETS, ImapProvider, MailSource
from tracker.shared.constants.setup import (
    CLAUDE_CODE_PAGE,
    CLOUD_LINKEDIN_HOST,
    CLOUD_OUTLOOK_HOST,
    LOCAL_ONLY_SETTINGS,
)


class CloudStep:
    """Lists the cloud variables and allowed domains, and offers to copy values."""

    name = StepName.CLOUD
    title = "The alternative: a Claude cloud routine"

    async def is_done(self, ctx: SetupContext) -> bool:
        """Never skipped: it only shows a list."""
        return False

    async def run(self, ctx: SetupContext) -> None:
        """Show the variable names and the domains, then copy values on request."""
        io = ctx.io
        io.say("Threadline normally runs on GitHub (the schedule and github steps).")
        if not io.confirm(
            "Set up the alternative instead, a Claude cloud routine? Only needed when the "
            "summary must go through the Gmail connector",
            default=False,
        ):
            io.say("Skipped. To set it up later: uv run tracker setup cloud")
            return
        names = cloud_variable_names(ctx)
        io.say("The routine runs in a Claude cloud environment (the guide, part 8c).")
        io.say("Add these variables to it, one per line as NAME=value:")
        for name in names:
            io.say(f"  {name}")
        io.say("Network access: Custom. Allowed domains, one per line:")
        for host in allowed_hosts(ctx):
            io.say(f"  {host}")
        io.say("Also tick 'Also include default list of common package managers'.")
        io.open_page(CLAUDE_CODE_PAGE)
        if io.confirm("Copy each value to the clipboard, one at a time?", default=True):
            copy_values(ctx, {name: ctx.env.get(name) or "" for name in names})


def cloud_setting_names() -> tuple[str, ...]:
    """Every setting a run elsewhere may be given, in the order Threadline declares them."""
    declared = [field.upper() for field in Settings.model_fields]
    return tuple(name for name in declared if name not in LOCAL_ONLY_SETTINGS)


def cloud_variable_names(ctx: SetupContext) -> tuple[str, ...]:
    """The saved settings Threadline reads, in the order it declares them."""
    return tuple(name for name in cloud_setting_names() if ctx.env.get(name))


def allowed_hosts(ctx: SetupContext) -> tuple[str, ...]:
    """The domains the cloud environment must be allowed to reach."""
    ref = values.project_ref(ctx.require("SUPABASE_URL", StepName.SUPABASE))
    hosts = [f"{ref}.supabase.co"]
    sources = saved_sources(ctx) or (MailSource.OUTLOOK,)
    if MailSource.OUTLOOK in sources:
        hosts.append(CLOUD_OUTLOOK_HOST)
    if MailSource.IMAP in sources and (imap_host := _imap_host(ctx)):
        hosts.append(imap_host)
    if ctx.env.get("LINKEDIN_ACCESS_TOKEN"):
        hosts.append(CLOUD_LINKEDIN_HOST)
    return tuple(hosts)


def _imap_host(ctx: SetupContext) -> str | None:
    """The IMAP server the saved settings point at, if any."""
    named = (ctx.env.get("IMAP_PROVIDER") or "").strip().lower()
    preset = next(
        (IMAP_PRESETS[provider] for provider in ImapProvider if provider.value == named),
        IMAP_PRESETS[ImapProvider.CUSTOM],
    )
    return ctx.env.get("IMAP_HOST") or preset.host or None


def copy_values(ctx: SetupContext, values_by_name: dict[str, str]) -> None:
    """Put each value on the clipboard in turn, never on screen.

    Args:
        ctx: The set-up's context.
        values_by_name: The values to copy, by setting name, in order.
    """
    for name, value in values_by_name.items():
        if not ctx.io.copy(value):
            ctx.io.say("No clipboard is available here; copy the values from .env instead.")
            return
        ctx.io.pause(f"{name} is on the clipboard: once it is pasted after '{name}='")
    ctx.io.copy("")
    ctx.io.say("Done. The clipboard has been emptied.")
