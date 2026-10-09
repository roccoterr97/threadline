"""The set-up's conversation in a terminal: prompts, the browser, the clipboard."""

from __future__ import annotations

import shutil
import subprocess
import webbrowser
from collections.abc import Sequence
from typing import Final

import typer

from tracker.shared.constants.terminal import CLIPBOARD_COMMANDS, CLIPBOARD_TIMEOUT_SECONDS

#: What a pause asks for here; the page asks for a click instead.
PAUSE_SUFFIX: Final[str] = ", press Enter"


class TerminalIO:
    """Talks to the person at the keyboard."""

    def say(self, text: str) -> None:
        """Show one line."""
        typer.echo(text)

    def ask(self, prompt: str, *, default: str | None = None) -> str:
        """Ask for a value that may be shown on screen."""
        return str(typer.prompt(prompt, default=default or "", show_default=bool(default)))

    def ask_secret(self, prompt: str) -> str:
        """Ask for a value without showing what is typed."""
        return str(typer.prompt(prompt, hide_input=True))

    def confirm(self, prompt: str, *, default: bool) -> bool:
        """Ask a yes/no question."""
        return typer.confirm(prompt, default=default)

    def pause(self, prompt: str) -> None:
        """Wait until the person presses Enter."""
        typer.prompt(f"{prompt}{PAUSE_SUFFIX}", default="", show_default=False, prompt_suffix=" ")

    def open_page(self, url: str) -> None:
        """Open a page in the browser, and always show its address too."""
        typer.echo(f"  Opening {url}")
        try:
            opened = webbrowser.open(url)
        except webbrowser.Error:
            opened = False
        if not opened:
            typer.echo("  (No browser could be opened here: open that address yourself.)")

    def copy(self, value: str) -> bool:
        """Put a value on the clipboard, when this machine has one."""
        return copy_to_clipboard(value)


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
