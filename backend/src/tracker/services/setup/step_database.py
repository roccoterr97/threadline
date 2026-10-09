"""Step 3: the database structure, applied automatically or by hand.

Supabase names each file it applies after the current second, so two files sent
within one second collide. The step therefore waits a moment between files and
sends a refused file once more before switching to the SQL editor. By hand, it
checks after each confirmation that the file really ran, and asks again if not.
"""

from __future__ import annotations

from pydantic import SecretStr

from tracker.services.database_structure import (
    MigrationFile,
    StructureProbe,
    StructureReport,
    inspect_structure,
    is_applied,
)
from tracker.services.setup import values
from tracker.services.setup.context import MAX_ATTEMPTS, SetupContext
from tracker.services.setup.fresh_project import ask_until_it_answers
from tracker.services.setup.models import StepName
from tracker.services.setup.ports import SetupIO
from tracker.services.setup.supabase_session import require_supabase_token
from tracker.shared.constants.setup import (
    MIGRATION_PAUSE_SECONDS,
    MIGRATION_RETRY_WAIT_SECONDS,
    SUPABASE_SQL_EDITOR_PAGE,
)
from tracker.shared.errors import (
    SourceAuthError,
    SourceRequestRejectedError,
    SourceUnavailableError,
    ValidationFailedError,
)


class DatabaseStep:
    """Creates the tables, views and rules Threadline needs."""

    name = StepName.DATABASE
    title = "Database structure"

    async def is_done(self, ctx: SetupContext) -> bool:
        """Never skipped: checking is quick and changes nothing."""
        return False

    async def run(self, ctx: SetupContext) -> None:
        """Find what is missing, apply it, then check again."""
        files = ctx.gateways.migrations
        ctx.io.say("The database needs its tables before anything can be stored.")
        pending = pending_files(files, await _inspect_when_it_answers(ctx))
        if not pending:
            ctx.io.say("Every structure file is already applied.")
            return
        ctx.io.say(f"To apply: {', '.join(item.name for item in pending)}.")
        ref = values.project_ref(ctx.require("SUPABASE_URL", StepName.SUPABASE))
        remaining = pending
        if _apply_automatically_wanted(ctx):
            remaining = await _apply_automatically(ctx, ref, pending)
        if remaining:
            _guide_by_hand(ctx, ref, remaining)
        report = inspect_structure(files, ctx.admin())
        if report.missing:
            message = f"still not applied: {', '.join(report.missing)}"
            raise ValidationFailedError(message)
        ctx.io.say("The database structure is in place.")


async def _inspect_when_it_answers(ctx: SetupContext) -> StructureReport:
    """Look at the structure; a project that was just created gets a few more tries."""

    async def inspect() -> StructureReport:
        return inspect_structure(ctx.gateways.migrations, ctx.admin())

    hint = f"Give it a minute, then run 'uv run tracker setup {StepName.DATABASE}' again."
    return await ask_until_it_answers(ctx, inspect, hint=hint)


def pending_files(
    files: tuple[MigrationFile, ...], report: StructureReport
) -> tuple[MigrationFile, ...]:
    """Choose the files to apply.

    A file the database cannot confirm is taken to be applied only when a
    later file shows and no earlier one is missing. Otherwise it is applied
    again, which every such file allows: one that comes after a missing file,
    or after every file that shows (a database at 0006 is offered 0007), may
    never have run.

    Args:
        files: Every migration file, in order.
        report: What the database showed.

    Returns:
        The files to apply, in order; empty when nothing is missing.
    """
    return tuple(
        item
        for item in files
        if item.name in report.missing
        or (item.name in report.unconfirmed and _may_not_have_run(item.name, report))
    )


def _may_not_have_run(name: str, report: StructureReport) -> bool:
    """Whether an unconfirmed file comes after a missing one or after every one that shows."""
    first_missing = min(report.missing, default=None)
    newest_present = max(report.present, default=None)
    after_a_gap = first_missing is not None and name > first_missing
    after_the_last_seen = newest_present is None or name > newest_present
    return after_a_gap or after_the_last_seen


def _apply_automatically_wanted(ctx: SetupContext) -> bool:
    """Apply with this run's token when there is one; otherwise ask first."""
    if ctx.session.supabase_token is not None:
        return True
    return ctx.io.confirm(
        "Apply them automatically? It needs a Supabase access token, used now and not saved.",
        default=True,
    )


