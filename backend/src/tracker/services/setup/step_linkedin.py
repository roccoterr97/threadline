"""Step 6: LinkedIn, optional and only for members in the EEA or Switzerland.

A first connection is walked through three stages, each on the page it
happens on: create the application, add the product, then connect the
application to Threadline. That last stage adds Threadline's address on this
computer to the application once; from then on the set-up opens LinkedIn's
"Allow" page, catches LinkedIn's answer itself and saves the key with its
expiry date, so a renewal is one command and one click.

Making the key by hand on LinkedIn's token page stays available whenever the
one-click way does not work.
"""

from __future__ import annotations

from datetime import date
from typing import Final

from pydantic import SecretStr

from tracker.domain.linkedin_sign_in import LinkedInApp, LinkedInGrant, SignInProblem
from tracker.services.setup import values
from tracker.services.setup.context import MAX_ATTEMPTS, SetupContext
from tracker.services.setup.github_values import offer_to_send
from tracker.services.setup.models import StepName
from tracker.services.setup.step_mailbox import store_access
from tracker.services.summary.wording import format_day
from tracker.shared.constants.linkedin_sign_in import CLIENT_ID_SETTING, REDIRECT_URL
from tracker.shared.constants.setup import (
    LINKEDIN_DEFAULT_COMPANY,
    LINKEDIN_DEVELOPER_APPS_PAGE,
    LINKEDIN_GUIDE_SECTION,
    LINKEDIN_NEW_APP_PAGE,
    LINKEDIN_PERMISSION_PREFIX,
    LINKEDIN_PRODUCT,
    LINKEDIN_TOKEN_GENERATOR_PAGE,
)
from tracker.shared.errors import (
    ConfigurationError,
    DatabaseStructureMissingError,
    DatabaseUnavailableError,
    LinkedInSignInError,
    SourceUnavailableError,
    ValidationFailedError,
)
from tracker.shared.logging import get_logger

TOKEN: Final[str] = "LINKEDIN_ACCESS_TOKEN"
EXPIRES_ON: Final[str] = "LINKEDIN_TOKEN_EXPIRES_ON"
PROFILE: Final[str] = "OWNER_LINKEDIN_PROFILE_URL"

_INTRODUCTION: Final[tuple[str, ...]] = (
    "LinkedIn is optional. It works only if your LinkedIn profile is located in the",
    "European Economic Area or Switzerland (the location on your profile, not your citizenship).",
    "LinkedIn's copy of your messages runs one to two days behind, so LinkedIn",
    "messages reach Threadline a day or two late.",
    f"The first time takes about ten minutes, in three stages; {LINKEDIN_GUIDE_SECTION}",
    "shows every click. After that, a new key takes one command and one click.",
)

_CREATE_APPLICATION: Final[tuple[str, ...]] = (
    "",
    "Stage 1 of 3 - create a developer application (guide, part 8a, stage 1).",
    "On the LinkedIn page that opens, fill in 'App name' with any name, such as Threadline.",
    f"For 'LinkedIn Page', type 'Member Data Portability' and choose '{LINKEDIN_DEFAULT_COMPANY}'",
    "- do not create a new page. If it asks for an 'App logo', upload any small picture.",
    "Tick the terms and click 'Create app'.",
    f"(Made one on an earlier try? Open it from {LINKEDIN_DEVELOPER_APPS_PAGE} instead.)",
)

_ADD_PRODUCT: Final[tuple[str, ...]] = (
    "",
    "Stage 2 of 3 - add the product (guide, part 8a, stage 2).",
    "Stay on your application's page. Open its 'Products' tab, find",
    f"'{LINKEDIN_PRODUCT}' and click 'Request access'. Accept the terms.",
    "If LinkedIn says the product is not available to you, answer no below.",
)

_PRODUCT_UNAVAILABLE: Final[str] = (
    "Skipped: LinkedIn offers this only to profiles located in the EEA or "
    "Switzerland, so Threadline carries on without LinkedIn."
)

