"""Blanking out a Claude key in a screen's output before anyone sees it.

``claude setup-token`` prints the key it made. The set-up shows the rest of
that screen, so the person can follow the sign-in, but the key itself must
never reach the window, a log or a chat that reads the window. Output arrives
in pieces of any size, so a key can be cut between two pieces: the end of a
piece that could still be the start of a key is held back until the next piece
settles it. A key wrapped onto a second line is blanked there too; blanking a
little more than the key is harmless, showing any of it is not.
"""

from __future__ import annotations

import re
from typing import Final

from tracker.shared.constants.claude import (
    CLAUDE_KEY_CHARACTERS,
    CLAUDE_KEY_FAMILY_PREFIX,
    CLAUDE_KEY_HIDDEN,
)

#: One terminal control sequence (colour, cursor movement, erasing a line).
_CONTROL: Final[str] = r"\x1b\[[0-?]*[ -/]*[@-~]"

#: A key, with the part a narrow screen wraps onto the following lines.
_KEY: Final[re.Pattern[str]] = re.compile(
    rf"{re.escape(CLAUDE_KEY_FAMILY_PREFIX)}{CLAUDE_KEY_CHARACTERS}"
    rf"(?:(?:{_CONTROL})*\r*\n(?:{_CONTROL})*{CLAUDE_KEY_CHARACTERS})*"
)

#: What may follow a key that is not settled yet: a control sequence, maybe cut
#: short, or line breaks. More key characters could still come after it.
_MAYBE_MORE: Final[re.Pattern[str]] = re.compile(r"(?:\x1b\[[0-?]*[ -/]*[@-~]?|\x1b|\r|\n)*")


class KeyBlanker:
    """Passes a screen's output on with every Claude key replaced by a short notice."""

    def __init__(self) -> None:
        """Start with nothing held back."""
        self._pending = ""

    def feed(self, text: str) -> str:
        """Take the next piece of output.

        Args:
            text: What the screen printed since the last piece.

        Returns:
            What can be shown now, keys blanked; the rest waits for the next piece.
        """
        self._pending += text
        hold, _ = _held_part(self._pending)
        return self._release(hold)

    def idle(self) -> str:
        """Show what was held back when it cannot be part of a key after all.

        Called when no output came for a moment: the start of a word such as
        "sk" at the end of a prompt is shown, a key that may go on is not.

        Returns:
            What can be shown now.
        """
        hold, is_key = _held_part(self._pending)
        return self._release(hold if is_key else len(self._pending))

    def flush(self) -> str:
        """Show everything still held, keys blanked: the output has ended.

        Returns:
            The rest of the output.
        """
        return self._release(len(self._pending))

    def _release(self, upto: int) -> str:
        """Hand over the pending output up to one point, keys blanked."""
        shown, self._pending = self._pending[:upto], self._pending[upto:]
        return _KEY.sub(CLAUDE_KEY_HIDDEN, shown)


def _held_part(text: str) -> tuple[int, bool]:
    """Find where the part that must wait starts.

    Args:
        text: The output not shown yet.

    Returns:
        Where the held part starts (the length of ``text`` when nothing is
        held), and whether it holds a key rather than the start of a word.
    """
    keys = list(_KEY.finditer(text))
    last_key = keys[-1] if keys else None
    if last_key is not None and _MAYBE_MORE.fullmatch(text, last_key.end()):
        return last_key.start(), True
    for length in range(len(CLAUDE_KEY_FAMILY_PREFIX), 0, -1):
        if text.endswith(CLAUDE_KEY_FAMILY_PREFIX[:length]):
            return len(text) - length, False
    return len(text), False
