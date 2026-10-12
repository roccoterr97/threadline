"""The set-up's conversation in a terminal: prompts, the browser, the clipboard.

A hidden prompt on macOS and Linux reads every line of one paste. Python's own
hidden prompt reads one line and throws the rest away, so a key that
``claude setup-token`` wraps over two lines lost its second half without a word.
On Windows the rest stays waiting for the next prompt, which reads it.

A prompt can also watch the clipboard, so a password or a code copied from a
web page is picked up without being pasted; typing or pasting still works the
whole time. A password is asked hidden, a code shown as it is typed.
"""

from __future__ import annotations

import getpass
import os
import select
import sys
import time
import webbrowser
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from dataclasses import dataclass
from typing import Final

import typer

from tracker.infrastructure.clipboard import copy_to_clipboard, read_clipboard
from tracker.shared.constants.terminal import (
    CLIPBOARD_POLL_SECONDS,
    CLIPBOARD_WATCH_SECONDS,
    KEEP_SUGGESTION_ANSWERS,
    KEY_CHECK_SECONDS,
    PASTE_GAP_SECONDS,
    TERMINAL_READ_BYTES,
)

#: What a pause asks for here; the page asks for a click instead.
PAUSE_SUFFIX: Final[str] = ", press Enter"

#: Said when the clipboard is no longer watched, so a later copy is pasted.
STOPPED_WATCHING: Final[str] = "(Stopped watching the clipboard: paste it here and press Enter.)"

#: How many looks at the clipboard one watch takes at most.
_WATCH_POLLS: Final[int] = round(CLIPBOARD_WATCH_SECONDS / CLIPBOARD_POLL_SECONDS)

#: Looks at the clipboard once: the value now on it when it is the one awaited.
LookAtClipboard = Callable[[], str | None]


@dataclass(frozen=True, slots=True)
class SecretAnswer:
    """An answer that may have come from the clipboard, and where it came from.

    Attributes:
        value: What was typed, pasted or copied. Never shown when it was asked hidden.
        copied: Whether it was picked up from the clipboard rather than typed.
    """

    value: str
    copied: bool


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

    def watches_clipboard(self) -> bool:
        """Whether a hidden question here can pick its answer up from the clipboard."""
        return sys.stdin.isatty() and read_clipboard() is not None

    def ask_secret_or_copied(self, prompt: str, wanted: Callable[[str], bool]) -> SecretAnswer:
        """Ask for a hidden value, or pick it up once a value ``wanted`` accepts is copied.

        Without a terminal or a clipboard this is the plain hidden question.

        Args:
            prompt: The question.
            wanted: Tells the awaited value from anything else on the clipboard.

        Returns:
            The answer, and whether it came from the clipboard.
        """
        return self._typed_or_copied(prompt, wanted, hidden=True)

    def ask_or_copied(self, prompt: str, wanted: Callable[[str], bool]) -> SecretAnswer:
        """Ask for a value shown as typed, or pick it up once a value ``wanted`` accepts is copied.

        Without a terminal or a clipboard this is the plain question.

        Args:
            prompt: The question.
            wanted: Tells the awaited value from anything else on the clipboard.

        Returns:
            The answer, and whether it came from the clipboard.
        """
        return self._typed_or_copied(prompt, wanted, hidden=False)

    def _typed_or_copied(
        self, prompt: str, wanted: Callable[[str], bool], *, hidden: bool
    ) -> SecretAnswer:
        """Watch the clipboard while the answer may be typed, hidden or shown."""
        before = read_clipboard() if sys.stdin.isatty() else None
        if before is None:
            typed = self.ask_secret(prompt) if hidden else self.ask(prompt, exact=True)
            return SecretAnswer(typed, copied=False)
        look = newly_copied(before, wanted, read_clipboard)
        typer.echo(f"{prompt}: ", nl=False)
        answer = SecretAnswer("", copied=True)
        try:
            if sys.platform == "win32":
                answer = _windows_typed_or_copied(look, hidden=hidden)
            else:
                answer = read_hidden_or_copied(sys.stdin.fileno(), look, hidden=hidden)
            return answer
        finally:
            # A shown answer ends with the Enter the person typed; the others need a new line.
            if hidden or answer.copied:
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


def newly_copied(
    before: str, wanted: Callable[[str], bool], read: Callable[[], str | None]
) -> LookAtClipboard:
    """Make a look at the clipboard that finds only a newly copied, awaited value.

    What was already on the clipboard when the watch began is never taken, so
    a password refused a moment ago is not picked up again.

    Args:
        before: The clipboard's text when the watch began.
        wanted: Tells the awaited value from anything else.
        read: Reads the clipboard; ``None`` when it cannot.
    """

    def look() -> str | None:
        text = read()
        if text is None or text == before or not wanted(text):
            return None
        return text

    return look