_FIRST_CONNECTION: Final[str] = (
    "Stage 3 of 3 - connect the application to Threadline (guide, part 8a, stage 3)."
)

_ADD_ADDRESS: Final[tuple[str, ...]] = (
    "Open the application's 'Auth' tab. Under 'OAuth 2.0 settings', click the pencil next",
    "to 'Authorized redirect URLs for your app', click '+ Add redirect URL', paste this",
    "address exactly, and click 'Update':",
    f"  {REDIRECT_URL}",
)

_COPY_CREDENTIALS: Final[tuple[str, ...]] = (
    "At the top of the same tab, under 'Application credentials', copy the 'Client ID',",
    "then the 'Primary Client Secret' (click the eye icon to show it).",
)

_ALLOW: Final[tuple[str, ...]] = (
    "",
    "LinkedIn's page opens next and asks to let your application read your data:",
    "click 'Allow', then come back here. If you are already signed in to LinkedIn,",
    "it may not even ask.",
)

_RENEWAL: Final[str] = "A LinkedIn key is already saved, so this makes a new one to replace it."

_OFFER_ONE_CLICK: Final[tuple[str, ...]] = (
    "From now on a new key can take one click, once your application knows Threadline's",
    "address on this computer. Setting that up takes about two minutes, once.",
)

_CONNECT_LATER: Final[str] = "Connect the application to Threadline (guide, part 8a, stage 3)."

_MAKE_KEY: Final[tuple[str, ...]] = (
    "",
    "Making the key by hand (guide, part 8a, 'Making the key by hand').",
    "On the LinkedIn page that opens, pick your application, tick the permission whose",
    f"name starts with {LINKEDIN_PERMISSION_PREFIX}, click 'Request access token', then 'Allow'.",
    "Copy the token LinkedIn shows - it is shown only once - and paste it here.",
)

_FIND_EXPIRY: Final[tuple[str, ...]] = (
    "",
    "Now the day the key expires. At the top of the same LinkedIn page, open",
    "'Docs and tools' > 'OAuth Token Tools' and choose the Token Inspector. Pick your",
    "application, paste the token and click 'Inspect': it shows when the key expires.",
    "The morning summary reminds you before that day.",
)

_EXPIRY_QUESTION: Final[str] = "Expiry date (YYYY-MM-DD, or with the month's name: 24 Sep 2027)"
_KEEP_WAITING: Final[str] = "No answer from LinkedIn yet. Keep waiting?"
_SECRET_PROMPT: Final[str] = "Client Secret (it stays hidden)"
_SECRET_AGAIN_PROMPT: Final[str] = "Client Secret (it stays hidden; Enter keeps the one you typed)"
_TRY_LATER: Final[str] = "Skipped. Run 'uv run tracker setup linkedin' to try again."

_ONE_CLICK_NOT_SET_UP: Final[tuple[str, ...]] = (
    "The key is saved, but the Client Secret could not be saved in your Supabase database,",
    "so one-click renewal is not set up. To set it up, run 'uv run tracker setup linkedin'",
    "again later; it asks for the Client ID and Client Secret once more.",
)

#: Why the Client Secret could not be kept: the database, or its settings in ``.env``.
_STORE_ERRORS: Final = (
    DatabaseUnavailableError,
    DatabaseStructureMissingError,
    ConfigurationError,
    ValidationFailedError,
)

_log = get_logger(__name__)


