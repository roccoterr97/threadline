"""Steps 1 and 2: the Supabase project and its keys, and the encryption key.

With one Supabase access token the step finds or creates the project and reads
its address and both keys itself; nothing is copied between screens. Someone
who prefers it can still type an existing project's address and keys.
"""

from __future__ import annotations

import binascii
from typing import Final

from cryptography.fernet import Fernet
from pydantic import SecretStr

from tracker.services.setup import values
from tracker.services.setup.context import SetupContext
from tracker.services.setup.models import StepName
from tracker.services.setup.supabase_project import find_or_create_project, read_keys
from tracker.services.setup.supabase_session import require_supabase_token
from tracker.shared.constants.setup import (
    SUPABASE_API_KEYS_PAGE,
    SUPABASE_HOST_SUFFIX,
    SUPABASE_PROJECTS_PAGE,
)

URL: Final[str] = "SUPABASE_URL"
PUBLISHABLE_KEY: Final[str] = "SUPABASE_ANON_KEY"
SECRET_KEY: Final[str] = "SUPABASE_SERVICE_ROLE_KEY"
ENCRYPTION_KEY: Final[str] = "TOKEN_ENCRYPTION_KEY"


class SupabaseStep:
    """Saves the project address and its two keys, once each is accepted live."""

    name = StepName.SUPABASE
    title = "Your Supabase project"

    async def is_done(self, ctx: SetupContext) -> bool:
        """Done when all three values are in ``.env``."""
        return all(ctx.env.get(name) for name in (URL, PUBLISHABLE_KEY, SECRET_KEY))

    async def run(self, ctx: SetupContext) -> None:
        """Find or create the project with the token, or take typed values; check, then save."""
        io = ctx.io
        io.say("Supabase is the database that keeps your people and conversations.")
        io.say("You need a free Supabase account; the set-up creates the project in it.")
        if io.confirm("Create the project (or pick an existing one) for you?", default=True):
            url, publishable, secret = await _from_the_account(ctx)
        else:
            url, publishable, secret = await _typed_by_hand(ctx)
        for name, value in ((URL, url), (PUBLISHABLE_KEY, publishable), (SECRET_KEY, secret)):
            ctx.write(name, value)
        io.say("Supabase accepted the address and both keys.")


def project_url(project_ref: str) -> str:
    """A project's address.

    Args:
        project_ref: The project's identifier.

    Returns:
        ``https://<project-ref>.supabase.co``.
    """
    return f"https://{project_ref}{SUPABASE_HOST_SUFFIX}"


async def _from_the_account(ctx: SetupContext) -> tuple[str, str, str]:
    """Find or create the project with this run's token, then read its keys."""
    token = await require_supabase_token(ctx)
    project = await find_or_create_project(ctx, token)
    url = project_url(project.ref)
    publishable, secret = await read_keys(ctx, token, project.ref)
    ctx.io.say(f"Read the address and both keys of '{project.name}'. Neither key is shown.")
    await _check_publishable(ctx, url, publishable)
    await _check_secret(ctx, url, secret)
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
        io.say("This key locks the Microsoft sign-in that is kept in your database,")
        io.say("so a copy of the database alone reveals nothing. It is made for you.")
        if is_usable_key(ctx.env.get(ENCRYPTION_KEY)):
            io.say("A usable key is already saved; it is kept. Changing it would mean")
            io.say("signing in to Microsoft again.")
            return
        if ctx.write(ENCRYPTION_KEY, ctx.gateways.make_encryption_key()):
            io.say("A new key was made and saved. It is never shown on screen.")


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
