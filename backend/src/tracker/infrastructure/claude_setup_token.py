"""Running ``claude setup-token`` so the set-up can take the key it prints.

Claude Code draws its screen with a library that needs a real terminal: on a
plain pipe it stops at once ("Raw mode is not supported"). So the command runs
inside a pseudo-terminal, a terminal made in software whose screen this module
reads. That screen is made very wide, so the key comes on one line. When the
set-up runs in a terminal, the person sees Claude's screen and can type into
it (to paste a sign-in code, or press Ctrl+C to stop), but never the key: it
is blanked out before it reaches the window (``claude_key_screen``). On the
set-up's page it still runs inside a pseudo-terminal, as it must, but its
screen is shown nowhere: the browser sign-in alone finishes the job. Either
way it is stopped after a few minutes, so the set-up can never hang on it.

Python has no pseudo-terminal on Windows, so there the key is pasted as before.
"""

from __future__ import annotations

import codecs
import os
import select
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pydantic import SecretStr

from tracker.infrastructure.claude_key_screen import KeyBlanker
from tracker.shared.constants.claude import (
    CLAUDE_COMMAND,
    CLAUDE_KEY_EXIT_SECONDS,
    CLAUDE_KEY_POLL_SECONDS,
    CLAUDE_KEY_SCREEN_COLUMNS,
    CLAUDE_KEY_SCREEN_ROWS,
    CLAUDE_KEY_WAIT_SECONDS,
    CLAUDE_NATIVE_INSTALL_PATH,
    CLAUDE_SETUP_TOKEN_ARGUMENTS,
)
from tracker.shared.constants.terminal import TERMINAL_READ_BYTES, TERMINAL_RESTORE_SEQUENCE
from tracker.shared.errors import ClaudeKeyNotMadeError
from tracker.shared.logging import get_logger

_log = get_logger(__name__)


class ClaudeCodeState(StrEnum):
    """Whether this computer can make the Claude key for the set-up."""

    READY = "ready"
    MISSING = "missing"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class ClaudeKeyScreen:
    """What ``claude setup-token`` wrote, and how it ended.

    Attributes:
        text: Everything it wrote, the key included: never shown or logged.
        columns: The width of its screen, where a longer line would wrap.
        exit_code: How it ended; 0 when it finished as planned.
    """

    text: SecretStr
    columns: int
    exit_code: int


def find_claude() -> str | None:
    """Find the ``claude`` command, also where Anthropic's installer puts it.

    Returns:
        Its path, or ``None`` when Claude Code is not on this computer.
    """
    found = shutil.which(CLAUDE_COMMAND)
    if found is not None:
        return found
    installed = Path.home().joinpath(*CLAUDE_NATIVE_INSTALL_PATH)
    return str(installed) if installed.is_file() and os.access(installed, os.X_OK) else None


def write_to_terminal(text: str) -> None:
    """Show text in this terminal at once, as a screen is drawn."""
    sys.stdout.write(text)
    sys.stdout.flush()


class PtyClaudeKeyMaker:
    """Runs ``claude setup-token`` in a pseudo-terminal and hands back what it wrote."""

    def __init__(
        self,
        *,
        screen: Callable[[str], None] | None,
        keyboard: int | None,
        command: Sequence[str] | None = None,
        columns: int = CLAUDE_KEY_SCREEN_COLUMNS,
        wait_seconds: float = CLAUDE_KEY_WAIT_SECONDS,
    ) -> None:
        """Say where Claude's screen is shown and where typing comes from.

        Args:
            screen: Shows Claude's screen, the key blanked; ``None`` shows nothing.
            keyboard: The terminal whose typing goes to Claude; ``None`` for none.
            command: What to run; ``claude setup-token`` when omitted.
            columns: The width of Claude's screen.
            wait_seconds: How long to wait for Claude to finish.
        """
        self._screen = screen
        self._keyboard = keyboard
        self._command = tuple(command) if command is not None else None
        self._columns = columns
        self._wait_seconds = wait_seconds

    def state(self) -> ClaudeCodeState:
        """Tell whether the key can be made here."""
        if sys.platform == "win32":
            return ClaudeCodeState.UNSUPPORTED
        return ClaudeCodeState.READY if self._arguments() is not None else ClaudeCodeState.MISSING

    def make_key(self) -> ClaudeKeyScreen:
        """Run ``claude setup-token`` until it ends, showing its screen with the key blanked.

        Returns:
            What it wrote, the key included, and how it ended.

        Raises:
            ClaudeKeyNotMadeError: If it could not be started, or did not end in time.
        """
        arguments = self._arguments()
        if sys.platform == "win32" or arguments is None:
            message = "Claude Code was not found"
            raise ClaudeKeyNotMadeError(message)
        process, terminal = _start(arguments, self._columns)
        try:
            with _typing_passed_on(self._keyboard):
                text = self._relay(process, terminal)
        finally:
            os.close(terminal)
            exit_code = _ended(process)
            self._show(TERMINAL_RESTORE_SEQUENCE)
        _log.info("claude_setup_token_ended", exit_code=exit_code)
        return ClaudeKeyScreen(text=SecretStr(text), columns=self._columns, exit_code=exit_code)

    def _arguments(self) -> tuple[str, ...] | None:
        """The command line to run, or ``None`` when ``claude`` is not here."""
        if self._command is not None:
            return self._command
        program = find_claude()
        return None if program is None else (program, *CLAUDE_SETUP_TOKEN_ARGUMENTS)

    def _relay(self, process: subprocess.Popen[bytes], terminal: int) -> str:
        """Pass Claude's screen on and typing in, until its screen closes.

        Raises:
            ClaudeKeyNotMadeError: If it did not finish within the wait.
        """
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        blanker = KeyBlanker()
        written: list[str] = []
        keyboard = self._keyboard
        deadline = time.monotonic() + self._wait_seconds
        while True:
            if time.monotonic() >= deadline:
                process.kill()
                message = f"no key came within {round(self._wait_seconds / 60)} minutes"
                raise ClaudeKeyNotMadeError(message)
            sources = [terminal] if keyboard is None else [terminal, keyboard]
            ready = select.select(sources, [], [], CLAUDE_KEY_POLL_SECONDS)[0]
            if keyboard in ready and not _pass_on(keyboard, terminal):
                keyboard = None
            if terminal not in ready:
                if process.poll() is not None:
                    break
                self._show(blanker.idle())
                continue
            chunk = _read(terminal)
            if not chunk:
                break
            written.append(decoder.decode(chunk))
            self._show(blanker.feed(written[-1]))
        written.append(decoder.decode(b"", final=True))
        self._show(blanker.feed(written[-1]) + blanker.flush())
        return "".join(written)

    def _show(self, text: str) -> None:
        """Show text on Claude's screen, when there is one."""
        if text and self._screen is not None:
            self._screen(text)


