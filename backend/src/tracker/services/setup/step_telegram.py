"""Step: Telegram, optional, read-only.

Telegram expects every program that reads an account to have its own small
"application", so the owner makes one at my.telegram.org (the step says every
click) and pastes its two values. Then the step logs in once, here: the phone
number, the code Telegram sends to the owner's Telegram app, and the two-step
verification password when the account has one. The password is used for that
login only and never saved. What the login leaves (the saved session) is full
access to the account, so it is kept like the other secrets: in ``.env`` and in
the repository's Actions secrets, never shown.

Nothing else is asked: the values are saved and sent to GitHub straight away,
since the daily run there cannot read Telegram without them.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Final

from pydantic import SecretStr

from tracker.domain.telegram import TelegramApp, TelegramLogin, TelegramLoginProblem
from tracker.services.setup import values
from tracker.services.setup.context import MAX_ATTEMPTS, SetupContext
from tracker.services.setup.github_values import offer_to_send
from tracker.services.setup.models import StepName
from tracker.services.setup.skipped_steps import remember_skip, skipped_earlier
from tracker.services.setup.telegram_login import TelegramLoginFlow
from tracker.shared.constants.telegram import (
    TELEGRAM_APP_SHORT_NAME,
    TELEGRAM_APP_TITLE,
    TELEGRAM_APPS_PAGE,
    TELEGRAM_GUIDE_SECTION,
)
from tracker.shared.errors import TelegramLoginError, ValidationFailedError

API_ID: Final[str] = "TELEGRAM_API_ID"
API_HASH: Final[str] = "TELEGRAM_API_HASH"
SESSION: Final[str] = "TELEGRAM_SESSION"

#: The one question a run of every extra asks; asked for by name, it is not asked.
TELEGRAM_OFFER: Final[str] = "Connect Telegram now?"

_WHAT_IT_DOES: Final[tuple[str, ...]] = (
    "Threadline can read your one-to-one Telegram chats with people (not groups,",
    "channels or bots). It only reads: it never sends and never marks anything as read.",
    "It takes about three minutes: you make your own small Telegram app on Telegram's",
    f"website, then log in once here. {TELEGRAM_GUIDE_SECTION} shows every click.",
)

_MAKE_APP: Final[tuple[str, ...]] = (
    "",
    "On the page that opens (my.telegram.org):",
    "  1. Type your phone number with its country code, such as +39 333 123 4567,",
    "     and click 'Next'.",
    "  2. Telegram sends a code to your Telegram app (a message from 'Telegram').",
    "     Type it on the page and click 'Sign In'.",
    "  3. Click 'API development tools'.",
    f"  4. Fill in App title: {TELEGRAM_APP_TITLE}, Short name: {TELEGRAM_APP_SHORT_NAME},",
    "     Platform: Desktop. Leave the rest as it is and click 'Create application'.",
    "     If the page only says 'ERROR', wait a minute and click it again; if it keeps",
    "     saying it, switch off any VPN or ad blocker, or try another browser.",
    "  5. Copy 'App api_id' and 'App api_hash' and paste them here.",
)

_APP_AGAIN: Final[str] = "Copy both again from my.telegram.org > 'API development tools'."
_SAVED_APP: Final[str] = "Using the api_id and api_hash saved earlier."
_PHONE_PROMPT: Final[str] = "Your phone number for Telegram, with its country code"
_CODE_SENT: Final[str] = (
    "Telegram sent a login code to your Telegram app (a message from 'Telegram'), or by SMS."
)
_CODE_PROMPT: Final[str] = "The code"
_PASSWORD_NEEDED: Final[str] = (
    "Your account has a two-step verification password. It is used for this login only "
    "and never saved."
)
_PASSWORD_PROMPT: Final[str] = "Your Telegram password (it stays hidden)"
_DEVICES: Final[tuple[str, ...]] = (
    "Telegram now shows a 'new login' message in your app: that is Threadline.",
    "You can end it at any time in Telegram > Settings > Devices.",
)


class TelegramStep:
    """Makes the owner's Telegram application, logs in once and saves the login."""

    name = StepName.TELEGRAM
    title = "Telegram (optional)"

    async def is_done(self, ctx: SetupContext) -> bool:
        """Done when the application's values and a saved login are all in ``.env``."""
        return all(ctx.env.get(name) for name in (API_ID, API_HASH, SESSION))

    async def run(self, ctx: SetupContext) -> None:
        """Make the application if needed, log in, then save and send to GitHub."""
        if not _wanted(ctx):
            return
        app = _saved_app(ctx) or _make_app(ctx)
        app, login = await _log_in(ctx, app)
        _save(ctx, app, login)


