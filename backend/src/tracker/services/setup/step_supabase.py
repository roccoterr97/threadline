"""Steps 1 and 2: the Supabase project and its keys, and the encryption key.

With one Supabase access token the step finds or creates the project and reads
its address and both keys itself; nothing is copied between screens. While a
new project starts, the step hands the wait to what the wizard gives it (a
full run asks for the mailbox then). Someone who prefers it can still type an
existing project's address and keys.
"""

from __future__ import annotations

import binascii
from collections.abc import Sequence
from typing import Final

from cryptography.fernet import Fernet
from pydantic import SecretStr

from tracker.services.setup import values
from tracker.services.setup.context import SetupContext
from tracker.services.setup.fresh_project import ask_until_it_answers
from tracker.services.setup.models import StepName
from tracker.services.setup.supabase_project import Meanwhile, find_or_create_project, read_keys
from tracker.services.setup.supabase_session import full_access_needed, require_supabase_token
from tracker.shared.constants.setup import (
    SUPABASE_API_KEYS_PAGE,
    SUPABASE_HOST_SUFFIX,
    SUPABASE_PROJECTS_PAGE,
)
from tracker.shared.errors import ValidationFailedError

URL: Final[str] = "SUPABASE_URL"
PUBLISHABLE_KEY: Final[str] = "SUPABASE_ANON_KEY"
SECRET_KEY: Final[str] = "SUPABASE_SERVICE_ROLE_KEY"
ENCRYPTION_KEY: Final[str] = "TOKEN_ENCRYPTION_KEY"

#: What the step needs from the owner, said before the Supabase page opens.
_ACCOUNT_NEEDED: Final[str] = (
    "Supabase keeps your data, in a free account; the set-up creates the project there."
)


class SupabaseStep:
    """Saves the project address and its two keys, once each is accepted live."""

    name = StepName.SUPABASE
    title = "Your Supabase project"

    def __init__(self, meanwhile: Sequence[Meanwhile] = ()) -> None:
        """Bind the step to what the owner may do while a new project starts.

        Args:
            meanwhile: Asked in order while a project that is not up yet
                starts, until it is up; none of it may need the database.
        """
        self._meanwhile = meanwhile

    async def is_done(self, ctx: SetupContext) -> bool:
        """Done when all three values are in ``.env``."""
        return all(ctx.env.get(name) for name in (URL, PUBLISHABLE_KEY, SECRET_KEY))

    async def run(self, ctx: SetupContext) -> None:
        """Keep the saved project, or find or create one with the token, or take typed values."""
        io = ctx.io
        ctx.detail("Supabase is the database that keeps your people and conversations.")
        replacing = await self.is_done(ctx)
        if replacing and _keep_saved_project(ctx):
            return
        io.say(_ACCOUNT_NEEDED)
        if ctx.session.express or io.confirm(
            "Create the project (or pick an existing one) for you?", default=True
        ):
            url, publishable, secret = await _from_the_account(ctx, self._meanwhile)
        else:
            url, publishable, secret = await _typed_by_hand(ctx)
        for name, value in ((URL, url), (PUBLISHABLE_KEY, publishable), (SECRET_KEY, secret)):
            _save(ctx, name, value, replacing=replacing)
        ctx.detail("Supabase accepted the address and both keys.")


def _keep_saved_project(ctx: SetupContext) -> bool:
    """Say which project is saved and keep it unless a different one is wanted.

    Asked before any token is requested, so keeping the project costs nothing
    and creates nothing.
    """
    saved = ctx.require(URL, StepName.SUPABASE)
    try:
        ref = values.project_ref(saved)
    except ValidationFailedError:
        ctx.io.say(f"The saved {URL} does not look like a Supabase project, so it is replaced.")
        return False
    ctx.io.say(f"Your .env already points to the Supabase project {ref}.")
    if not ctx.io.confirm("Keep it?", default=True):
        ctx.io.say("The old project stays in your Supabase account; only .env changes.")
        return False
    ctx.io.say("Kept the project; nothing was changed.")
    return True


def _save(ctx: SetupContext, name: str, value: str, *, replacing: bool) -> None:
    """Save one value; replace a saved one without asking again when a change was chosen."""
    if not replacing:
        ctx.write(name, value)
        return
    ctx.env.set(name, value)
    ctx.io.say(f"Saved {name} in .env.")