class LinkedInStep:
    """Connects LinkedIn once, then renews its key with one click."""

    name = StepName.LINKEDIN
    title = "LinkedIn (optional)"

    async def is_done(self, ctx: SetupContext) -> bool:
        """Done when a key and its expiry date are saved."""
        return bool(ctx.env.get(TOKEN) and ctx.env.get(EXPIRES_ON))

    async def run(self, ctx: SetupContext) -> None:
        """Prepare a first connection, or go straight to a new key for a renewal."""
        if ctx.env.get(TOKEN):
            ctx.io.say(_RENEWAL)
            app = await _saved_app(ctx)
        elif _prepare_first_connection(ctx):
            ctx.io.say("")
            ctx.io.say(_FIRST_CONNECTION)
            app = _connect_application(ctx)
        else:
            return
        if app is None:
            await _make_key_by_hand(ctx, None)
            return
        app, grant = await _sign_in(ctx, app)
        if grant is None:
            await _offer_key_by_hand(ctx, app)
            return
        await _save_signed_in(ctx, app, grant)


def _prepare_first_connection(ctx: SetupContext) -> bool:
    """Create the application and add the product, each on its own page.

    Returns:
        Whether LinkedIn is ready for the application to be connected. ``False``
        when the person skipped LinkedIn or LinkedIn does not offer them the product.
    """
    io = ctx.io
    _say(ctx, _INTRODUCTION)
    if not io.confirm("Connect LinkedIn now?", default=False):
        io.say("Skipped. Run 'uv run tracker setup linkedin' whenever you want it.")
        return False
    _say(ctx, _CREATE_APPLICATION)
    io.open_page(LINKEDIN_NEW_APP_PAGE)
    io.pause("Once your application's own page is open")
    # No page is opened here: the Products tab has no address of its own, and
    # the application's page is already open from the stage before.
    _say(ctx, _ADD_PRODUCT)
    if not io.confirm("Did LinkedIn let you request access?", default=True):
        io.say(_PRODUCT_UNAVAILABLE)
        return False
    return True


async def _saved_app(ctx: SetupContext) -> LinkedInApp | None:
    """The application saved by an earlier connection, or one connected now.

    Returns:
        The application, or ``None`` when the person keeps making keys by hand.
    """
    client_id = ctx.env.get(CLIENT_ID_SETTING)
    secret = None
    if client_id is not None:
        secret = await ctx.gateways.linkedin.saved_client_secret(store_access(ctx))
    if client_id is not None and secret is not None:
        return LinkedInApp(client_id, secret)
    _say(ctx, _OFFER_ONE_CLICK)
    if not ctx.io.confirm("Set that up now?", default=True):
        return None
    ctx.io.say("")
    ctx.io.say(_CONNECT_LATER)
    return _connect_application(ctx)


def _connect_application(ctx: SetupContext) -> LinkedInApp:
    """Add Threadline's address on the Auth tab, then ask for the application's two values."""
    io = ctx.io
    _say(ctx, _ADD_ADDRESS)
    if io.copy(REDIRECT_URL):
        io.say("(It is already on your clipboard.)")
    io.pause("Once the address is saved")
    return _ask_app(ctx, None)


def _ask_app(ctx: SetupContext, previous: LinkedInApp | None) -> LinkedInApp:
    """Ask for the Client ID and the Client Secret from the Auth tab.

    Args:
        ctx: The set-up's context.
        previous: What was typed on an earlier try; Enter keeps each value.

    Returns:
        The application.
    """
    io = ctx.io
    _say(ctx, _COPY_CREDENTIALS)
    client_id = ctx.ask_until_valid(
        lambda: io.ask("Client ID", default=previous.client_id if previous else None),
        values.linkedin_client_id,
    )
    if previous is None:
        secret = ctx.ask_until_valid(
            lambda: io.ask_secret(_SECRET_PROMPT),
            lambda raw: values.non_empty(raw, "the Client Secret"),
        )
        return LinkedInApp(client_id, SecretStr(secret))
    typed = io.ask_secret(_SECRET_AGAIN_PROMPT).strip()
    return LinkedInApp(client_id, SecretStr(typed) if typed else previous.client_secret)


