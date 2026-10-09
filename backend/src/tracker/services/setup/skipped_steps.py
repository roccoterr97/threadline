"""Remembering an optional step the owner said no to, so a later run does not ask again.

Finished steps are recognised by what they left behind (a saved setting, a
login, a sign-in). A step the owner skipped leaves nothing, so the skip itself
is written to ``.env``, in ``SETUP_SKIPPED_STEPS``. It is bookkeeping for the
set-up on this computer only: Threadline's settings never read it, so it is
never sent to GitHub. Running the step by name asks again and forgets the skip.
"""

from __future__ import annotations

from typing import Final

from tracker.services.setup.context import SetupContext
from tracker.services.setup.models import StepName

#: The ``.env`` line listing the skipped steps, such as ``microsoft,categories``.
SKIPPED_STEPS: Final[str] = "SETUP_SKIPPED_STEPS"

_SEPARATOR: Final[str] = ","

#: How the owner types the set-up.
_COMMAND: Final[str] = "uv run tracker setup"


def skipped_earlier(ctx: SetupContext, step: StepName, offer: str) -> bool:
    """Say so when the owner skipped this step on an earlier run.

    Args:
        ctx: The set-up's context.
        step: The optional step about to ask.
        offer: What running the step by name does, such as ``To add it``.

    Returns:
        Whether it was skipped, so the step should not ask again.
    """
    if step not in _skipped(ctx):
        return False
    ctx.io.say(f"Skipped earlier. {offer}: {_COMMAND} {step}")
    return True


def remember_skip(ctx: SetupContext, step: StepName) -> None:
    """Write down that the owner said no to this step.

    Args:
        ctx: The set-up's context.
        step: The step that was skipped.
    """
    skipped = _skipped(ctx)
    if step not in skipped:
        _save(ctx, (*skipped, step))


def forget_skip(ctx: SetupContext, step: StepName) -> None:
    """Forget a skip, so the step asks again; nothing is written when there was none.

    Args:
        ctx: The set-up's context.
        step: The step run by name.
    """
    skipped = _skipped(ctx)
    if step in skipped:
        _save(ctx, tuple(name for name in skipped if name is not step))


def _skipped(ctx: SetupContext) -> tuple[StepName, ...]:
    """The skipped steps ``.env`` lists; a word that names no step is ignored."""
    raw = ctx.env.get(SKIPPED_STEPS) or ""
    words = (word.strip().lower() for word in raw.split(_SEPARATOR))
    return tuple(dict.fromkeys(StepName(word) for word in words if word in StepName))


def _save(ctx: SetupContext, steps: tuple[StepName, ...]) -> None:
    """Write the list back, quietly: it is the set-up's own note, not a setting."""
    ctx.env.set(SKIPPED_STEPS, _SEPARATOR.join(steps))
