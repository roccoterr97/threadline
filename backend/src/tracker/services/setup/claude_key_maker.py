"""Making the Claude subscription key for the owner, instead of asking them to paste it.

When Claude Code is on this computer, the GitHub step offers to run
``claude setup-token`` itself: a Claude page opens in the browser, the owner
clicks Authorize, and the key it prints is read from its screen. That screen is
never shown: the owner sees only Threadline's own lines, the sign-in address
once (for when no page opened) and, after a while without a key, how to paste
a code the Claude page may show. The key is checked by its shape
(``claude_key``) and handed on exactly as a pasted one is: straight to GitHub,
never written anywhere. Anything that goes wrong ends in one plain line and the
paste prompt of before.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Final

from pydantic import SecretStr

from tracker.services.setup.claude_key import ask_claude_key, claude_key_problem
from tracker.services.setup.context import SetupContext
from tracker.services.setup.ports import ClaudeCodeState, ClaudeKeyScreen, SetupIO
from tracker.shared.constants.claude import (
    CLAUDE_CODE_SETUP_PAGE,
    CLAUDE_KEY_CHARACTERS,
    CLAUDE_KEY_WAIT_SECONDS,
    CLAUDE_SUBSCRIPTION_KEY_PREFIX,
)
from tracker.shared.constants.github import CLAUDE_TOKEN_SECRET
from tracker.shared.constants.terminal import TERMINAL_CONTROL_PATTERN
from tracker.shared.errors import ClaudeKeyNotMadeError, SourceUnavailableError
from tracker.shared.logging import get_logger

_log = get_logger(__name__)

_CONTROL: Final[re.Pattern[str]] = re.compile(TERMINAL_CONTROL_PATTERN)

#: A key, or the start of one, as it stands on one line of the screen.
_KEY_ON_LINE: Final[re.Pattern[str]] = re.compile(
    rf"{re.escape(CLAUDE_SUBSCRIPTION_KEY_PREFIX)}[A-Za-z0-9_-]*"
)

#: Key characters at the start of a line: the rest of a key that wrapped.
_KEY_REST: Final[re.Pattern[str]] = re.compile(CLAUDE_KEY_CHARACTERS)

_WAIT_MINUTES: Final[int] = round(CLAUDE_KEY_WAIT_SECONDS / 60)

#: The offer to make the key, and the same offer when GitHub already holds one.
_OFFER: Final[str] = "Make the Claude key now? A Claude page opens in your browser: click Authorize"
_OFFER_AGAIN: Final[str] = (
    "GitHub already has a Claude key. Make a new one now? A Claude page opens in your "
    "browser: click Authorize"
)


class _OwnerTold:
    """Words, in Threadline's own lines, what the owner may need while the key is made."""

    def __init__(self, io: SetupIO) -> None:
        """Talk through the set-up's conversation."""
        self._io = io

    def sign_in_address(self, address: str) -> None:
        """Give the sign-in page's address once, for when no page opened."""
        self._io.say(f"If no page opened, open this address: {address}")

    def no_key_yet(self) -> None:
        """Say that a code the Claude page shows can be pasted here."""
        self._io.say("If the Claude page shows a code, paste it here and press Enter.")


class KeyNotTaken(StrEnum):
    """Why a key that ``claude setup-token`` ended with was not taken."""

    STOPPED = "stopped"
    NO_KEY = "no_key"
    NOT_WHOLE = "not_whole"


#: What the owner is told for each, in the line that leads to the paste prompt.
_NOT_TAKEN_REASONS: Final[dict[KeyNotTaken, str]] = {
    KeyNotTaken.STOPPED: "Claude stopped before it made one",
    KeyNotTaken.NO_KEY: "no key came back from Claude",
    KeyNotTaken.NOT_WHOLE: "the key that came back was not whole",
}


def claude_key_for_github(ctx: SetupContext, repository: str | None) -> SecretStr | None:
    """Make the Claude key with Claude Code when it is here, otherwise ask for it.

    Args:
        ctx: The set-up's context.
        repository: The owner's copy on GitHub, when known; a key already
            there turns the offer to make a new one into a "no" by default,
            and that "no" keeps it.

    Returns:
        The key, or ``None`` when GitHub keeps the key it has.

    Raises:
        ValidationFailedError: If every pasted key was not whole.
    """
    has_key = repository is not None and claude_key_on_github(ctx, repository) is True
    if not _claude_code_ready(ctx):
        return ask_claude_key(ctx)
    if _wants_new_key(ctx, has_key=has_key):
        made = _make_claude_key(ctx)
        return made if made is not None else ask_claude_key(ctx)
    if has_key:
        ctx.io.say(f"No new key: GitHub keeps the {CLAUDE_TOKEN_SECRET} it already has.")
        return None
    return ask_claude_key(ctx)