async def _sign_in(ctx: SetupContext, app: LinkedInApp) -> tuple[LinkedInApp, LinkedInGrant | None]:
    """Open LinkedIn's "Allow" page and wait for the key, trying again when asked.

    Returns:
        The application as last typed, and the key, or ``None`` instead of the
        key when every try failed or the person stopped trying.
    """
    io = ctx.io
    for attempt in range(1, MAX_ATTEMPTS + 1):
        _say(ctx, _ALLOW)
        try:
            grant = await ctx.gateways.linkedin.sign_in(
                app, io.open_page, lambda: io.confirm(_KEEP_WAITING, default=True)
            )
        except (LinkedInSignInError, SourceUnavailableError) as error:
            io.say(f"  {error.message}.")
            if attempt == MAX_ATTEMPTS or not io.confirm("Try again?", default=True):
                break
            if _needs_app_details_again(error):
                app = _ask_app(ctx, app)
        else:
            return app, grant
    return app, None


def _needs_app_details_again(error: LinkedInSignInError | SourceUnavailableError) -> bool:
    """Whether the error points at the Client ID, the Client Secret or the address."""
    if not isinstance(error, LinkedInSignInError):
        return False
    return SignInProblem(error.problem).needs_app_details_again


async def _save_signed_in(ctx: SetupContext, app: LinkedInApp, grant: LinkedInGrant) -> None:
    """Check the new key live, save it and its expiry, then keep the application.

    LinkedIn's one-time code is spent by now, so the key is written before
    anything that may still fail; losing it would mean signing in again.
    """
    expires = await _expiry_of_new_key(ctx, app, grant)
    await _check_new_key(ctx, grant)
    changed = _saved(ctx, TOKEN, grant.access_token.get_secret_value())
    if expires is None:
        expires = _ask_expiry(ctx)
    changed += _saved(ctx, EXPIRES_ON, expires.isoformat())
    await _keep_app_for_renewals(ctx, app)
    _ask_profile_and_offer(ctx, changed)


async def _check_new_key(ctx: SetupContext, grant: LinkedInGrant) -> None:
    """Try the key LinkedIn just made; an outage does not throw it away.

    LinkedIn issued the key moments ago, so a failed connection says nothing
    about the key, and its one-time code cannot be used again. A refusal still
    stops the step, so a key LinkedIn will not read is never saved.
    """
    try:
        await ctx.gateways.check_linkedin(grant.access_token)
    except SourceUnavailableError:
        _log.warning("linkedin_new_key_unchecked")
        ctx.io.say(
            "LinkedIn could not be reached to try the new key; it is saved anyway, "
            "and the next morning run uses it."
        )
        return
    ctx.io.say("LinkedIn accepted the key.")


async def _expiry_of_new_key(
    ctx: SetupContext, app: LinkedInApp, grant: LinkedInGrant
) -> date | None:
    """Read when the new key stops working from LinkedIn, and say it.

    Returns:
        The day, or ``None`` when LinkedIn did not say; the person is asked
        once the key is saved.
    """
    moment = grant.expires_at
    if moment is None:
        try:
            moment = await ctx.gateways.linkedin.expiry_of(app, grant.access_token)
        except (LinkedInSignInError, SourceUnavailableError) as error:
            _log.warning("linkedin_new_key_expiry_unread", error_type=type(error).__name__)
    if moment is None:
        ctx.io.say("LinkedIn made a new key but did not say when it expires.")
        return None
    expires = moment.date()
    ctx.io.say(f"LinkedIn made a new key. It works until {format_day(expires)}.")
    return expires


async def _keep_app_for_renewals(ctx: SetupContext, app: LinkedInApp) -> None:
    """Save the application, so the next key takes one click; say so plainly when that fails."""
    _replace(ctx, CLIENT_ID_SETTING, app.client_id)
    try:
        await ctx.gateways.linkedin.save_client_secret(store_access(ctx), app.client_secret)
    except _STORE_ERRORS as error:
        _log.warning("linkedin_client_secret_not_saved", error_type=type(error).__name__)
        _say(ctx, _ONE_CLICK_NOT_SET_UP)
        return
    ctx.io.say("Saved the Client Secret, encrypted, in your Supabase database.")