def project_url(project_ref: str) -> str:
    """A project's address.

    Args:
        project_ref: The project's identifier.

    Returns:
        ``https://<project-ref>.supabase.co``.
    """
    return f"https://{project_ref}{SUPABASE_HOST_SUFFIX}"


async def _from_the_account(
    ctx: SetupContext, meanwhile: Sequence[Meanwhile]
) -> tuple[str, str, str]:
    """Find or create the project with this run's token, then read its keys."""
    token = await require_supabase_token(ctx)
    with full_access_needed(ctx):
        project = await find_or_create_project(ctx, token, meanwhile=meanwhile)
        publishable, secret = await read_keys(ctx, token, project.ref)
    url = project_url(project.ref)
    ctx.detail(f"Read the address and both keys of '{project.name}'. Neither key is shown.")
    hint = (
        f"It exists, so give it a minute, then run 'uv run tracker setup {StepName.SUPABASE}' "
        "again and pick it from the list."
    )
    await ask_until_it_answers(ctx, lambda: _check_publishable(ctx, url, publishable), hint=hint)
    await ask_until_it_answers(ctx, lambda: _check_secret(ctx, url, secret), hint=hint)
    return url, publishable, secret


async def _typed_by_hand(ctx: SetupContext) -> tuple[str, str, str]:
    """Take an existing project's address and keys, each checked as it is typed."""
    io = ctx.io
    io.open_page(SUPABASE_PROJECTS_PAGE)
    url = ctx.ask_until_valid(
        lambda: io.ask(
            "Project address or Project ID (https://<project-id>.supabase.co, or just "
            "<project-id>)",
            default=ctx.env.get(URL),
        ),
        values.supabase_url,
    )
    io.say("Now open Project Settings > API Keys, tab 'Publishable and secret API keys'.")
    io.open_page(SUPABASE_API_KEYS_PAGE.format(ref=values.project_ref(url)))
    publishable = await ctx.ask_until_accepted(
        lambda: io.ask("Publishable key (starts with sb_publishable_)"),
        lambda raw: _check_publishable(ctx, url, raw),
    )
    secret = await ctx.ask_until_accepted(
        lambda: io.ask_secret("Secret key (starts with sb_secret_; it stays hidden)"),
        lambda raw: _check_secret(ctx, url, raw),
    )
    return url, publishable, secret


async def _check_publishable(ctx: SetupContext, url: str, raw: str) -> str:
    """Read the project's public settings with the key."""
    key = values.non_empty(raw, "the publishable key")
    await ctx.gateways.platform.signups_disabled(url, SecretStr(key))
    return key


async def _check_secret(ctx: SetupContext, url: str, raw: str) -> str:
    """Make one call only the secret key may make."""
    key = values.non_empty(raw, "the secret key")
    ctx.gateways.admin_for(url, SecretStr(key)).check_service_key()
    return key


class EncryptionStep:
    """Makes the key that locks the stored Microsoft sign-in."""

    name = StepName.ENCRYPTION
    title = "Encryption key"

    async def is_done(self, ctx: SetupContext) -> bool:
        """Done when a usable key is in ``.env``."""
        return is_usable_key(ctx.env.get(ENCRYPTION_KEY))

    async def run(self, ctx: SetupContext) -> None:
        """Keep a usable key; otherwise make one and save it without showing it."""
        io = ctx.io
        ctx.detail("This key locks the Microsoft sign-in that is kept in your database,")
        ctx.detail("so a copy of the database alone reveals nothing. It is made for you.")
        if is_usable_key(ctx.env.get(ENCRYPTION_KEY)):
            io.say("A usable key is already saved; it is kept. Changing it would mean")
            io.say("signing in to Microsoft again.")
            return
        if ctx.write(ENCRYPTION_KEY, ctx.gateways.make_encryption_key()):
            ctx.detail("A new key was made and saved. It is never shown on screen.")


def is_usable_key(value: str | None) -> bool:
    """Tell whether a value is a key the encryption library accepts.

    Args:
        value: The saved value, or ``None``.

    Returns:
        ``True`` when it can be used.
    """
    if not value:
        return False
    try:
        Fernet(value.encode())
    except (ValueError, binascii.Error):
        return False
    return True
