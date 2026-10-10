"""Finding or creating the Supabase project, and reading its keys, with the access token.

The token's organizations are listed; one is chosen when there are several.
The organization's projects are offered for reuse, or a new one is created
with a generated database password that Threadline never needs again, in the
smart region group closest to this computer's time zone. A new project is
watched until Supabase reports it healthy. Last, the project's publishable and
secret keys are read revealed, or created when it has none.

An express run asks none of that. It reuses the project named ``threadline``
when there is one, running or starting, and otherwise creates it with that
name in the region nearest the time zone. It never picks a project with
another name by itself, since that project may hold someone's other data: only
when Supabase will not create one (the free plan is full) are the projects
listed, and one is used after an explicit yes.
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
    PROJECT_PAUSED_STATUS,
    PROJECT_READY_ATTEMPTS,
    PROJECT_READY_WAIT_SECONDS,
    PROJECT_REUSABLE_STATUSES,
    PROJECT_STATUS_LABELS,
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
    SourcePermissionError,
    SourceRequestRejectedError,
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
        ValidationFailedError: If the account has no organization, no project
            was chosen, or the project is still not up after the longest wait.
        SourceUnavailableError: If Supabase gave up on the project.
    """
    if ctx.session.express:
        project = await _threadline_project(ctx, token)
    else:
        project = await _chosen_or_created(ctx, token)
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


def region_group_for(zone: str | None) -> RegionGroup:
    """Name the region group closest to a time zone.

    Args:
        zone: A time-zone name such as ``Europe/Rome``, or ``None`` when unknown.

    Returns:
        The group, or the Americas when the zone is unknown or says nothing
        about a place.
    """
    if zone is None:
        return DEFAULT_REGION_GROUP
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
    ctx.io.say("If you stop now (Ctrl-C), it keeps being set up: run this step again and")
    if ctx.session.express:
        ctx.io.say("it carries on with this project instead of creating another.")
    else:
        ctx.io.say("pick it from the list instead of creating another.")
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
        f"the project '{project.name}' is still being set up after {minutes} minutes. It is "
        f"already created, so do not create another: run 'uv run tracker setup "
        f"{StepName.SUPABASE}' again in a while and pick it from the list"
    )
    raise ValidationFailedError(message)


async def _chosen_or_created(ctx: SetupContext, token: SecretStr) -> SupabaseProject:
    """Offer the organization's projects for reuse, or create one with the name and region asked."""
    organization = await _choose_organization(ctx, token)
    projects = await _organization_projects(ctx, token, organization)
    _mention_paused(ctx, projects)
    existing = _usable(projects)
    project = _pick_existing(ctx, existing) if existing else None
    if project is not None:
        return project
    return await _create(ctx, token, organization, _asked_name(ctx), _asked_region(ctx))


async def _threadline_project(ctx: SetupContext, token: SecretStr) -> SupabaseProject:
    """Reuse the project named ``threadline``, or create it; never take another one unasked."""
    projects = await ctx.gateways.platform.projects(token)
    ours = _ours(projects)
    if ours:
        project = ours[0] if len(ours) == 1 else _one_of_ours(ctx, ours)
        ctx.io.say(f"Using your Supabase project '{project.name}' ({project.ref}).")
        return project
    organization = await _choose_organization(ctx, token)
    in_organization = tuple(
        project for project in projects if project.organization_slug == organization.slug
    )
    _stop_for_a_paused_one(ctx, in_organization)
    region = region_group_for(ctx.gateways.local_time_zone())
    ctx.io.say(
        f"Creating the project '{SUPABASE_DEFAULT_PROJECT_NAME}' in {REGION_GROUP_LABELS[region]}, "
        "the region nearest your time zone."
    )
    try:
        return await _create(ctx, token, organization, SUPABASE_DEFAULT_PROJECT_NAME, region)
    except SourceRequestRejectedError as error:
        others = _usable(in_organization)
        if not others:
            raise
        return _chosen_after_refusal(ctx, others, error)


