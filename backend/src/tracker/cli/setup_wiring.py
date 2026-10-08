"""Builds the set-up wizard on real clients: the composition root for ``tracker setup``."""

from __future__ import annotations

import asyncio
import secrets
from pathlib import Path

from cryptography.fernet import Fernet
from pydantic import SecretStr

from tracker.infrastructure.database import connect
from tracker.infrastructure.env_file import EnvFile
from tracker.infrastructure.github_api import GitHubApi
from tracker.infrastructure.github_cli import GitHubCli, GitRepository, TextFile, run_command
from tracker.infrastructure.imap.connection import ImapConnection
from tracker.infrastructure.linkedin.client import LinkedInSnapshotClient
from tracker.infrastructure.local_time_zone import detect_time_zone
from tracker.infrastructure.microsoft.connection import MicrosoftConnection
from tracker.infrastructure.supabase_admin import SupabaseAdmin
from tracker.infrastructure.supabase_platform import SupabasePlatform
from tracker.infrastructure.terminal_io import TerminalIO
from tracker.infrastructure.web_probe import WebProbe
from tracker.repositories import build_repositories
from tracker.services.database_structure import list_migration_files
from tracker.services.profile.applier import ProfileApplier
from tracker.services.profile.choice import ChoiceSaver, ProfileFiles
from tracker.services.setup.context import SetupContext
from tracker.services.setup.ports import SetupGateways, SetupIO
from tracker.shared.clock import Clock, SystemClock
from tracker.shared.config import REPOSITORY_ROOT
from tracker.shared.constants.github import WORKFLOW_FILE
from tracker.shared.constants.profile import GUIDE_FILE, GUIDE_TEMPLATE_FILE, PROFILE_FILE
from tracker.shared.constants.setup import (
    DAILY_START_KEY_BYTES,
    MIGRATIONS_DIRECTORY,
    REFRESH_FUNCTION_DIRECTORY,
    REFRESH_FUNCTION_FILES,
)


def build_context(
    env_path: Path, platform: SupabasePlatform, io: SetupIO | None = None
) -> SetupContext:
    """Put the real terminal, ``.env`` file and clients together.

    Args:
        env_path: Where the ``.env`` file is.
        platform: An open Supabase platform client.
        io: The conversation; the terminal when omitted.

    Returns:
        The context every step works with.
    """
    clock = SystemClock()
    gateways = SetupGateways(
        admin_for=lambda url, key: SupabaseAdmin(connect(url, key)),
        choices_for=lambda url, key: choice_saver(url, key, clock),
        platform=platform,
        microsoft=MicrosoftConnection(connect, clock),
        mailbox=ImapConnection(connect, clock),
        check_linkedin=check_linkedin,
        status_of=WebProbe().status_of,
        status_of_post=WebProbe().status_of_post,
        make_encryption_key=make_encryption_key,
        migrations=list_migration_files(MIGRATIONS_DIRECTORY),
        clock=clock,
        workflow=TextFile(WORKFLOW_FILE),
        git=GitRepository(run_command(REPOSITORY_ROOT)),
        github=GitHubCli(run_command(REPOSITORY_ROOT)),
        sleep=asyncio.sleep,
        local_time_zone=detect_time_zone,
        github_api=GitHubApi(),
        refresh_function=read_refresh_function,
        make_daily_start_key=make_daily_start_key,
    )
    return SetupContext(io=io or TerminalIO(), env=EnvFile(env_path), gateways=gateways)


def choice_saver(url: str, key: SecretStr, clock: Clock) -> ChoiceSaver:
    """Build the category-choice store on the project's database.

    Args:
        url: The project's address.
        key: The secret key.
        clock: Stamps the moment a category is hidden.

    Returns:
        The store ``tracker profile choose`` saves through too.
    """
    repositories = build_repositories(connect(url, key))
    files = ProfileFiles(profile=PROFILE_FILE, guide_template=GUIDE_TEMPLATE_FILE, guide=GUIDE_FILE)
    return ChoiceSaver(repositories, ProfileApplier(repositories, clock), files)


async def check_linkedin(token: SecretStr) -> None:
    """Make one small LinkedIn call with a key.

    Args:
        token: The key to try.
    """
    async with LinkedInSnapshotClient(token) as client:
        await client.check_access()


def read_refresh_function() -> dict[str, bytes]:
    """Read the "Refresh now" function's files from this repository, entry point first."""
    return {
        name: (REFRESH_FUNCTION_DIRECTORY / name).read_bytes() for name in REFRESH_FUNCTION_FILES
    }


def make_encryption_key() -> str:
    """Generate a new key for the encrypted store."""
    return Fernet.generate_key().decode()


def make_daily_start_key() -> str:
    """Generate a new key for the on-time morning start's timer."""
    return secrets.token_urlsafe(DAILY_START_KEY_BYTES)