def wait_for_copy(
    key_pressed: Callable[[float], bool],
    look: LookAtClipboard,
    *,
    polls: int,
    interval: float,
) -> str | None:
    """Watch the clipboard until the awaited value is copied, a key is pressed or time is up.

    Args:
        key_pressed: Waits up to the given seconds; ``True`` once the person types.
        look: One look at the clipboard.
        polls: How many looks at most.
        interval: Seconds listened to the keyboard before each look.

    Returns:
        The copied value, or ``None`` when the person typed or time ran out.
    """
    for _ in range(polls):
        if key_pressed(interval):
            return None
        copied = look()
        if copied is not None:
            return copied
    return None


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
    with _echo_off(fd):
        return _read_lines(fd, gap_seconds)


def read_hidden_or_copied(
    fd: int,
    look: LookAtClipboard,
    *,
    hidden: bool = True,
    polls: int = _WATCH_POLLS,
    interval: float = CLIPBOARD_POLL_SECONDS,
    gap_seconds: float = PASTE_GAP_SECONDS,
) -> SecretAnswer:
    """Read an answer from a terminal, hidden or shown, or pick it up from the clipboard.

    Once the value is picked up, anything typed meanwhile is thrown away, so a
    paste the person was about to make never lands, visible, in the next
    question. When the watch ends without a copy the keyboard is still read.

    Args:
        fd: The terminal's file descriptor.
        look: One look at the clipboard.
        hidden: Whether what is typed stays off the screen.
        polls: How many looks at most.
        interval: Seconds between two looks.
        gap_seconds: How long to wait for another line of the same paste.

    Returns:
        The answer, and whether it came from the clipboard.

    Raises:
        typer.Abort: If the terminal was closed before an answer came.
    """
    quiet: AbstractContextManager[None] = _echo_off(fd) if hidden else nullcontext()
    with quiet:
        copied = wait_for_copy(
            lambda seconds: _readable(fd, seconds), look, polls=polls, interval=interval
        )
        if copied is not None:
            _drop_typed(fd)
            return SecretAnswer(copied, copied=True)
        if not _readable(fd, 0):
            typer.echo("")
            typer.echo(STOPPED_WATCHING)
        return SecretAnswer(_read_lines(fd, gap_seconds), copied=False)


@contextmanager
def _echo_off(fd: int) -> Iterator[None]:
    """Keep the terminal from showing what is typed, and restore it afterwards."""
    if sys.platform == "win32":  # pragma: no cover - termios exists on macOS and Linux only
        message = "Windows reads a hidden answer with its own prompt"
        raise OSError(message)
    import termios

    saved = termios.tcgetattr(fd)
    quiet = saved[:]
    quiet[3] &= ~termios.ECHO
    termios.tcsetattr(fd, termios.TCSANOW, quiet)
    try:
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, saved)


def _read_lines(fd: int, gap_seconds: float) -> str:
    """Read the first line typed and every further line of the same paste."""
    chunks = [os.read(fd, TERMINAL_READ_BYTES)]
    if not chunks[0]:
        raise typer.Abort
    while _readable(fd, gap_seconds):
        chunk = os.read(fd, TERMINAL_READ_BYTES)
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks).decode("utf-8", errors="replace").rstrip("\r\n")


def _readable(fd: int, seconds: float) -> bool:
    """Whether a line is waiting to be read, waiting up to ``seconds`` for one."""
    return bool(select.select([fd], [], [], seconds)[0])


def _drop_typed(fd: int) -> None:
    """Throw away whatever was typed but not yet read."""
    if sys.platform == "win32":  # pragma: no cover - termios exists on macOS and Linux only
        message = "Windows drops typed keys with its own console calls"
        raise OSError(message)
    import termios

    termios.tcflush(fd, termios.TCIFLUSH)


def _windows_typed_or_copied(  # pragma: no cover - Windows only
    look: LookAtClipboard, *, hidden: bool
) -> SecretAnswer:
    """Windows' version of :func:`read_hidden_or_copied`, through its console calls."""
    if sys.platform != "win32":
        message = "only Windows has its console calls"
        raise OSError(message)
    import msvcrt

    copied = wait_for_copy(
        _key_pressed_within,
        look,
        polls=_WATCH_POLLS,
        interval=CLIPBOARD_POLL_SECONDS,
    )
    if copied is not None:
        while msvcrt.kbhit():
            msvcrt.getwch()
        return SecretAnswer(copied, copied=True)
    if not msvcrt.kbhit():
        typer.echo("")
        typer.echo(STOPPED_WATCHING)
    if not hidden:
        # input reads the keys already pressed too, and shows them.
        return SecretAnswer(input(""), copied=False)
    # getpass reads the keys already pressed, and shows none of them.
    return SecretAnswer(getpass.getpass(""), copied=False)


def _key_pressed_within(seconds: float) -> bool:  # pragma: no cover - Windows only
    """Wait up to ``seconds`` for a key press on the Windows console."""
    if sys.platform != "win32":
        message = "only Windows has its console calls"
        raise OSError(message)
    import msvcrt

    deadline = time.monotonic() + seconds
    while not msvcrt.kbhit():
        if time.monotonic() >= deadline:
            return False
        time.sleep(KEY_CHECK_SECONDS)
    return True