def _ours(projects: tuple[SupabaseProject, ...]) -> tuple[SupabaseProject, ...]:
    """The projects with the set-up's own name that are running or starting."""
    return tuple(
        project
        for project in projects
        if project.name == SUPABASE_DEFAULT_PROJECT_NAME
        and project.status in PROJECT_REUSABLE_STATUSES
    )


def _one_of_ours(ctx: SetupContext, ours: tuple[SupabaseProject, ...]) -> SupabaseProject:
    """Ask which of several projects named ``threadline`` to use."""
    ctx.io.say(f"You have several projects named '{SUPABASE_DEFAULT_PROJECT_NAME}':")
    names = [f"{_described(project)}, {project.ref}" for project in ours]
    return ours[_ask_for_one(ctx, names, "Which one? (number)") - 1]


def _stop_for_a_paused_one(ctx: SetupContext, projects: tuple[SupabaseProject, ...]) -> None:
    """Stop before creating a second ``threadline`` beside a paused one, unless told to.

    Raises:
        ValidationFailedError: If the paused one is to be restored instead.
    """
    paused = next(
        (
            project
            for project in projects
            if project.name == SUPABASE_DEFAULT_PROJECT_NAME
            and project.status == PROJECT_PAUSED_STATUS
        ),
        None,
    )
    if paused is None:
        return
    ctx.io.say(f"Your project '{paused.name}' is paused. It may hold your Threadline data.")
    if ctx.io.confirm("Create a new project instead of restoring it?", default=False):
        return
    message = (
        f"the project '{paused.name}' is paused - restore it in Supabase (open it and click "
        "'Restore project'), then run the set-up again"
    )
    raise ValidationFailedError(message)


def _chosen_after_refusal(
    ctx: SetupContext, projects: tuple[SupabaseProject, ...], error: SourceRequestRejectedError
) -> SupabaseProject:
    """List the projects after Supabase refused a new one, and use one only after a yes.

    Raises:
        ValidationFailedError: If none of them is to be used.
    """
    io = ctx.io
    io.say(f"Supabase would not create a new project. {error.message}.")
    io.say("On the free plan an account has at most two active projects. Yours:")
    _show_numbered(ctx, [_described(project) for project in projects])
    io.say("Threadline adds its own tables to the project it uses, so choose one only if")
    io.say("nothing else needs it. Or pause or delete a project in Supabase and run the")
    io.say(f"set-up again: it then creates '{SUPABASE_DEFAULT_PROJECT_NAME}'.")
    if not io.confirm("Use one of these projects for Threadline?", default=False):
        message = (
            "no project to use yet - pause or delete one in Supabase, then run the set-up again"
        )
        raise ValidationFailedError(message)
    if len(projects) == 1:
        return projects[0]
    return projects[_ask_number(ctx, len(projects), "Which one? (number)", None) - 1]


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


async def _organization_projects(
    ctx: SetupContext, token: SecretStr, organization: Organization
) -> tuple[SupabaseProject, ...]:
    """Every project of the organization, whatever its status."""
    return tuple(
        project
        for project in await ctx.gateways.platform.projects(token)
        if project.organization_slug == organization.slug
    )


def _usable(projects: tuple[SupabaseProject, ...]) -> tuple[SupabaseProject, ...]:
    """The projects that can still come up."""
    return tuple(project for project in projects if project.status not in PROJECT_FAILED_STATUSES)


def _mention_paused(ctx: SetupContext, projects: tuple[SupabaseProject, ...]) -> None:
    """Name each paused project and how to bring it back; none is offered for use.

    A paused free project is restored in the dashboard and takes a while to
    come back, so the step does not pick it up directly.
    """
    for project in projects:
        if project.status == PROJECT_PAUSED_STATUS:
            ctx.io.say(
                f"'{project.name}' is paused. Restore it in Supabase (open the project and "
                "click 'Restore project'), then run this step again, or create a new project."
            )


