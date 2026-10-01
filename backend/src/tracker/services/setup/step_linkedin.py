"""Step 6: LinkedIn, optional and only for members in the EEA or Switzerland.

LinkedIn offers no sign-in button for this, so the key is made by hand on its
developer pages. A first connection is walked through three stages, each on
the page it happens on: create the application, add the product, make the key.
Once a key is saved the step is a renewal and goes straight to the last stage.
"""

from __future__ import annotations

from datetime import date
from typing import Final

from pydantic import SecretStr

from tracker.services.setup import values
from tracker.services.setup.context import SetupContext
from tracker.services.setup.models import StepName
from tracker.shared.constants.setup import (
    LINKEDIN_DEFAULT_COMPANY,
    LINKEDIN_DEVELOPER_APPS_PAGE,
    LINKEDIN_GUIDE_SECTION,
    LINKEDIN_PERMISSION_PREFIX,
    LINKEDIN_PRODUCT,
    LINKEDIN_TOKEN_GENERATOR_PAGE,
)

TOKEN: Final[str] = "LINKEDIN_ACCESS_TOKEN"
EXPIRES_ON: Final[str] = "LINKEDIN_TOKEN_EXPIRES_ON"
PROFILE: Final[str] = "OWNER_LINKEDIN_PROFILE_URL"

_INTRODUCTION: Final[tuple[str, ...]] = (
    "LinkedIn is optional, and the least friendly step: LinkedIn has no sign-in",
    "button for this, so you make a key by hand on its developer pages.",
    "It works only if your LinkedIn profile is located in the European Economic",
    "Area or Switzerland (the location on your profile, not your citizenship).",
    "LinkedIn's copy of your messages runs one to two days behind, so LinkedIn",
    "messages reach Threadline a day or two late.",
    f"It takes about ten minutes, in three stages; {LINKEDIN_GUIDE_SECTION} shows every click.",
)

_CREATE_APPLICATION: Final[tuple[str, ...]] = (
    "",
    "Stage 1 of 3 - create a developer application (guide, part 6a).",
    "On the LinkedIn page that opens, click 'Create app' and give it any name, such as",
    f"Threadline. For 'LinkedIn Page', choose '{LINKEDIN_DEFAULT_COMPANY}' -",
    "do not create a new page. Then tick the terms and click 'Create app'.",
    "(Made one on an earlier try? Open it instead.)",
)

_ADD_PRODUCT: Final[tuple[str, ...]] = (
    "",
    "Stage 2 of 3 - add the product (guide, part 6b).",
    "Stay on your application's page. Open its 'Products' tab, find",
    f"'{LINKEDIN_PRODUCT}' and click 'Request access'. Accept the terms.",
    "If LinkedIn says the product is not available to you, answer no below.",
)

_PRODUCT_UNAVAILABLE: Final[str] = (
    "Skipped: LinkedIn offers this only to profiles located in the EEA or "
    "Switzerland, so Threadline carries on without LinkedIn."
)

_RENEWAL: Final[tuple[str, ...]] = (
    "A LinkedIn key is already saved, so this is a renewal: you make a new key",
    "and it replaces the old one (guide, part 6c).",
)

_FIRST_KEY: Final[tuple[str, ...]] = ("", "Stage 3 of 3 - make the key (guide, part 6c).")

_MAKE_KEY: Final[tuple[str, ...]] = (
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


class LinkedInStep:
    """Walks through LinkedIn's developer pages and saves a key LinkedIn accepted."""

    name = StepName.LINKEDIN
    title = "LinkedIn (optional)"

    async def is_done(self, ctx: SetupContext) -> bool:
        """Done when a key and its expiry date are saved."""
        return bool(ctx.env.get(TOKEN) and ctx.env.get(EXPIRES_ON))

    async def run(self, ctx: SetupContext) -> None:
        """Prepare a first connection, or go straight to a new key for a renewal."""
        if ctx.env.get(TOKEN):
            _say(ctx, _RENEWAL)
        elif _prepare_first_connection(ctx):
            _say(ctx, _FIRST_KEY)
        else:
            return
        await _make_and_save_key(ctx)


def _prepare_first_connection(ctx: SetupContext) -> bool:
    """Create the application and add the product, each on its own page.

    Returns:
        Whether LinkedIn is ready for a key to be made. ``False`` when the
        person skipped LinkedIn or LinkedIn does not offer them the product.
    """
    io = ctx.io
    _say(ctx, _INTRODUCTION)
    if not io.confirm("Connect LinkedIn now?", default=False):
        io.say("Skipped. Run 'uv run tracker setup linkedin' whenever you want it.")
        return False
    _say(ctx, _CREATE_APPLICATION)
    io.open_page(LINKEDIN_DEVELOPER_APPS_PAGE)
    io.pause("Press Enter once your application's own page is open")
    # No page is opened here: the Products tab has no address of its own, and
    # the application's page is already open from the stage before.
    _say(ctx, _ADD_PRODUCT)
    if not io.confirm("Did LinkedIn let you request access?", default=True):
        io.say(_PRODUCT_UNAVAILABLE)
        return False
    return True


async def _make_and_save_key(ctx: SetupContext) -> None:
    """Open the page that makes a key, check the key live, then save it."""
    io = ctx.io
    _say(ctx, _MAKE_KEY)
    io.open_page(LINKEDIN_TOKEN_GENERATOR_PAGE)
    token = await ctx.ask_until_accepted(
        lambda: io.ask_secret("LinkedIn access token (it stays hidden)"),
        lambda raw: _check_token(ctx, raw),
    )
    io.say("LinkedIn accepted the key.")
    expires = _ask_expiry(ctx)
    profile = ctx.env.get(PROFILE) or ctx.ask_until_valid(
        lambda: io.ask("Your LinkedIn profile address (https://www.linkedin.com/in/...)"),
        values.linkedin_profile,
    )
    for name, value in ((TOKEN, token), (EXPIRES_ON, expires.isoformat()), (PROFILE, profile)):
        ctx.write(name, value)


async def _check_token(ctx: SetupContext, raw: str) -> str:
    """Make one small LinkedIn call with the key."""
    token = values.non_empty(raw, "the access token")
    await ctx.gateways.check_linkedin(SecretStr(token))
    return token


def _ask_expiry(ctx: SetupContext) -> date:
    """Say where LinkedIn shows the expiry date, then ask for it."""
    _say(ctx, _FIND_EXPIRY)
    today = ctx.gateways.clock.now().date()
    return ctx.ask_until_valid(
        lambda: ctx.io.ask(_EXPIRY_QUESTION),
        lambda raw: values.future_date(raw, today),
    )


def _say(ctx: SetupContext, lines: tuple[str, ...]) -> None:
    """Show several lines, one after the other."""
    for line in lines:
        ctx.io.say(line)
