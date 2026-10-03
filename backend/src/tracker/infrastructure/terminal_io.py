"""The set-up's conversation in a terminal: prompts, the browser, the clipboard."""

from __future__ import annotations

import shutil
import subprocess
import webbrowser
from typing import Final

import typer

#: Clipboard command on a Mac.
CLIPBOARD_COMMAND: Final[str] = "pbcopy"

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
    """Put a value on the clipboard with pbcopy, when this machine has it.

    Args:
        value: What to copy. Never shown.

    Returns:
        ``False`` when there is no clipboard command, or it failed.
    """
    command = shutil.which(CLIPBOARD_COMMAND)
    if command is None:
        return False
    try:
        subprocess.run([command], input=value, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return False
    return True
