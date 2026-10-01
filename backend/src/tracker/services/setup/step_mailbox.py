"""Step: the mailbox Threadline reads — Gmail, Outlook, iCloud, Yahoo, Fastmail or another.

Outlook is handed on to the Microsoft sign-in step. Every other mailbox is
read over IMAP with an app password: the step explains what that is, opens
the provider's page, tries the password live (sign in, open the inbox
read-only, count the recent messages) and only then stores it, encrypted, in
the database. The password never goes into ``.env``.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

from pydantic import SecretStr

from tracker.infrastructure.imap.connection import StoreAccess
from tracker.infrastructure.imap.reader import MailboxSurvey
from tracker.infrastructure.imap.session import ImapAccount
from tracker.services.setup import values
from tracker.services.setup.context import SetupContext
from tracker.services.setup.mail_sources import save_sources, saved_sources
from tracker.services.setup.models import StepName
from tracker.services.setup.owner_address import remember_address
from tracker.services.setup.step_microsoft import microsoft_access
from tracker.shared.constants.collection import INITIAL_WINDOW_DAYS
from tracker.shared.constants.mailbox import IMAP_PRESETS, ImapPreset, ImapProvider, MailSource
from tracker.shared.errors import ValidationFailedError

IMAP_PROVIDER: Final[str] = "IMAP_PROVIDER"
IMAP_USERNAME: Final[str] = "IMAP_USERNAME"
IMAP_HOST: Final[str] = "IMAP_HOST"
IMAP_PORT: Final[str] = "IMAP_PORT"

#: The answers understood, and what each one means.
_CHOICES: Final[dict[str, MailSource | ImapProvider]] = {
    "gmail": ImapProvider.GMAIL,
    "google": ImapProvider.GMAIL,
    "outlook": MailSource.OUTLOOK,
    "hotmail": MailSource.OUTLOOK,
    "microsoft": MailSource.OUTLOOK,
    "icloud": ImapProvider.ICLOUD,
    "apple": ImapProvider.ICLOUD,
    "yahoo": ImapProvider.YAHOO,
    "fastmail": ImapProvider.FASTMAIL,
    "other": ImapProvider.CUSTOM,
    "custom": ImapProvider.CUSTOM,
    "imap": ImapProvider.CUSTOM,
}

_QUESTION: Final[str] = (
    "Which mailbox should Threadline read? gmail, outlook, icloud, yahoo, fastmail or other"
)

#: What every provider has in common, in two plain sentences.
_APP_PASSWORD: Final[str] = (
    "Threadline signs in with an app password: a separate password just for "
    "Threadline, which you can remove at any time. Your normal password is never used."
)

#: What is particular to each provider, in one or two sentences.
_PROVIDER_NOTES: Final[dict[ImapProvider, str]] = {
    ImapProvider.GMAIL: (
        "Google offers app passwords only once 2-Step Verification is on. On a work "
        "or school account your administrator may have switched them off."
    ),
    ImapProvider.ICLOUD: (
        "Apple calls it an app-specific password; two-factor authentication must be on. "
        "Sign in, then open Sign-In and Security > App-Specific Passwords."
    ),
    ImapProvider.YAHOO: (
        "On Yahoo's Account Security page, choose 'Create app password' under External connections."
    ),
    ImapProvider.FASTMAIL: (
        "Fastmail offers IMAP on paid plans above Basic. In Settings, open Privacy & "
        "Security > Manage app passwords and access, and choose Mail access."
    ),
    ImapProvider.CUSTOM: (
        "Your provider's help pages explain how to make one: search them for "
        "'app password' and 'IMAP'."
    ),
}

_DEFAULT_PORT: Final[str] = "993"


class MailboxStep:
    """Chooses the mailbox and, for anything but Outlook, checks its app password."""

    name = StepName.MAILBOX
    title = "Your mailbox (Gmail, Outlook, iCloud, Yahoo, Fastmail or another)"

    async def is_done(self, ctx: SetupContext) -> bool:
        """Done when a mailbox is chosen and, for IMAP, its password is stored."""
        sources = saved_sources(ctx)
        if not sources:
            return False
        if MailSource.IMAP not in sources:
            return True
        username = ctx.env.get(IMAP_USERNAME)
        if username is None:
            return False
        return await ctx.gateways.mailbox.has_password(store_access(ctx), username)

    async def run(self, ctx: SetupContext) -> None:
        """Ask which mailbox, then connect it."""
        choice = ctx.ask_until_valid(lambda: ctx.io.ask(_QUESTION, default="gmail"), _choice)
        if isinstance(choice, ImapProvider):
            await _connect_imap(ctx, choice)
            return
        save_sources(ctx, (*(saved_sources(ctx) or ()), MailSource.OUTLOOK))
        ctx.io.say("The Microsoft step signs you in: 'uv run tracker setup microsoft'.")


def store_access(ctx: SetupContext) -> StoreAccess:
    """Collect what reaching the encrypted store needs from ``.env``."""
    return StoreAccess(
        supabase_url=ctx.require("SUPABASE_URL", StepName.SUPABASE),
        service_key=SecretStr(ctx.require("SUPABASE_SERVICE_ROLE_KEY", StepName.SUPABASE)),
        encryption_key=SecretStr(ctx.require("TOKEN_ENCRYPTION_KEY", StepName.ENCRYPTION)),
    )


async def _connect_imap(ctx: SetupContext, provider: ImapProvider) -> None:
    """Describe the mailbox, check its app password live, then save everything."""
    preset = IMAP_PRESETS[provider]
    account = _account(ctx, provider, preset)
    _explain(ctx, provider, preset)
    since = ctx.gateways.clock.now() - timedelta(days=INITIAL_WINDOW_DAYS)

    async def accept(raw: str) -> tuple[SecretStr, MailboxSurvey]:
        password = _app_password(raw)
        return password, await ctx.gateways.mailbox.check(account, password, since)

    password, survey = await ctx.ask_until_accepted(
        lambda: ctx.io.ask_secret(f"Paste the {preset.label} app password (it is not shown)"),
        accept,
    )
    _report(ctx, survey)
    await ctx.gateways.mailbox.save_password(store_access(ctx), account.username, password)
    ctx.io.say("Saved the app password, encrypted, in your database - it is not in .env.")
    _save_account(ctx, provider, account)
    await _save_sources(ctx)
    if "@" in account.username:
        remember_address(ctx, account.username.lower())


def _account(ctx: SetupContext, provider: ImapProvider, preset: ImapPreset) -> ImapAccount:
    """Ask for the address and, for another provider, the server."""
    if provider is not ImapProvider.CUSTOM:
        username = ctx.ask_until_valid(
            lambda: ctx.io.ask(f"Your {preset.label} address", default=ctx.env.get(IMAP_USERNAME)),
            values.email_address,
        )
        return ImapAccount(preset.host, preset.port, username, preset.label, preset.company)
    host = ctx.ask_until_valid(
        lambda: ctx.io.ask(
            "Your provider's IMAP server, such as imap.example.com",
            default=ctx.env.get(IMAP_HOST),
        ),
        values.server_name,
    )
    port = ctx.ask_until_valid(
        lambda: ctx.io.ask("Its port", default=ctx.env.get(IMAP_PORT) or _DEFAULT_PORT),
        values.port_number,
    )
    username = ctx.ask_until_valid(
        lambda: ctx.io.ask(
            "The name you sign in with, usually your address",
            default=ctx.env.get(IMAP_USERNAME),
        ),
        lambda raw: values.non_empty(raw, "the sign-in name"),
    )
    return ImapAccount(host, port, username, preset.label, preset.company)


def _explain(ctx: SetupContext, provider: ImapProvider, preset: ImapPreset) -> None:
    """Say what an app password is, and open the page where it is made."""
    ctx.io.say(_APP_PASSWORD)
    ctx.io.say(_PROVIDER_NOTES[provider])
    if preset.app_password_page:
        ctx.io.say(f"Opening {preset.app_password_page} - make one there, then come back.")
        ctx.io.open_page(preset.app_password_page)


def _app_password(raw: str) -> SecretStr:
    """Clean a pasted app password: providers show it in groups with spaces."""
    cleaned = "".join(raw.split())
    if not cleaned:
        message = "nothing was pasted"
        raise ValidationFailedError(message)
    return SecretStr(cleaned)


def _report(ctx: SetupContext, survey: MailboxSurvey) -> None:
    """Say what the live check found."""
    ctx.io.say(
        f"Connected. Your inbox has {survey.inbox_messages} messages from the last "
        f"{INITIAL_WINDOW_DAYS} days."
    )
    if survey.sent_folder is None:
        ctx.io.say(
            "No Sent folder was found, so your own replies cannot be read and some "
            "conversations may look unanswered."
        )
        return
    ctx.io.say(f"Your own replies are read from the folder '{survey.sent_folder}'.")


def _save_account(ctx: SetupContext, provider: ImapProvider, account: ImapAccount) -> None:
    """Write the provider, the sign-in name and, for another provider, the server."""
    ctx.env.set(IMAP_PROVIDER, provider.value)
    ctx.env.set(IMAP_USERNAME, account.username)
    if provider is ImapProvider.CUSTOM:
        ctx.env.set(IMAP_HOST, account.host)
        ctx.env.set(IMAP_PORT, str(account.port))
    else:
        for name in (IMAP_HOST, IMAP_PORT):
            if ctx.env.get(name) is not None:
                ctx.env.set(name, "")
    ctx.io.say(f"Saved {IMAP_PROVIDER} and {IMAP_USERNAME} in .env.")


async def _save_sources(ctx: SetupContext) -> None:
    """Add the IMAP mailbox, asking whether Outlook stays read too."""
    saved = saved_sources(ctx)
    had_outlook = (
        MailSource.OUTLOOK in saved
        if saved is not None
        else await ctx.gateways.microsoft.is_signed_in(microsoft_access(ctx))
    )
    keep = had_outlook and ctx.io.confirm(
        "Keep reading your Outlook mailbox and calendar as well?", default=True
    )
    save_sources(ctx, (MailSource.OUTLOOK, MailSource.IMAP) if keep else (MailSource.IMAP,))


def _choice(raw: str) -> MailSource | ImapProvider:
    """Read the answer to "which mailbox"."""
    choice = _CHOICES.get(raw.strip().lower())
    if choice is None:
        message = "please answer gmail, outlook, icloud, yahoo, fastmail or other"
        raise ValidationFailedError(message)
    return choice
