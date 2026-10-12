"""Step: the mailbox Threadline reads — Gmail, Outlook, iCloud, Yahoo, Fastmail or another.

An express run asks only for the address and tells the provider from it
(``mail_provider``); the provider question is left for an address whose
provider the ending does not show. Any other run asks the provider first.

Outlook is handed on to the Microsoft sign-in step. Every other mailbox is
read over IMAP with an app password: the step explains what that is, opens
the provider's page (``app_password``), picks the password up from the
clipboard or takes it pasted, tries it live (sign in, open the inbox
read-only, count the recent messages) and only then stores it, encrypted, in
the database. The password never goes into ``.env``.

A full run asks all that while Supabase starts a new project
(:func:`ask_while_project_starts`), when the database cannot store anything
yet: the checked password is held in memory (``mailbox_answers``) and this
step stores it once the database is ready, without asking again.

The morning summary is sent from the same mailbox by SMTP. The known providers'
sending servers are built in; for another provider the step asks for it and
signs in to it once, so a wrong server shows up now rather than every morning.
That comes last, once the checked password and the mailbox are saved: a
sending server that will not work, or that the owner does not know yet, never
costs them the mailbox, and they can carry on without it and add it later.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

from pydantic import SecretStr

from tracker.infrastructure.imap.connection import StoreAccess
from tracker.infrastructure.imap.reader import MailboxSurvey
from tracker.infrastructure.imap.session import ImapAccount
from tracker.infrastructure.smtp import SmtpAccount
from tracker.services.setup import values
from tracker.services.setup.app_password import AppPasswordQuestion
from tracker.services.setup.context import MAX_ATTEMPTS, SetupContext
from tracker.services.setup.mail_provider import provider_for
from tracker.services.setup.mail_sources import save_sources, saved_sources, summary_route
from tracker.services.setup.mailbox_answers import CheckedImapMailbox, MailboxAnswer
from tracker.services.setup.models import StepName
from tracker.services.setup.owner_address import remember_address
from tracker.services.setup.step_microsoft import microsoft_access
from tracker.shared.constants.collection import INITIAL_WINDOW_DAYS
from tracker.shared.constants.mailbox import (
    IMAP_PRESETS,
    SMTP_TLS_PORT,
    DeliveryRoute,
    ImapPreset,
    ImapProvider,
    MailSource,
)
from tracker.shared.errors import (
    AppPasswordUnavailableError,
    SourceAuthError,
    SourceUnavailableError,
    TrackerError,
    ValidationFailedError,
)
from tracker.shared.logging import get_logger

_log = get_logger(__name__)

IMAP_PROVIDER: Final[str] = "IMAP_PROVIDER"
IMAP_USERNAME: Final[str] = "IMAP_USERNAME"
IMAP_HOST: Final[str] = "IMAP_HOST"
IMAP_PORT: Final[str] = "IMAP_PORT"
SMTP_HOST: Final[str] = "SMTP_HOST"
SMTP_PORT: Final[str] = "SMTP_PORT"

#: How a provider's receiving server is usually named, and its sending one.
_IMAP_HOST_PREFIX: Final[str] = "imap."
_SMTP_HOST_PREFIX: Final[str] = "smtp."

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

#: The one question of an express run.
ADDRESS_PROMPT: Final[str] = "Your e-mail address"

#: How Outlook is named when it was told from the address.
_OUTLOOK_LABEL: Final[str] = "Outlook"

_DEFAULT_PORT: Final[str] = "993"

#: Said before the mailbox is asked for while Supabase starts the project.
MEANWHILE: Final[str] = "Meanwhile, your mailbox."

#: Said when the mailbox could not be settled while the project started.
_ASKED_AGAIN_LATER: Final[str] = "{reason}. Your mailbox is asked again once the project is up."

#: What asking for the mailbox can end with, short of the owner stopping the set-up.
_MAILBOX_PROBLEMS: Final[tuple[type[TrackerError], ...]] = (
    ValidationFailedError,
    SourceAuthError,
    SourceUnavailableError,
    AppPasswordUnavailableError,
)


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
        """Save the mailbox asked for while the project started, or ask for it now, then save it."""
        answer = ctx.session.held_mailbox or await ask_mailbox(ctx)
        ctx.session.held_mailbox = None
        if isinstance(answer, CheckedImapMailbox):
            await _save_imap(ctx, answer)
            return
        save_sources(ctx, (*(saved_sources(ctx) or ()), MailSource.OUTLOOK))
        if ctx.session.express:
            ctx.io.say("Outlook is read through a Microsoft sign-in: it comes next.")
            return
        ctx.io.say("The Microsoft step signs you in: 'uv run tracker setup microsoft'.")


async def ask_mailbox(ctx: SetupContext) -> MailboxAnswer:
    """Ask which mailbox (an express run: only the address), and check its app password live.

    Nothing is saved: that needs the database, which the mailbox step uses.

    Args:
        ctx: The set-up's context.

    Returns:
        The mailbox with its accepted app password, or Outlook.

    Raises:
        ValidationFailedError: If an answer was refused every time.
        SourceAuthError: If the provider refused every app password.
        SourceUnavailableError: If the mailbox could not be reached.
        AppPasswordUnavailableError: If the provider offers no app passwords.
    """
    if ctx.session.express:
        address, choice = _address_and_provider(ctx)
    else:
        address, choice = None, _asked_provider(ctx)
    if isinstance(choice, ImapProvider):
        return await _checked_imap(ctx, choice, address)
    return MailSource.OUTLOOK


async def ask_while_project_starts(ctx: SetupContext) -> None:
    """Ask for the mailbox while Supabase starts a new project, holding the answer in memory.

    Only a full run does it, and only when the mailbox step will need asking:
    a mailbox read with an app password stores it in the database, which a new
    project does not have yet. A problem is said in one line, and the mailbox
    step then asks again once the project is up. Stopping the set-up stops it.

    Args:
        ctx: The set-up's context; the answer is kept in its session.
    """
    if ctx.session.named_step is not None:
        return
    sources = saved_sources(ctx)
    if sources is not None and MailSource.IMAP not in sources:
        return
    ctx.io.say("")
    ctx.io.say(MEANWHILE)
    try:
        ctx.session.held_mailbox = await ask_mailbox(ctx)
    except _MAILBOX_PROBLEMS as error:
        _log.info("mailbox_not_settled_early", code=error.code)
        ctx.io.say(_ASKED_AGAIN_LATER.format(reason=error.message))


def _asked_provider(ctx: SetupContext) -> MailSource | ImapProvider:
    """Ask which mailbox Threadline should read."""
    return ctx.ask_until_valid(lambda: ctx.io.ask(_QUESTION, default="gmail"), _choice)


def _address_and_provider(ctx: SetupContext) -> tuple[str, MailSource | ImapProvider]:
    """Ask the address alone, and ask the provider only when the address does not show it."""
    address = ctx.ask_until_valid(
        lambda: ctx.io.ask(ADDRESS_PROMPT, default=ctx.env.get(IMAP_USERNAME)),
        values.email_address,
    )
    provider = provider_for(address)
    if provider is None:
        ctx.io.say("The address does not show who runs this mailbox, so please say.")
        return address, _asked_provider(ctx)
    label = IMAP_PRESETS[provider].label if isinstance(provider, ImapProvider) else _OUTLOOK_LABEL
    ctx.detail(f"From the address, your mailbox is {label}.")
    return address, provider


def store_access(ctx: SetupContext) -> StoreAccess:
    """Collect what reaching the encrypted store needs from ``.env``."""
    return StoreAccess(
        supabase_url=ctx.require("SUPABASE_URL", StepName.SUPABASE),
        service_key=SecretStr(ctx.require("SUPABASE_SERVICE_ROLE_KEY", StepName.SUPABASE)),
        encryption_key=SecretStr(ctx.require("TOKEN_ENCRYPTION_KEY", StepName.ENCRYPTION)),
    )


async def _checked_imap(
    ctx: SetupContext, provider: ImapProvider, address: str | None
) -> CheckedImapMailbox:
    """Describe the mailbox and check its app password live; nothing is saved."""
    preset = IMAP_PRESETS[provider]
    account = _account(ctx, provider, preset, address)
    question = AppPasswordQuestion(ctx, provider, account.username)
    question.explain()
    question.open_page()
    since = ctx.gateways.clock.now() - timedelta(days=INITIAL_WINDOW_DAYS)

    async def accept(raw: str) -> tuple[SecretStr, MailboxSurvey]:
        password = _app_password(raw)
        return password, await ctx.gateways.mailbox.check(account, password, since)

    password, survey = await ctx.ask_until_accepted(question.ask, accept)
    _report(ctx, survey)
    return CheckedImapMailbox(provider, account, password)


async def _save_imap(ctx: SetupContext, mailbox: CheckedImapMailbox) -> None:
    """Store the checked app password, encrypted, then save the mailbox in ``.env``."""
    account, password = mailbox.account, mailbox.password
    same_mailbox = _is_saved_mailbox(ctx, account)
    await ctx.gateways.mailbox.save_password(store_access(ctx), account.username, password)
    ctx.detail("Saved the app password, encrypted, in your database - it is not in .env.")
    _save_account(ctx, mailbox.provider, account)
    await _save_sources(ctx)
    if "@" in account.username:
        remember_address(ctx, account.username.lower())
    if mailbox.provider is ImapProvider.CUSTOM and _summary_goes_by_smtp(ctx):
        await _connect_sending(ctx, account, password, keep_saved=same_mailbox)


def _is_saved_mailbox(ctx: SetupContext, account: ImapAccount) -> bool:
    """Whether ``.env`` already names this mailbox: same server, same sign-in name."""
    return (ctx.env.get(IMAP_HOST), ctx.env.get(IMAP_USERNAME)) == (account.host, account.username)


async def _connect_sending(
    ctx: SetupContext, account: ImapAccount, password: SecretStr, *, keep_saved: bool
) -> None:
    """Save the sending server that signs in, or leave it for later.

    Args:
        ctx: The set-up's context.
        account: The mailbox that was just connected.
        password: Its checked app password.
        keep_saved: Whether a sending server already in ``.env`` belongs to
            this same mailbox and may stay when none signs in now.
    """
    sending = await _sending_server(ctx, account, password)
    if sending is not None:
        _save_sending_server(ctx, sending)
        return
    if not keep_saved:
        _forget_sending_server(ctx)
    _say_sending_left_for_later(ctx)


def _account(
    ctx: SetupContext, provider: ImapProvider, preset: ImapPreset, address: str | None
) -> ImapAccount:
    """Ask for the address, unless it was given, and, for another provider, the server."""
    if provider is not ImapProvider.CUSTOM:
        username = address or ctx.ask_until_valid(
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
            default=address or ctx.env.get(IMAP_USERNAME),
        ),
        lambda raw: values.non_empty(raw, "the sign-in name"),
    )
    return ImapAccount(host, port, username, preset.label, preset.company)


async def _sending_server(
    ctx: SetupContext, account: ImapAccount, password: SecretStr
) -> SmtpAccount | None:
    """Ask another provider's sending server and sign in to it once.

    After a failed sign-in the owner may try another server or carry on
    without one; after the last attempt the step carries on by itself.

    Returns:
        The checked server, or ``None`` when none could be signed in to.
    """
    ctx.io.say("The morning summary is sent from this mailbox, through its sending (SMTP) server.")
    for attempt in range(1, MAX_ATTEMPTS + 1):
        sending = _asked_sending_server(ctx, account)
        if sending is None:
            return None
        if await _signs_in(ctx, sending, password):
            return sending
        if attempt < MAX_ATTEMPTS and not ctx.io.confirm(
            "Try another server or port? Answer n to carry on without it for now", default=True
        ):
            break
    return None


def _asked_sending_server(ctx: SetupContext, account: ImapAccount) -> SmtpAccount | None:
    """Ask the sending server; ``None`` when no answer was a server name or a port.

    The mailbox is already saved by now, so answers that never pass their
    check end the asking, not the step.
    """
    try:
        return _ask_sending_server(ctx, account)
    except ValidationFailedError as error:
        ctx.io.say(f"  {error.message}.")
        return None


async def _signs_in(ctx: SetupContext, sending: SmtpAccount, password: SecretStr) -> bool:
    """Sign in to the sending server once, saying why when it does not work."""
    try:
        await ctx.gateways.mailbox.check_sending(sending, password)
    except (SourceAuthError, SourceUnavailableError) as error:
        ctx.io.say(f"  {error.message}. Please check the server and port.")
        return False
    ctx.io.say("Signed in to the sending server. Nothing was sent.")
    return True


def _say_sending_left_for_later(ctx: SetupContext) -> None:
    """Say what works without the sending server, and how to add it later."""
    io = ctx.io
    io.say("Carrying on without the sending server. Your mailbox is connected and read every")
    io.say("morning, but the morning summary cannot be e-mailed until the sending server works.")
    io.say("Your provider's help pages list it: search them for 'SMTP server'. To add it later,")
    io.say(f"run 'uv run tracker setup {StepName.MAILBOX}' again: it asks for the app password")
    io.say("once more (make a new one if you no longer have it), then for the sending server.")
    io.say(f"If your daily run is on GitHub, run 'uv run tracker setup {StepName.GITHUB}' after")
    io.say("that, so the run there is told the sending server too.")


def _ask_sending_server(ctx: SetupContext, account: ImapAccount) -> SmtpAccount:
    """Ask the sending server and its port, offering what is saved or likely."""
    host = ctx.ask_until_valid(
        lambda: ctx.io.ask(
            "Your provider's SMTP server, such as smtp.example.com",
            default=ctx.env.get(SMTP_HOST) or _likely_smtp_host(account.host),
        ),
        values.server_name,
    )
    port = ctx.ask_until_valid(
        lambda: ctx.io.ask(
            "Its port (465 or 587)", default=ctx.env.get(SMTP_PORT) or str(SMTP_TLS_PORT)
        ),
        values.port_number,
    )
    return SmtpAccount(host, port, account.username, account.label, account.company)


def _likely_smtp_host(imap_host: str) -> str | None:
    """Guess ``smtp.example.com`` from ``imap.example.com``; nothing otherwise."""
    if not imap_host.startswith(_IMAP_HOST_PREFIX):
        return None
    return _SMTP_HOST_PREFIX + imap_host.removeprefix(_IMAP_HOST_PREFIX)


def _summary_goes_by_smtp(ctx: SetupContext) -> bool:
    """Whether the summary is sent by SMTP: the default once an IMAP mailbox is read."""
    return summary_route(ctx) is DeliveryRoute.SMTP


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
    ctx.detail(f"Your own replies are read from the folder '{survey.sent_folder}'.")


def _save_account(ctx: SetupContext, provider: ImapProvider, account: ImapAccount) -> None:
    """Write the provider, the sign-in name and, for another provider, the server."""
    ctx.env.set(IMAP_PROVIDER, provider.value)
    ctx.env.set(IMAP_USERNAME, account.username)
    if provider is ImapProvider.CUSTOM:
        ctx.env.set(IMAP_HOST, account.host)
        ctx.env.set(IMAP_PORT, str(account.port))
    else:
        # A server left from another provider would win over the built-in one.
        for name in (IMAP_HOST, IMAP_PORT, SMTP_HOST, SMTP_PORT):
            if ctx.env.get(name) is not None:
                ctx.env.set(name, "")
    ctx.detail(f"Saved {IMAP_PROVIDER} and {IMAP_USERNAME} in .env.")


def _forget_sending_server(ctx: SetupContext) -> None:
    """Blank a sending server saved for an earlier mailbox.

    Left in place, every morning's summary would sign in to the old
    mailbox's server with this mailbox's name and app password.
    """
    for name in (SMTP_HOST, SMTP_PORT):
        if ctx.env.get(name) is not None:
            ctx.env.set(name, "")


def _save_sending_server(ctx: SetupContext, sending: SmtpAccount) -> None:
    """Write the sending server that was signed in to."""
    ctx.env.set(SMTP_HOST, sending.host)
    ctx.env.set(SMTP_PORT, str(sending.port))
    ctx.io.say(f"Saved {SMTP_HOST} and {SMTP_PORT} in .env.")


async def _save_sources(ctx: SetupContext) -> None:
    """Add the IMAP mailbox, asking whether Outlook stays read too."""
    saved = saved_sources(ctx)
    had_outlook = (
        MailSource.OUTLOOK in saved
        if saved is not None
        else await ctx.gateways.microsoft.is_signed_in(microsoft_access(ctx))
    )
    keep = had_outlook and (
        ctx.session.express
        or ctx.io.confirm("Keep reading your Outlook mailbox and calendar as well?", default=True)
    )
    save_sources(ctx, (MailSource.OUTLOOK, MailSource.IMAP) if keep else (MailSource.IMAP,))


def _choice(raw: str) -> MailSource | ImapProvider:
    """Read the answer to "which mailbox"."""
    choice = _CHOICES.get(raw.strip().lower())
    if choice is None:
        message = "please answer gmail, outlook, icloud, yahoo, fastmail or other"
        raise ValidationFailedError(message)
    return choice