def _wanted(ctx: SetupContext) -> bool:
    """Whether to connect Telegram now: asked once in a run of every extra, never by name."""
    io = ctx.io
    if ctx.session.named_step == StepName.TELEGRAM:
        _say(ctx, _WHAT_IT_DOES)
        return True
    if skipped_earlier(ctx, StepName.TELEGRAM, "To add it"):
        return False
    _say(ctx, _WHAT_IT_DOES)
    if io.confirm(TELEGRAM_OFFER, default=False):
        return True
    remember_skip(ctx, StepName.TELEGRAM)
    io.say(f"Skipped. Run 'uv run tracker setup {StepName.TELEGRAM}' whenever you want it.")
    return False


def _saved_app(ctx: SetupContext) -> TelegramApp | None:
    """The application saved by an earlier login, so a new login needs no new one."""
    raw_id = ctx.env.get(API_ID)
    raw_hash = ctx.env.get(API_HASH)
    if raw_id is None or raw_hash is None:
        return None
    try:
        app = TelegramApp(
            values.telegram_api_id(raw_id), SecretStr(values.telegram_api_hash(raw_hash))
        )
    except ValidationFailedError:
        return None
    ctx.io.say(_SAVED_APP)
    return app


def _make_app(ctx: SetupContext) -> TelegramApp:
    """Say how to make the application on my.telegram.org, then take its two values."""
    _say(ctx, _MAKE_APP)
    ctx.io.open_page(TELEGRAM_APPS_PAGE)
    return _ask_app(ctx)


def _ask_app(ctx: SetupContext) -> TelegramApp:
    """Ask for the application's api_id, then its api_hash, hidden."""
    io = ctx.io
    api_id = ctx.ask_until_valid(lambda: io.ask("App api_id"), values.telegram_api_id)
    api_hash = ctx.ask_until_valid(
        lambda: io.ask_secret("App api_hash (it stays hidden)"), values.telegram_api_hash
    )
    return TelegramApp(api_id, SecretStr(api_hash))


async def _log_in(ctx: SetupContext, app: TelegramApp) -> tuple[TelegramApp, TelegramLogin]:
    """Log in, asking for the application's values again when Telegram refuses them.

    Returns:
        The application Telegram accepted, and the finished login.

    Raises:
        TelegramLoginError: If Telegram refused something every time it was typed.
        SourceUnavailableError: If Telegram could not be reached.
    """
    phone = ctx.ask_until_valid(lambda: ctx.io.ask(_PHONE_PROMPT), values.phone_number)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return app, await _log_in_once(ctx, app, phone)
        except TelegramLoginError as error:
            if error.problem != TelegramLoginProblem.APP_REFUSED or attempt == MAX_ATTEMPTS:
                raise
            ctx.io.say(f"  {error.message}. {_APP_AGAIN}")
            ctx.io.open_page(TELEGRAM_APPS_PAGE)
            app = _ask_app(ctx)
    message = "no attempt was made"  # pragma: no cover - MAX_ATTEMPTS >= 1
    raise ValidationFailedError(message)  # pragma: no cover