async def _apply_automatically(
    ctx: SetupContext, ref: str, pending: tuple[MigrationFile, ...]
) -> tuple[MigrationFile, ...]:
    """Apply files through Supabase's Management API, one second or more apart.

    Returns:
        The files still to apply by hand; empty when all went through.
    """
    token = await require_supabase_token(ctx)
    try:
        applied = await ctx.gateways.platform.applied_migrations(ref, token)
    except SourceAuthError as error:
        _say_token_may_not_apply(ctx, error)
        ctx.io.say("Carrying on by hand instead.")
        return pending
    sent_before = False
    for index, item in enumerate(pending):
        if item.name in applied:
            continue
        if sent_before:
            await ctx.gateways.sleep(MIGRATION_PAUSE_SECONDS)
        sent_before = True
        if not await _apply_one(ctx, ref, token, item):
            ctx.io.say("Carrying on by hand from that file.")
            return pending[index:]
        ctx.io.say(f"Applied {item.name}.")
    return ()


async def _apply_one(ctx: SetupContext, ref: str, token: SecretStr, item: MigrationFile) -> bool:
    """Send one file, and once more after a short wait if Supabase refused it.

    A token that may read the applied files but not run one (Supabase answers
    401 or 403) is not retried: it ends the automatic route at once.

    Returns:
        Whether the file is now applied.
    """
    platform = ctx.gateways.platform
    try:
        await platform.apply_migration(ref, token, item.name, item.sql())
    except SourceRequestRejectedError as error:
        ctx.io.say(f"Supabase could not apply {item.name}: {error.message}.")
        ctx.io.say("Trying that file once more in a few seconds.")
    except SourceAuthError as error:
        _say_token_may_not_apply(ctx, error)
        return False
    except SourceUnavailableError as error:
        ctx.io.say(f"Supabase could not apply {item.name}: {error.message}.")
        return False
    else:
        return True
    await ctx.gateways.sleep(MIGRATION_RETRY_WAIT_SECONDS)
    if is_applied(item.name, ctx.admin()):
        return True
    try:
        await platform.apply_migration(ref, token, item.name, item.sql())
    except SourceAuthError as error:
        _say_token_may_not_apply(ctx, error)
        return False
    except SourceUnavailableError as error:
        ctx.io.say(f"Supabase could not apply {item.name} again: {error.message}.")
        return False
    return True


def _say_token_may_not_apply(ctx: SetupContext, error: SourceAuthError) -> None:
    """Explain that the token may read the project's files but not change its database."""
    ctx.io.say(f"{error.message}: it may not change this project's database.")


def _guide_by_hand(ctx: SetupContext, ref: str, remaining: tuple[MigrationFile, ...]) -> None:
    """Walk through pasting each file into Supabase's SQL editor."""
    io = ctx.io
    io.say("In the SQL editor that opens, click '+' for a new query for each file.")
    io.open_page(SUPABASE_SQL_EDITOR_PAGE.format(ref=ref))
    probe = ctx.admin()
    for number, item in enumerate(remaining, start=1):
        io.say(f"File {number} of {len(remaining)}: supabase/migrations/{item.path.name}")
        _apply_by_hand(ctx, item, probe)


def _apply_by_hand(ctx: SetupContext, item: MigrationFile, probe: StructureProbe) -> None:
    """Hand over one file, then ask again until the database shows it ran.

    A file whose effect the database cannot show is taken on trust.

    Raises:
        ValidationFailedError: If the file still does not show after every attempt.
    """
    io = ctx.io
    for attempt in range(1, MAX_ATTEMPTS + 1):
        _hand_over(io, item)
        io.pause("Once Supabase shows 'Success. No rows returned'")
        if is_applied(item.name, probe) is not False:
            return
        io.say(f"The database does not show {item.name} yet, so it has not been run.")
        if attempt < MAX_ATTEMPTS:
            io.say("Let's do the same file again: paste it into a new query and click Run.")
    message = f"{item.name} is still not applied - run 'uv run tracker setup database' again"
    raise ValidationFailedError(message)


def _hand_over(io: SetupIO, item: MigrationFile) -> None:
    """Put a file on the clipboard, or say where to copy it from."""
    if io.copy(item.sql()):
        io.say("Its content is on your clipboard: paste it into the editor and click Run.")
    else:
        io.say("Open that file in a text editor, copy all of it, paste it and click Run.")
