"""The set-up's conversation in a terminal: prompts, the browser, the clipboard.

A hidden prompt on macOS and Linux reads every line of one paste. Python's own
hidden prompt reads one line and throws the rest away, so a key that
``claude setup-token`` wraps over two lines lost its second half without a word.
On Windows the rest stays waiting for the next prompt, which reads it.
"""

from __future__ import annotations

import os
import select
import shutil
import subprocess
import sys
import webbrowser
from collections.abc import Sequence
from typing import Final

import typer

from tracker.shared.constants.terminal import (
    CLIPBOARD_COMMANDS,
    CLIPBOARD_TIMEOUT_SECONDS,
    KEEP_SUGGESTION_ANSWERS,
    PASTE_GAP_SECONDS,
    TERMINAL_READ_BYTES,
)

#: What a pause asks for here; the page asks for a click instead.
PAUSE_SUFFIX: Final[str] = ", press Enter"


class TerminalIO:
    """Talks to the person at the keyboard."""

    def say(self, text: str) -> None:
        """Show one line."""
        typer.echo(text)

    def ask(self, prompt: str, *, default: str | None = None, exact: bool = False) -> str:
        """Ask for a value that may be shown on screen; "y" keeps a suggestion unless ``exact``."""
        answer = str(typer.prompt(prompt, default=default or "", show_default=bool(default)))
        return answer if exact else answer_or_suggestion(answer, default)

    def ask_secret(self, prompt: str) -> str:
        """Ask for a value without showing what is typed, keeping every line of a paste."""
        if sys.platform == "win32" or not sys.stdin.isatty():
            # An empty default lets Enter alone answer, as the prompts promise.
            return str(typer.prompt(prompt, default="", hide_input=True, show_default=False))
        typer.echo(f"{prompt}: ", nl=False)
        try:
            return read_hidden_lines(sys.stdin.fileno())
        finally:
            typer.echo("")

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


def answer_or_suggestion(answer: str, suggestion: str | None) -> str:
    """Read "y", "yes" or "ok" as "keep the suggestion" when one was offered.

    People answer a question such as ``Your time zone [Europe/Paris]:`` with
    "Y" out of habit from the yes/no questions; that means "yes, that one".

    Args:
        answer: What was typed.
        suggestion: The value offered in brackets, if any.

    Returns:
        The suggestion for one of those words, otherwise the answer unchanged.
    """
    if suggestion and answer.strip().lower() in KEEP_SUGGESTION_ANSWERS:
        return suggestion
    return answer


def read_hidden_lines(fd: int, gap_seconds: float = PASTE_GAP_SECONDS) -> str:
    """Read one answer from a terminal without showing it, with every line of a paste.

    The terminal stays line by line, so the person can still correct a typing
    mistake; only its echo is off. After the first line, lines already
    arriving within ``gap_seconds`` belong to the same paste and are kept.

    Args:
        fd: The terminal's file descriptor.
        gap_seconds: How long to wait for another line of the same paste.

    Returns:
        What was typed or pasted, its lines joined by line breaks.

    Raises:
        typer.Abort: If the terminal was closed before an answer came.
    """
    if sys.platform == "win32":  # pragma: no cover - termios exists on macOS and Linux only
        message = "Windows reads a hidden answer with its own prompt"
        raise OSError(message)
    import termios

    saved = termios.tcgetattr(fd)
    quiet = saved[:]
    quiet[3] &= ~termios.ECHO
    termios.tcsetattr(fd, termios.TCSANOW, quiet)
    try:
        chunks = [os.read(fd, TERMINAL_READ_BYTES)]
        if not chunks[0]:
            raise typer.Abort
        while select.select([fd], [], [], gap_seconds)[0]:
            chunk = os.read(fd, TERMINAL_READ_BYTES)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, saved)
    return b"".join(chunks).decode("utf-8", errors="replace").rstrip("\r\n")


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
