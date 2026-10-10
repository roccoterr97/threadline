"""Running ``claude setup-token`` so the set-up can take the key it prints.

Claude Code draws its screen with a library that needs a real terminal: on a
plain pipe it stops at once ("Raw mode is not supported"). So the command runs
inside a pseudo-terminal, a terminal made in software whose screen this module
reads. That screen is made very wide, so the key and the sign-in address each
come on one line. The screen itself is shown nowhere: drawn for a window
1,000 characters wide, it is a mess in any real one, and it holds the key.
Only two things are passed on, to a listener that words them for the person:
the sign-in address, for when no browser opened, and, when typing reaches
Claude, a word that no key has come for a while (the Claude page may show a
code to paste). Typing still goes straight to Claude: a pasted code, or Ctrl+C
to stop it. Either way it is stopped after a few minutes, so the set-up can
never hang on it.

Python has no pseudo-terminal on Windows, so there the key is pasted as before.
"""

from __future__ import annotations

import codecs
import os
import re
import select
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final, Protocol

from pydantic import SecretStr

from tracker.shared.constants.claude import (
    CLAUDE_COMMAND,
    CLAUDE_KEY_CODE_HINT_SECONDS,
    CLAUDE_KEY_EXIT_SECONDS,
    CLAUDE_KEY_FAMILY_PREFIX,
    CLAUDE_KEY_POLL_SECONDS,
    CLAUDE_KEY_SCREEN_COLUMNS,
    CLAUDE_KEY_SCREEN_ROWS,
    CLAUDE_KEY_WAIT_SECONDS,
    CLAUDE_NATIVE_INSTALL_PATH,
    CLAUDE_SETUP_TOKEN_ARGUMENTS,
    CLAUDE_SIGN_IN_ADDRESS_WINDOW,
)
from tracker.shared.constants.terminal import TERMINAL_CONTROL_PATTERN, TERMINAL_READ_BYTES
from tracker.shared.errors import ClaudeKeyNotMadeError
from tracker.shared.logging import get_logger

_log = get_logger(__name__)

_CONTROL: Final[re.Pattern[str]] = re.compile(TERMINAL_CONTROL_PATTERN)

#: A web address that has ended: a space, a line break or a control sequence
#: follows it, so the rest of it is not still on its way.
_ADDRESS: Final[re.Pattern[str]] = re.compile(r"https://\S+(?=\s)")

#: What Enter sends in a terminal that turns it into a line break, and what
#: Claude reads as Enter.
_LINE_BREAK: Final[bytes] = b"\n"
_ENTER: Final[bytes] = b"\r"


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


class ClaudeKeyListener(Protocol):
    """Hears what the person may need while ``claude setup-token`` runs unseen."""

    def sign_in_address(self, address: str) -> None:
        """Claude printed its sign-in page's address, for when no browser opened."""
        ...

    def no_key_yet(self) -> None:
        """No key came for a while, and typing reaches Claude: a code may be wanted."""
        ...


