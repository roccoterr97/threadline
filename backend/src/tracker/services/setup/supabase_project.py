"""Finding or creating the Supabase project, and reading its keys, with the access token.

The token's organizations are listed; one is chosen when there are several.
The organization's projects are offered for reuse, or a new one is created
with a generated database password that Threadline never needs again, in the
smart region group closest to this computer's time zone. A new project is
watched until Supabase reports it healthy. Last, the project's publishable and
secret keys are read revealed, or created when it has none.
"""

from __future__ import annotations

import re
import secrets
from typing import Final

from pydantic import SecretStr

from tracker.domain.supabase import ApiKey, ApiKeyKind, NewProject, Organization, SupabaseProject
from tracker.services.setup import values
from tracker.services.setup.context import SetupContext
from tracker.services.setup.models import StepName
from tracker.shared.constants.setup import (
    DATABASE_PASSWORD_BYTES,
    DEFAULT_REGION_GROUP,
    PROJECT_FAILED_STATUSES,
    PROJECT_HEALTHY_STATUS,
    PROJECT_READY_ATTEMPTS,
    PROJECT_READY_WAIT_SECONDS,
    PUBLISHABLE_KEY_NAME,
    PUBLISHABLE_KEY_PREFIX,
    REGION_GROUP_BY_ZONE_PREFIX,
    REGION_GROUP_LABELS,
    SECRET_KEY_NAME,
    SECRET_KEY_PREFIX,
    SUPABASE_DEFAULT_PROJECT_NAME,
    RegionGroup,
)
from tracker.shared.errors import (
    SourceAuthError,
    SourceUnavailableError,
    ValidationFailedError,
)
from tracker.shared.logging import get_logger

_log = get_logger(__name__)

#: What a whole API key is made of; a masked one carries dots or bullets.
_KEY_CHARACTERS: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9_-]+")


async def find_or_create_project(ctx: SetupContext, token: SecretStr) -> SupabaseProject:
    """Choose an existing project or create a new one, and wait until it is up.

    Args:
        ctx: The set-up's context.
        token: This run's accepted access token.

    Returns:
        The project, healthy.

    Raises:
        ValidationFailedError: If the account has no organization, or the
            project is still not up after the longest wait.
        SourceUnavailableError: If Supabase gave up on the project.
    """
    organization = await _choose_organization(ctx, token)
    existing = await _usable_projects(ctx, token, organization)
    project = _pick_existing(ctx, existing) if existing else None
    if project is None:
        project = await _create(ctx, token, organization)
    return await wait_until_ready(ctx, token, project)


async def read_keys(ctx: SetupContext, token: SecretStr, project_ref: str) -> tuple[str, str]:
    """Read the project's publishable and secret keys, creating any it lacks.

    Args:
        ctx: The set-up's context.
        token: This run's accepted access token.
        project_ref: The project's identifier.

    Returns:
        The publishable key, then the secret key. Neither is shown.
    """
    keys = await ctx.gateways.platform.api_keys(project_ref, token)
    publishable = await _key_of_kind(
        ctx, token, project_ref, keys, ApiKeyKind.PUBLISHABLE, PUBLISHABLE_KEY_PREFIX
    )
    secret = await _key_of_kind(ctx, token, project_ref, keys, ApiKeyKind.SECRET, SECRET_KEY_PREFIX)
    return publishable, secret


def region_group_for(zone: str) -> RegionGroup:
    """Name the region group closest to a time zone.

    Args:
        zone: A time-zone name such as ``Europe/Rome``.

    Returns:
        The group, or the Americas when the zone says nothing about a place.
    """
    for prefix, group in REGION_GROUP_BY_ZONE_PREFIX.items():
        if zone.startswith(prefix):
            return group
    return DEFAULT_REGION_GROUP


