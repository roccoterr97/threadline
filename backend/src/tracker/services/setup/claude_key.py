"""Asking for the Claude subscription key, and catching one that was copied wrong.

``claude setup-token`` prints the key across two lines of the window. A copy
can stop at the end of the first line, or bring the line break along, which a
hidden prompt used to end the answer at, so only the first half was saved.
The key is therefore checked by its shape before it goes to GitHub: how it
starts, what it is made of, and whether it is long enough. A key cut short gets
one more prompt for the rest of it, which also takes in a second line that is
already waiting (as on Windows, where the rest of a paste waits for the next
prompt). Whether Claude accepts the key is not asked here: that would
spend the subscription's usage. The first run on GitHub, which the set-up
watches, is that check.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Final

from pydantic import SecretStr

from tracker.services.setup.context import MAX_ATTEMPTS, SetupContext
from tracker.shared.constants.claude import (
    CLAUDE_API_KEY_PREFIX,
    CLAUDE_KEY_CHARACTERS,
    CLAUDE_KEY_FAMILY_PREFIX,
    CLAUDE_KEY_MIN_LENGTH,
    CLAUDE_SUBSCRIPTION_KEY_PREFIX,
)
from tracker.shared.constants.github import CLAUDE_TOKEN_SECRET
from tracker.shared.errors import ValidationFailedError
from tracker.shared.logging import get_logger

_log = get_logger(__name__)

_KEY_CHARACTERS: Final[re.Pattern[str]] = re.compile(CLAUDE_KEY_CHARACTERS)

#: How to copy the key, said whenever a copy went wrong.
_HOW_TO_COPY: Final[str] = "copy it from the first letter to the last, including the second line"


class ClaudeKeyProblem(StrEnum):
    """What is wrong with a pasted key, judged by its shape alone."""

    NOT_A_KEY = "not_a_key"
    API_KEY = "api_key"
    STRAY_CHARACTERS = "stray_characters"
    CUT_SHORT = "cut_short"


#: What the owner is told about each problem.
_PROBLEM_LINES: Final[dict[ClaudeKeyProblem, str]] = {
    ClaudeKeyProblem.NOT_A_KEY: (
        f"That is not the key: it starts with {CLAUDE_SUBSCRIPTION_KEY_PREFIX}. "
        f"In the window where 'claude setup-token' ran, {_HOW_TO_COPY}"
    ),
    ClaudeKeyProblem.API_KEY: (
        f"That is an API key ({CLAUDE_API_KEY_PREFIX}...), which bills an API account. "
        "GitHub needs the subscription key that 'claude setup-token' prints, starting "
        f"{CLAUDE_SUBSCRIPTION_KEY_PREFIX}"
    ),
    ClaudeKeyProblem.STRAY_CHARACTERS: (
        f"That has characters a key never has. Copy only the key: {_HOW_TO_COPY}"
    ),
    ClaudeKeyProblem.CUT_SHORT: f"That key is cut short. Paste it again: {_HOW_TO_COPY}",
}

#: The prompt that takes in the rest of a key cut short.
_REST_PROMPT: Final[str] = (
    "That key looks cut short (it is split over two lines). Paste its second line, or the "
    "whole key again (it is not shown)"
)


def claude_key_problem(key: str) -> ClaudeKeyProblem | None:
    """Judge a pasted key by its shape.

    Args:
        key: The key, with every space and line break already taken out.

    Returns:
        What is wrong with it, or ``None`` when it looks whole.
    """
    if key.startswith(CLAUDE_API_KEY_PREFIX):
        return ClaudeKeyProblem.API_KEY
    if not key.startswith(CLAUDE_SUBSCRIPTION_KEY_PREFIX):
        return ClaudeKeyProblem.NOT_A_KEY
    if _KEY_CHARACTERS.fullmatch(key.removeprefix(CLAUDE_KEY_FAMILY_PREFIX)) is None:
        return ClaudeKeyProblem.STRAY_CHARACTERS
    if len(key) < CLAUDE_KEY_MIN_LENGTH:
        return ClaudeKeyProblem.CUT_SHORT
    return None


def ask_claude_key(ctx: SetupContext) -> SecretStr | None:
    """Ask for the Claude subscription key; it is kept in memory only.

    Args:
        ctx: The set-up's context.

    Returns:
        The key, or ``None`` when the answer was empty: GitHub keeps the key it has.

    Raises:
        ValidationFailedError: If every attempt gave a key that is not whole.
    """
    io = ctx.io
    io.say("GitHub also needs a key to use your Claude subscription. To make it:")
    io.say("  Open a new terminal window, run claude setup-token, and sign in in the browser.")
    io.say(f"  Back in that window it prints a long key starting {CLAUDE_SUBSCRIPTION_KEY_PREFIX},")
    io.say(f"  split over two lines: {_HOW_TO_COPY}. It lasts one year.")
    key = _cleaned(
        io.ask_secret(
            f"Paste that key for {CLAUDE_TOKEN_SECRET} (it is not shown), or leave it empty "
            "to keep the key GitHub already has, if any"
        )
    )
    if not key:
        io.say(f"No new key: GitHub keeps the {CLAUDE_TOKEN_SECRET} it already has, if any.")
        return None
    return SecretStr(_whole_key(ctx, key))


def _whole_key(ctx: SetupContext, key: str) -> str:
    """Ask again until the key looks whole, joining a second line to a first.

    Raises:
        ValidationFailedError: If every attempt gave a key that is not whole.
    """
    for _ in range(MAX_ATTEMPTS):
        problem = claude_key_problem(key)
        if problem is None:
            return key
        _log.info("claude_key_refused", problem=problem.value)
        if problem is ClaudeKeyProblem.CUT_SHORT:
            more = _cleaned(ctx.io.ask_secret(_REST_PROMPT))
            key = more if more.startswith(CLAUDE_KEY_FAMILY_PREFIX) else key + more
            continue
        ctx.io.say(f"  {_PROBLEM_LINES[problem]}.")
        key = _cleaned(ctx.io.ask_secret(f"Paste the key for {CLAUDE_TOKEN_SECRET} again"))
    problem = claude_key_problem(key)
    if problem is None:
        return key
    raise ValidationFailedError(_PROBLEM_LINES[problem])


def _cleaned(raw: str) -> str:
    """The pasted text without spaces or line breaks, which a key never has."""
    return "".join(raw.split())