def claude_key_on_github(ctx: SetupContext, repository: str) -> bool | None:
    """Whether GitHub holds the Claude key; ``None`` when it could not be asked."""
    try:
        return CLAUDE_TOKEN_SECRET in ctx.gateways.github.secret_names(repository)
    except SourceUnavailableError:
        return None


def _claude_code_ready(ctx: SetupContext) -> bool:
    """Whether ``claude setup-token`` can be run here; says so when Claude Code is missing."""
    state = ctx.gateways.claude_key_maker.state()
    if state is ClaudeCodeState.MISSING:
        ctx.io.say("Claude Code (the 'claude' command) is not on this computer, so the key")
        ctx.io.say(f"is made by hand. To install Claude Code, see {CLAUDE_CODE_SETUP_PAGE}")
        return False
    return state is not ClaudeCodeState.UNSUPPORTED


def _make_claude_key(ctx: SetupContext) -> SecretStr | None:
    """Run ``claude setup-token`` and take its key; ``None`` to paste it instead."""
    ctx.io.say("A Claude page opens in your browser. Sign in if it asks, then click Authorize.")
    ctx.io.say(f"The set-up waits up to {_WAIT_MINUTES} minutes; the key is never shown.")
    try:
        screen = ctx.gateways.claude_key_maker.make_key(_OwnerTold(ctx.io))
    except ClaudeKeyNotMadeError as error:
        _log.info("claude_key_not_made", reason=error.code)
        return _paste_instead(ctx, error.message)
    return _taken(ctx, screen)


def _wants_new_key(ctx: SetupContext, *, has_key: bool) -> bool:
    """Ask whether to make the key now; "no" is the default when GitHub has one already.

    An express run makes the first key without asking: GitHub needs it, and
    the only other way is pasting it by hand.
    """
    if has_key:
        return ctx.io.confirm(_OFFER_AGAIN, default=False)
    return ctx.session.express or ctx.io.confirm(_OFFER, default=True)


def _taken(ctx: SetupContext, screen: ClaudeKeyScreen) -> SecretStr | None:
    """Take the key from Claude's screen, or say why not and fall back to pasting."""
    key = key_from_screen(screen.text.get_secret_value(), screen.columns)
    if screen.exit_code != 0:
        reason = KeyNotTaken.STOPPED
    elif key is None:
        reason = KeyNotTaken.NO_KEY
    elif claude_key_problem(key) is not None:
        reason = KeyNotTaken.NOT_WHOLE
    else:
        _log.info("claude_key_made")
        ctx.io.say(
            "Got the Claude key. It goes straight to GitHub and is not kept on this computer."
        )
        return SecretStr(key)
    _log.info("claude_key_not_made", reason=reason.value)
    return _paste_instead(ctx, _NOT_TAKEN_REASONS[reason])


def _paste_instead(ctx: SetupContext, reason: str) -> None:
    """Say in one line that the key was not made, before the paste prompt."""
    ctx.io.say(f"The key could not be made here ({reason}). Paste it by hand instead.")


def key_from_screen(text: str, columns: int) -> str | None:
    """Find the subscription key on what ``claude setup-token`` wrote.

    Colours and cursor movements are taken out first. A key that reaches the
    very edge of the screen went on at the start of the next line, so that
    line's key characters are joined on; a shorter line ended the key.

    Args:
        text: Everything it wrote.
        columns: The width of its screen.

    Returns:
        The last key it printed (a screen redrawn shows the same key again),
        or ``None`` when there is none.
    """
    lines = _plain_lines(text)
    found: str | None = None
    for index, line in enumerate(lines):
        for match in _KEY_ON_LINE.finditer(line):
            found = match.group() + _wrapped_rest(lines, index, match.end(), columns)
    return found


def _plain_lines(text: str) -> list[str]:
    """The screen's text without control sequences, one string per line."""
    plain = _CONTROL.sub("", text).replace("\r\n", "\n").replace("\r", "\n")
    return plain.split("\n")


def _wrapped_rest(lines: list[str], index: int, end: int, columns: int) -> str:
    """The part of a key carried on to the lines after ``lines[index]``, if any."""
    rest = ""
    line = lines[index]
    while end == len(line) >= columns and index + 1 < len(lines):
        index += 1
        line = lines[index]
        more = _KEY_REST.match(line)
        if more is None:
            break
        rest += more.group()
        end = more.end()
    return rest