async def wait_until_ready(
    ctx: SetupContext, token: SecretStr, project: SupabaseProject
) -> SupabaseProject:
    """Look at a project every few seconds until Supabase reports it healthy.

    A look that fails (Supabase says "too many requests", or answers with an
    error while the project is coming up) is logged and counted as one
    attempt; the next look comes after the usual wait.

    Args:
        ctx: The set-up's context.
        token: This run's accepted access token.
        project: The project as last seen.

    Returns:
        The project, healthy.

    Raises:
        SourceUnavailableError: If Supabase gave up on the project.
        ValidationFailedError: If it is still not up after the longest wait.
    """
    if project.status == PROJECT_HEALTHY_STATUS:
        return project
    ctx.io.say("Supabase is setting the project up; this takes one to three minutes.")
    for _ in range(PROJECT_READY_ATTEMPTS):
        await ctx.gateways.sleep(PROJECT_READY_WAIT_SECONDS)
        try:
            project = await ctx.gateways.platform.project(token, project.ref)
        except SourceUnavailableError as error:
            _log.warning("project_status_unavailable", ref=project.ref, code=error.code)
            continue
        if project.status == PROJECT_HEALTHY_STATUS:
            ctx.io.say("The project is up.")
            return project
        if project.status in PROJECT_FAILED_STATUSES:
            message = (
                f"Supabase could not set the project up (status {project.status}) - "
                "delete it in the Supabase dashboard, then run this step again"
            )
            raise SourceUnavailableError(message)
    minutes = int(PROJECT_READY_ATTEMPTS * PROJECT_READY_WAIT_SECONDS // 60)
    message = (
        f"the project is still being set up after {minutes} minutes - run "
        f"'uv run tracker setup {StepName.SUPABASE}' again in a while and pick it from the list"
    )
    raise ValidationFailedError(message)


async def _choose_organization(ctx: SetupContext, token: SecretStr) -> Organization:
    """Use the only organization, or ask which one when there are several."""
    organizations = await ctx.gateways.platform.organizations(token)
    if not organizations:
        message = (
            "your Supabase account has no organization yet - create one on supabase.com, "
            "then run this step again"
        )
        raise ValidationFailedError(message)
    if len(organizations) == 1:
        ctx.io.say(f"Your Supabase organization: {organizations[0].name}.")
        return organizations[0]
    ctx.io.say("Your Supabase organizations:")
    number = _ask_for_one(ctx, [item.name for item in organizations], "Which one? (number)")
    return organizations[number - 1]


async def _usable_projects(
    ctx: SetupContext, token: SecretStr, organization: Organization
) -> tuple[SupabaseProject, ...]:
    """The organization's projects that can still come up."""
    return tuple(
        project
        for project in await ctx.gateways.platform.projects(token)
        if project.organization_slug == organization.slug
        and project.status not in PROJECT_FAILED_STATUSES
    )


def _pick_existing(
    ctx: SetupContext, projects: tuple[SupabaseProject, ...]
) -> SupabaseProject | None:
    """Offer the existing projects; ``None`` when a new one is wanted."""
    io = ctx.io
    io.say(f"Projects already there: {', '.join(project.name for project in projects)}.")
    if not io.confirm("Use one of them instead of creating a new project?", default=False):
        return None
    if len(projects) == 1:
        return projects[0]
    number = _ask_for_one(ctx, [project.name for project in projects], "Which one? (number)")
    return projects[number - 1]


async def _create(
    ctx: SetupContext, token: SecretStr, organization: Organization
) -> SupabaseProject:
    """Create a project with a generated database password that is never kept."""
    io = ctx.io
    name = ctx.ask_until_valid(
        lambda: io.ask("Name for the new project", default=SUPABASE_DEFAULT_PROJECT_NAME),
        values.project_name,
    )
    region = _choose_region(ctx)
    password = SecretStr(secrets.token_urlsafe(DATABASE_PASSWORD_BYTES))
    request = NewProject(
        organization_slug=organization.slug, name=name, region=region, database_password=password
    )
    project = await ctx.gateways.platform.create_project(token, request)
    io.say(f"Created the project '{name}' ({project.ref}).")
    io.say("Its database password was generated and is not kept: Threadline never needs it.")
    io.say("If you ever do, reset it in the Supabase dashboard (Project Settings > Database).")
    return project


def _choose_region(ctx: SetupContext) -> RegionGroup:
    """Offer the region group closest to this computer's time zone."""
    groups = list(RegionGroup)
    offered = groups.index(region_group_for(ctx.gateways.local_time_zone())) + 1
    ctx.io.say("Where should it live? Supabase picks the closest data centre in the group.")
    number = _ask_for_one(
        ctx, [REGION_GROUP_LABELS[group] for group in groups], "Region (number)", default=offered
    )
    return groups[number - 1]


def _ask_for_one(ctx: SetupContext, names: list[str], prompt: str, *, default: int = 1) -> int:
    """Show a numbered list and ask for one number."""
    for number, name in enumerate(names, start=1):
        ctx.io.say(f"  {number}. {name}")
    return ctx.ask_until_valid(
        lambda: ctx.io.ask(prompt, default=str(default)),
        lambda raw: values.list_number(raw, len(names)),
    )


async def _key_of_kind(
    ctx: SetupContext,
    token: SecretStr,
    project_ref: str,
    keys: tuple[ApiKey, ...],
    kind: ApiKeyKind,
    prefix: str,
) -> str:
    """The first revealed key of a kind, or a new one when the project has none.

    Raises:
        SourceAuthError: If the project has such a key but the token may not reveal it.
    """
    of_kind = [key for key in keys if key.kind is kind]
    for key in of_kind:
        value = key.value.get_secret_value() if key.value is not None else ""
        if _is_whole_key(value, prefix):
            return value
    if of_kind:
        message = (
            f"the access token cannot read the project's {kind.value} key - make a token "
            "with the 'API Keys' and 'API Key Secrets' permissions, then run this step again"
        )
        raise SourceAuthError(message)
    name = PUBLISHABLE_KEY_NAME if kind is ApiKeyKind.PUBLISHABLE else SECRET_KEY_NAME
    ctx.io.say(f"The project has no {kind.value} key yet, so one named '{name}' is made.")
    created = await ctx.gateways.platform.create_api_key(project_ref, token, kind, name)
    return created.get_secret_value()


def _is_whole_key(value: str, prefix: str) -> bool:
    """Whether a key was revealed in full, not shortened or masked for display."""
    return value.startswith(prefix) and _KEY_CHARACTERS.fullmatch(value) is not None