async def _offer_key_by_hand(ctx: SetupContext, app: LinkedInApp) -> None:
    """Offer the by-hand way after the one-click way did not work."""
    if not ctx.io.confirm("Make the key by hand on LinkedIn's token page instead?", default=True):
        ctx.io.say(_TRY_LATER)
        return
    await _make_key_by_hand(ctx, app)


async def _make_key_by_hand(ctx: SetupContext, app: LinkedInApp | None) -> None:
    """Open LinkedIn's token page, check the pasted key live, then save it.

    Args:
        ctx: The set-up's context.
        app: The application, when known: LinkedIn then tells the expiry date.
    """
    io = ctx.io
    _say(ctx, _MAKE_KEY)
    io.open_page(LINKEDIN_TOKEN_GENERATOR_PAGE)
    token = await ctx.ask_until_accepted(
        lambda: io.ask_secret("LinkedIn access token (it stays hidden)"),
        lambda raw: _check_token(ctx, raw),
    )
    io.say("LinkedIn accepted the key.")
    expires = await _expiry_of_pasted_key(ctx, app, SecretStr(token))
    await _save_key(ctx, token, expires)


async def _expiry_of_pasted_key(
    ctx: SetupContext, app: LinkedInApp | None, token: SecretStr
) -> date:
    """Ask LinkedIn for the expiry when the application is known, else ask the person."""
    if app is not None:
        try:
            moment = await ctx.gateways.linkedin.expiry_of(app, token)
        except (LinkedInSignInError, SourceUnavailableError):
            moment = None
        if moment is not None:
            ctx.io.say(f"LinkedIn says this key works until {format_day(moment.date())}.")
            return moment.date()
    _say(ctx, _FIND_EXPIRY)
    return _ask_expiry(ctx)


async def _save_key(ctx: SetupContext, token: str, expires: date) -> None:
    """Save the key and its date, ask for the profile the first time, and offer GitHub."""
    changed = _saved(ctx, TOKEN, token) + _saved(ctx, EXPIRES_ON, expires.isoformat())
    _ask_profile_and_offer(ctx, changed)


def _ask_profile_and_offer(ctx: SetupContext, changed: list[str]) -> None:
    """Ask for the profile the first time, then offer to send what changed to GitHub."""
    if ctx.env.get(PROFILE) is None:
        profile = ctx.ask_until_valid(
            lambda: ctx.io.ask("Your LinkedIn profile address (https://www.linkedin.com/in/...)"),
            values.linkedin_profile,
        )
        changed = changed + _saved(ctx, PROFILE, profile)
    offer_to_send(ctx, changed)


def _saved(ctx: SetupContext, name: str, value: str) -> list[str]:
    """Save one value LinkedIn just proved; the name, when it changed, for GitHub."""
    return [name] if _replace(ctx, name, value) else []


def _replace(ctx: SetupContext, name: str, value: str) -> bool:
    """Save a value LinkedIn just proved, without asking first.

    The person asked for a new key and LinkedIn accepted it, so the old value is
    never the one to keep.

    Returns:
        Whether the value changed.
    """
    if ctx.env.get(name) == value:
        return False
    ctx.env.set(name, value)
    ctx.io.say(f"Saved {name} in .env.")
    return True


async def _check_token(ctx: SetupContext, raw: str) -> str:
    """Make one small LinkedIn call with the key."""
    token = values.non_empty(raw, "the access token")
    await ctx.gateways.check_linkedin(SecretStr(token))
    return token


def _ask_expiry(ctx: SetupContext) -> date:
    """Ask for the day the key expires."""
    today = ctx.gateways.clock.now().date()
    return ctx.ask_until_valid(
        lambda: ctx.io.ask(_EXPIRY_QUESTION),
        lambda raw: values.future_date(raw, today),
    )


def _say(ctx: SetupContext, lines: tuple[str, ...]) -> None:
    """Show several lines, one after the other."""
    for line in lines:
        ctx.io.say(line)
