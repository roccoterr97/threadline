"""Asking a project that was just created, which may not answer for a few seconds.

Supabase reports a new project healthy slightly before its address, its auth
server and its data API all answer. The first checks made on it are therefore
repeated a few times, a few seconds apart, before they are taken as failed.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from tracker.services.setup.context import SetupContext
from tracker.shared.constants.setup import (
    NEW_PROJECT_ANSWER_ATTEMPTS,
    NEW_PROJECT_ANSWER_WAIT_SECONDS,
)
from tracker.shared.errors import DatabaseUnavailableError, SourceUnavailableError
from tracker.shared.logging import get_logger

_log = get_logger(__name__)


async def ask_until_it_answers[T](
    ctx: SetupContext, ask: Callable[[], Awaitable[T]], *, hint: str
) -> T:
    """Make a first call on a project, again after a short wait if it does not answer.

    Only an outage is repeated. A key Supabase refuses comes straight back, so
    a wrong key is never hidden by the wait.

    Args:
        ctx: The set-up's context.
        ask: Makes the call once.
        hint: What to say, in plain words, if the project still does not answer.

    Returns:
        What the call returned.

    Raises:
        SourceUnavailableError: If the project never answered (a Supabase address check).
        DatabaseUnavailableError: If the project never answered (a database check).
    """
    for attempt in range(1, NEW_PROJECT_ANSWER_ATTEMPTS + 1):
        try:
            return await ask()
        except (SourceUnavailableError, DatabaseUnavailableError) as error:
            _log.warning("new_project_not_answering", attempt=attempt, code=error.code)
            if attempt == NEW_PROJECT_ANSWER_ATTEMPTS:
                ctx.io.say(f"The project does not answer yet. {hint}")
                raise
        await ctx.gateways.sleep(NEW_PROJECT_ANSWER_WAIT_SECONDS)
    message = "no attempt was made"  # pragma: no cover - the attempts constant is positive
    raise SourceUnavailableError(message)  # pragma: no cover