def _start(arguments: Sequence[str], columns: int) -> tuple[subprocess.Popen[bytes], int]:
    """Start the command in a new pseudo-terminal of a given width.

    Returns:
        The running command, and this side of its terminal.

    Raises:
        ClaudeKeyNotMadeError: If it could not be started, or on Windows,
            which has no pseudo-terminal.
    """
    if sys.platform == "win32":  # pragma: no cover - never started on Windows
        message = "Windows has no pseudo-terminal for Claude Code"
        raise ClaudeKeyNotMadeError(message)
    terminal, follower = os.openpty()
    try:
        _set_size(follower, columns)
        process = subprocess.Popen(  # noqa: S603 - claude, found on this computer, no shell
            list(arguments),
            stdin=follower,
            stdout=follower,
            stderr=follower,
            start_new_session=True,
            close_fds=True,
        )
    except OSError as error:
        os.close(terminal)
        _log.warning("claude_setup_token_not_started", error=type(error).__name__)
        message = "Claude Code could not be started"
        raise ClaudeKeyNotMadeError(message) from None
    finally:
        os.close(follower)
    return process, terminal


def _set_size(follower: int, columns: int) -> None:
    """Give a pseudo-terminal its size, which Claude reads to lay its screen out."""
    if sys.platform == "win32":  # pragma: no cover - never started on Windows
        return
    import fcntl
    import struct
    import termios

    size = struct.pack("HHHH", CLAUDE_KEY_SCREEN_ROWS, columns, 0, 0)
    fcntl.ioctl(follower, termios.TIOCSWINSZ, size)


@contextmanager
def _typing_passed_on(keyboard: int | None) -> Iterator[None]:
    """Hand every key press straight on while Claude runs, then put the terminal back.

    The terminal stops reading whole lines and stops showing typing itself:
    Claude's own screen shows what is typed, and Ctrl+C reaches Claude, which
    stops, rather than stopping the whole set-up.
    """
    if sys.platform == "win32" or keyboard is None or not os.isatty(keyboard):
        yield
        return
    import termios
    import tty

    saved = termios.tcgetattr(keyboard)
    tty.setraw(keyboard)
    try:
        yield
    finally:
        termios.tcsetattr(keyboard, termios.TCSADRAIN, saved)


def _pass_on(keyboard: int, terminal: int) -> bool:
    """Pass what was typed to Claude; ``False`` once there is nothing more to pass."""
    try:
        typed = os.read(keyboard, TERMINAL_READ_BYTES)
        if typed:
            os.write(terminal, typed)
    except OSError:
        return False
    return bool(typed)


def _read(terminal: int) -> bytes:
    """Read what Claude wrote; empty once its screen is closed.

    Linux answers a read on a closed pseudo-terminal with an error, macOS
    with nothing; both mean the same here.
    """
    try:
        return os.read(terminal, TERMINAL_READ_BYTES)
    except OSError:
        return b""


def _ended(process: subprocess.Popen[bytes]) -> int:
    """Wait a moment for the command to end, stop it if it does not, and say how it ended."""
    try:
        return process.wait(timeout=CLAUDE_KEY_EXIT_SECONDS)
    except subprocess.TimeoutExpired:
        _log.info("claude_setup_token_stopped")
        process.kill()
        return process.wait()
