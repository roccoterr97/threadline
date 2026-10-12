"""The computer's clipboard: putting a value on it and reading what is on it.

Each system has its own commands, so the first one that works is used:
``pbcopy``/``pbpaste`` on a Mac, ``clip`` and PowerShell's ``Get-Clipboard`` on
Windows, ``wl-copy``/``wl-paste`` on Linux with Wayland and ``xclip`` or
``xsel`` on Linux with X11. What is copied or read never goes on a command
line and is never shown or logged.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence

from tracker.shared.constants.terminal import (
    CLIPBOARD_COMMANDS,
    CLIPBOARD_READ_COMMANDS,
    CLIPBOARD_TIMEOUT_SECONDS,
)


def copy_to_clipboard(value: str) -> bool:
    """Put a value on the clipboard with the first clipboard command that works.

    The value goes on the command's standard input, never on its command
    line, and nothing it prints is shown.

    Args:
        value: What to copy. Never shown.

    Returns:
        ``False`` when this computer has no clipboard command that worked.
    """
    return any(_copy_with(command, value) for command in CLIPBOARD_COMMANDS)


def read_clipboard() -> str | None:
    """Read the text on the clipboard with the first command that works.

    Returns:
        The clipboard's text, possibly empty, or ``None`` when this computer
        has no clipboard command that worked.
    """
    for command in CLIPBOARD_READ_COMMANDS:
        text = _read_with(command)
        if text is not None:
            return text
    return None


def _copy_with(command: Sequence[str], value: str) -> bool:
    """Try one clipboard command; ``False`` when it is missing or failed."""
    program = shutil.which(command[0])
    if program is None:
        return False
    # Output goes nowhere rather than to a pipe: xclip stays behind to hold the
    # clipboard, and waiting for its pipe to close would wait for ever.
    try:
        subprocess.run(
            [program, *command[1:]],
            input=value,
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=CLIPBOARD_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False
    return True


def _read_with(command: Sequence[str]) -> str | None:
    """Read with one clipboard command; ``None`` when it is missing or failed."""
    program = shutil.which(command[0])
    if program is None:
        return None
    try:
        finished = subprocess.run(
            [program, *command[1:]],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            check=True,
            timeout=CLIPBOARD_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return finished.stdout
