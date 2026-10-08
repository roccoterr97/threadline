"""The on-time morning start: the database's timer, and the daily time it reads.

GitHub starts the scheduled workflow when it has room, often hours after its
time. So a timer in the owner's database (pg_cron, migration 0016) calls the
``refresh-now`` function's scheduled path every 15 minutes, and the function
starts the daily run on GitHub once the owner's daily time has passed.

The timer needs two things the set-up provides: the daily time and zone in
``app_settings``, kept in step with the workflow's ``cron`` and ``timezone``
lines by the schedule and time-zone steps, and the function's address with a
shared key in Vault, saved by the Refresh now step. The key is made fresh on
each run of that step and goes to Supabase only; it is never shown or written
to ``.env``.
"""

from __future__ import annotations

from pydantic import SecretStr

from tracker.services.setup.context import SetupContext
from tracker.services.setup.models import StepName
from tracker.services.setup.workflow_schedule import Schedule, read_schedule
from tracker.shared.constants.setup import DAILY_START_INTERVAL_MINUTES, DAILY_START_PATH
from tracker.shared.errors import (
    DatabaseStructureMissingError,
    DatabaseUnavailableError,
    ValidationFailedError,
)

_SUPABASE_URL = "SUPABASE_URL"
_SERVICE_KEY = "SUPABASE_SERVICE_ROLE_KEY"


def daily_start_url(function_address: str) -> str:
    """Address of the function's scheduled path.

    Args:
        function_address: The "Refresh now" function's address.

    Returns:
        Where the database's timer calls.
    """
    return function_address.rstrip("/") + DAILY_START_PATH


def save_schedule_in_database(ctx: SetupContext, schedule: Schedule) -> None:
    """Copy the daily time and zone into the database, for the on-time morning start.

    Nothing is asked and nothing fails here: the workflow file is the step's
    real work. Without a database yet the time is copied later, by the
    Refresh now step; a database that cannot take it is named, with the fix.

    Args:
        ctx: The set-up's context.
        schedule: The daily time the workflow now holds.
    """
    if ctx.env.get(_SUPABASE_URL) is None or ctx.env.get(_SERVICE_KEY) is None:
        return
    try:
        ctx.admin().save_daily_schedule(schedule.at, schedule.zone)
    except DatabaseStructureMissingError:
        ctx.io.say("Your database cannot hold the daily time yet, so only GitHub knows it.")
        ctx.io.say(
            f"To fix it: uv run tracker setup {StepName.DATABASE}, "
            f"then uv run tracker setup {StepName.SCHEDULE} again."
        )
        return
    except DatabaseUnavailableError:
        ctx.io.say("Your database did not answer, so it still has the old daily time.")
        ctx.io.say(f"Run 'uv run tracker setup {StepName.SCHEDULE}' again in a few minutes.")
        return
    ctx.io.say(f"Saved the daily time in your database too: {schedule.describe()}.")


def daily_start_ready(ctx: SetupContext) -> bool:
    """Whether the timer is in place and knows where to call.

    Args:
        ctx: The set-up's context.

    Returns:
        ``False`` too when the database cannot be asked.
    """
    try:
        return ctx.admin().daily_start_status().ready
    except (ValidationFailedError, DatabaseStructureMissingError, DatabaseUnavailableError):
        return False


def switch_on_daily_start(ctx: SetupContext, function_address: str, key: SecretStr) -> None:
    """Copy the daily time, save the timer's address and key, then check the timer.

    The function already holds the same key among its settings; until this
    runs, the timer either does nothing or is turned away, never more.

    Args:
        ctx: The set-up's context.
        function_address: The "Refresh now" function's address.
        key: The shared key, already saved as the function's setting.

    Raises:
        ValidationFailedError: If the database lacks the timer's structure, or
            the timer is still not in place afterwards.
        DatabaseUnavailableError: If the database could not answer.
    """
    io = ctx.io
    io.say("Last, the on-time morning start. GitHub often starts the daily run hours late,")
    io.say("so your Supabase database will start it at its time instead.")
    admin = ctx.admin()
    schedule = _workflow_schedule(ctx)
    try:
        if schedule is not None:
            admin.save_daily_schedule(schedule.at, schedule.zone)
        admin.save_daily_start(daily_start_url(function_address), key)
        status = admin.daily_start_status()
    except DatabaseStructureMissingError as error:
        message = (
            "your database does not have the on-time morning start yet - run "
            f"'uv run tracker setup {StepName.DATABASE}', then "
            f"'uv run tracker setup {StepName.REFRESH}' again"
        )
        raise ValidationFailedError(message) from error
    if not status.ready:
        message = (
            "the database's timer is not in place - run "
            f"'uv run tracker setup {StepName.REFRESH}' again"
        )
        raise ValidationFailedError(message)
    when = f"{status.run_at:%H:%M} ({status.time_zone})" if status.run_at else "its time"
    io.say(f"On-time morning start is switched on: Supabase starts the daily run at {when},")
    io.say(f"looking every {DAILY_START_INTERVAL_MINUTES} minutes. GitHub's own timer stays as")
    io.say("a backup, and stops by itself when the day's run has already started.")


def _workflow_schedule(ctx: SetupContext) -> Schedule | None:
    """The daily time the workflow holds, or ``None`` when it cannot be read."""
    try:
        schedule = read_schedule(ctx.gateways.workflow.read())
    except FileNotFoundError:
        schedule = None
    if schedule is None:
        ctx.io.say("The workflow's daily time could not be read, so the database keeps its own.")
        ctx.io.say(f"To set it: uv run tracker setup {StepName.SCHEDULE}")
    return schedule