def _pick_existing(
    ctx: SetupContext, projects: tuple[SupabaseProject, ...]
) -> SupabaseProject | None:
    """Offer the existing projects; ``None`` when a new one is wanted.

    A project named like the one this set-up creates, and not yet or already
    running, is most likely left by a run that stopped, so it is the default
    answer: pressing Enter must not create a second one.
    """
    io = ctx.io
    left_over = _left_over_by_an_earlier_run(projects)
    io.say("Projects already there:")
    _show_numbered(ctx, [_described(project) for project in projects])
    if left_over is not None:
        io.say(f"'{left_over.name}' looks like the one an earlier run made.")
    if not io.confirm(
        "Use one of them instead of creating a new project?", default=left_over is not None
    ):
        return None
    if len(projects) == 1:
        return projects[0]
    default = projects.index(left_over) + 1 if left_over is not None else 1
    return projects[_ask_number(ctx, len(projects), "Which one? (number)", default) - 1]


def _left_over_by_an_earlier_run(projects: tuple[SupabaseProject, ...]) -> SupabaseProject | None:
    """The first project with the set-up's own name that is running or starting."""
    return next(
        (
            project
            for project in projects
            if project.name == SUPABASE_DEFAULT_PROJECT_NAME
            and project.status in PROJECT_REUSABLE_STATUSES
        ),
        None,
    )


def _described(project: SupabaseProject) -> str:
    """A project's name with its status in plain words."""
    label = PROJECT_STATUS_LABELS.get(project.status, f"status {project.status}")
    return f"{project.name} ({label})"


def _asked_name(ctx: SetupContext) -> str:
    """Ask the new project's name, offering the set-up's own."""
    return ctx.ask_until_valid(
        lambda: ctx.io.ask(
            "Name for the new project", default=SUPABASE_DEFAULT_PROJECT_NAME, exact=True
        ),
        values.project_name,
    )


async def _create(
    ctx: SetupContext,
    token: SecretStr,
    organization: Organization,
    name: str,
    region: RegionGroup,
) -> SupabaseProject:
    """Create a project with a generated database password that is never kept."""
    io = ctx.io
    password = SecretStr(secrets.token_urlsafe(DATABASE_PASSWORD_BYTES))
    request = NewProject(
        organization_slug=organization.slug, name=name, region=region, database_password=password
    )
    try:
        project = await ctx.gateways.platform.create_project(token, request)
    except SourceUnavailableError:
        io.say("Supabase did not confirm, so a project may already have been created.")
        io.say("Look at your projects in Supabase and run this step again to pick it,")
        io.say("instead of creating another.")
        raise
    io.say(f"Created the project '{name}' ({project.ref}).")
    io.say("Its database password was generated and is not kept: Threadline never needs it.")
    io.say("If you ever do, reset it in the Supabase dashboard (Project Settings > Database).")
    return project


def _asked_region(ctx: SetupContext) -> RegionGroup:
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
    _show_numbered(ctx, names)
    return _ask_number(ctx, len(names), prompt, default)


def _show_numbered(ctx: SetupContext, names: list[str]) -> None:
    """Say each name with its number."""
    for number, name in enumerate(names, start=1):
        ctx.io.say(f"  {number}. {name}")


def _ask_number(ctx: SetupContext, count: int, prompt: str, default: int | None) -> int:
    """Ask for the number of one of ``count`` items already shown; ``None`` offers none."""
    offered = None if default is None else str(default)
    return ctx.ask_until_valid(
        lambda: ctx.io.ask(prompt, default=offered),
        lambda raw: values.list_number(raw, count),
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
        SourcePermissionError: If the project has such a key but the token may not reveal it.
    """
    of_kind = [key for key in keys if key.kind is kind]
    for key in of_kind:
        value = key.value.get_secret_value() if key.value is not None else ""
        if _is_whole_key(value, prefix):
            return value
    if of_kind:
        message = f"Supabase says the access token may not read the project's {kind.value} key"
        raise SourcePermissionError(message)
    name = PUBLISHABLE_KEY_NAME if kind is ApiKeyKind.PUBLISHABLE else SECRET_KEY_NAME
    ctx.io.say(f"The project has no {kind.value} key yet, so one named '{name}' is made.")
    created = await ctx.gateways.platform.create_api_key(project_ref, token, kind, name)
    return created.get_secret_value()


def _is_whole_key(value: str, prefix: str) -> bool:
    """Whether a key was revealed in full, not shortened or masked for display."""
    return value.startswith(prefix) and _KEY_CHARACTERS.fullmatch(value) is not None