class PtyClaudeKeyMaker:
    """Runs ``claude setup-token`` in a pseudo-terminal and hands back what it wrote."""

    def __init__(
        self,
        *,
        keyboard: int | None,
        command: Sequence[str] | None = None,
        columns: int = CLAUDE_KEY_SCREEN_COLUMNS,
        wait_seconds: float = CLAUDE_KEY_WAIT_SECONDS,
        code_hint_seconds: float = CLAUDE_KEY_CODE_HINT_SECONDS,
    ) -> None:
        """Say where typing comes from, and how long to wait.

        Args:
            keyboard: The terminal whose typing goes to Claude; ``None`` for none.
            command: What to run; ``claude setup-token`` when omitted.
            columns: The width of Claude's screen.
            wait_seconds: How long to wait for Claude to finish.
            code_hint_seconds: How long to wait for a key before saying a code
                can be pasted; only said when there is a keyboard.
        """
        self._keyboard = keyboard
        self._command = tuple(command) if command is not None else None
        self._columns = columns
        self._wait_seconds = wait_seconds
        self._code_hint_seconds = code_hint_seconds

    def state(self) -> ClaudeCodeState:
        """Tell whether the key can be made here."""
        if sys.platform == "win32":
            return ClaudeCodeState.UNSUPPORTED
        return ClaudeCodeState.READY if self._arguments() is not None else ClaudeCodeState.MISSING

    def make_key(self, listener: ClaudeKeyListener) -> ClaudeKeyScreen:
        """Run ``claude setup-token`` until it ends, showing none of its screen.

        Args:
            listener: Hears the sign-in address, and when no key came for a while.

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
                text = self._relay(process, terminal, listener)
        finally:
            os.close(terminal)
            exit_code = _ended(process)
        _log.info("claude_setup_token_ended", exit_code=exit_code)
        return ClaudeKeyScreen(text=SecretStr(text), columns=self._columns, exit_code=exit_code)

    def _arguments(self) -> tuple[str, ...] | None:
        """The command line to run, or ``None`` when ``claude`` is not here."""
        if self._command is not None:
            return self._command
        program = find_claude()
        return None if program is None else (program, *CLAUDE_SETUP_TOKEN_ARGUMENTS)

    def _relay(
        self, process: subprocess.Popen[bytes], terminal: int, listener: ClaudeKeyListener
    ) -> str:
        """Read Claude's screen and pass typing in, until its screen closes.

        Raises:
            ClaudeKeyNotMadeError: If it did not finish within the wait.
        """
        screen = _ScreenReader(listener)
        keyboard = self._keyboard
        started = time.monotonic()
        hint_at = None if keyboard is None else started + self._code_hint_seconds
        while True:
            now = time.monotonic()
            if now >= started + self._wait_seconds:
                process.kill()
                message = f"no key came within {round(self._wait_seconds / 60)} minutes"
                raise ClaudeKeyNotMadeError(message)
            if hint_at is not None and now >= hint_at:
                hint_at = None
                listener.no_key_yet()
            sources = [terminal] if keyboard is None else [terminal, keyboard]
            ready = select.select(sources, [], [], CLAUDE_KEY_POLL_SECONDS)[0]
            if keyboard in ready and not _pass_on(keyboard, terminal):
                keyboard = None
            if terminal not in ready:
                if process.poll() is not None:
                    break
                continue
            chunk = _read(terminal)
            if not chunk:
                break
            screen.feed(chunk)
        return screen.finish()


class _ScreenReader:
    """Keeps what Claude wrote, unseen, and spots its sign-in address once."""

    def __init__(self, listener: ClaudeKeyListener) -> None:
        """Start with an empty screen."""
        self._listener = listener
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._written: list[str] = []
        self._unsearched: str | None = ""

    def feed(self, chunk: bytes) -> None:
        """Take the next piece of the screen."""
        text = self._decoder.decode(chunk)
        self._written.append(text)
        self._look_for_address(text)

    def finish(self) -> str:
        """Everything Claude wrote, the key included: never shown or logged."""
        self._written.append(self._decoder.decode(b"", final=True))
        return "".join(self._written)

    def _look_for_address(self, text: str) -> None:
        """Pass the sign-in address on the first time it is whole on the screen."""
        if self._unsearched is None:
            return
        searched = self._unsearched + text
        address = sign_in_address(searched)
        if address is None:
            self._unsearched = searched[-CLAUDE_SIGN_IN_ADDRESS_WINDOW:]
            return
        self._unsearched = None
        self._listener.sign_in_address(address)


def sign_in_address(screen: str) -> str | None:
    """Find the first whole web address on part of Claude's screen.

    Control sequences count as spaces, so one that ends an address ends it
    here too. An address that holds a key is never handed on.

    Args:
        screen: What Claude wrote, or the latest part of it.

    Returns:
        The address, or ``None`` when no whole one is there yet.
    """
    found = _ADDRESS.search(_CONTROL.sub(" ", screen))
    if found is None or CLAUDE_KEY_FAMILY_PREFIX in found.group():
        return None
    return found.group()


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

    The terminal stops waiting for whole lines, and Ctrl+C reaches Claude,
    which stops, rather than stopping the whole set-up. It still shows what is
    typed, as Claude's own screen is not shown, and lines the set-up says still
    start at the left edge.
    """
    if sys.platform == "win32" or keyboard is None or not os.isatty(keyboard):
        yield
        return
    import termios
    import tty

    saved = termios.tcgetattr(keyboard)
    passing_on = termios.tcgetattr(keyboard)
    passing_on[tty.LFLAG] &= ~(termios.ICANON | termios.ISIG | termios.IEXTEN)
    passing_on[tty.IFLAG] &= ~termios.IXON
    passing_on[tty.CC][termios.VMIN] = 1
    passing_on[tty.CC][termios.VTIME] = 0
    termios.tcsetattr(keyboard, termios.TCSADRAIN, passing_on)
    try:
        yield
    finally:
        termios.tcsetattr(keyboard, termios.TCSADRAIN, saved)


def _pass_on(keyboard: int, terminal: int) -> bool:
    """Pass what was typed to Claude; ``False`` once there is nothing more to pass.

    Enter reaches Claude as Enter even where this terminal turns it into a line break.
    """
    try:
        typed = os.read(keyboard, TERMINAL_READ_BYTES)
        if typed:
            os.write(terminal, typed.replace(_LINE_BREAK, _ENTER))
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