async def _log_in_once(ctx: SetupContext, app: TelegramApp, phone: str) -> TelegramLogin:
    """Send the code, take it, take the password when the account has one, and finish."""
    io = ctx.io
    async with ctx.gateways.telegram.open(app) as flow:
        await _until_accepted(
            ctx, lambda: phone, flow.send_code, TelegramLoginProblem.PHONE_REFUSED, _new_phone(ctx)
        )
        io.say(_CODE_SENT)
        needs_password = await _until_accepted(
            ctx, lambda: io.ask(_CODE_PROMPT), _code_entry(flow), TelegramLoginProblem.CODE_WRONG
        )
        if needs_password:
            io.say(_PASSWORD_NEEDED)
            await _until_accepted(
                ctx,
                lambda: io.ask_secret(_PASSWORD_PROMPT),
                _password_entry(flow),
                TelegramLoginProblem.PASSWORD_WRONG,
            )
        return await flow.finish()


def _new_phone(ctx: SetupContext) -> Callable[[], str]:
    """Ask for the phone number again, after Telegram refused the one typed."""
    return lambda: ctx.ask_until_valid(lambda: ctx.io.ask(_PHONE_PROMPT), values.phone_number)


def _code_entry(flow: TelegramLoginFlow) -> Callable[[str], Awaitable[bool]]:
    """Hand a typed code to the login, refusing an empty one before Telegram sees it."""

    async def enter(raw: str) -> bool:
        return await flow.enter_code(values.non_empty(raw, "the code"))

    return enter


def _password_entry(flow: TelegramLoginFlow) -> Callable[[str], Awaitable[None]]:
    """Hand a typed password to the login, wrapped so it is never shown."""

    async def enter(raw: str) -> None:
        await flow.enter_password(SecretStr(values.non_empty(raw, "the password")))

    return enter


async def _until_accepted[T](
    ctx: SetupContext,
    ask: Callable[[], str],
    act: Callable[[str], Awaitable[T]],
    problem: TelegramLoginProblem,
    ask_again: Callable[[], str] | None = None,
) -> T:
    """Hand an answer to Telegram, asking again a few times while it says ``problem``.

    Any other refusal is not something typing again can fix, so it stops the step.

    Args:
        ctx: The set-up's context.
        ask: Asks the question the first time.
        act: Hands the answer to Telegram.
        problem: The refusal that asking again can fix.
        ask_again: Asks the question after a refusal; ``ask`` when not given.

    Returns:
        What Telegram's answer came to.

    Raises:
        TelegramLoginError: If Telegram refused it every time, or for another reason.
        ValidationFailedError: If the answer was empty every time.
    """
    answer = ask()
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return await act(answer)
        except (TelegramLoginError, ValidationFailedError) as error:
            refused = isinstance(error, TelegramLoginError) and error.problem != problem
            if refused or attempt == MAX_ATTEMPTS:
                raise
            ctx.io.say(f"  {error.message}. Please try again.")
            answer = (ask_again or ask)()
    message = "no attempt was made"  # pragma: no cover - MAX_ATTEMPTS >= 1
    raise ValidationFailedError(message)  # pragma: no cover


def _save(ctx: SetupContext, app: TelegramApp, login: TelegramLogin) -> None:
    """Save the application and the login, say how to end it, and send them to GitHub."""
    io = ctx.io
    io.say(f"Logged in to Telegram as {login.account_name}.")
    changed = [
        name
        for name, value in (
            (API_ID, str(app.api_id)),
            (API_HASH, app.api_hash.get_secret_value()),
            (SESSION, login.session.get_secret_value()),
        )
        if _replace(ctx, name, value)
    ]
    _say(ctx, _DEVICES)
    offer_to_send(ctx, changed, ask_first=False)


def _replace(ctx: SetupContext, name: str, value: str) -> bool:
    """Save a value Telegram just accepted, without asking first; never show it.

    Returns:
        Whether the value changed.
    """
    if ctx.env.get(name) == value:
        return False
    ctx.env.set(name, value)
    ctx.io.say(f"Saved {name} in .env.")
    return True


def _say(ctx: SetupContext, lines: tuple[str, ...]) -> None:
    """Show several lines, one after the other."""
    for line in lines:
        ctx.io.say(line)
