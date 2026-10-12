"""Fixed values for talking to the person at the keyboard, on any computer.

None of it differs between machines of the same kind, so it is code rather than
configuration. Which of these commands exists is found out when it is needed.
"""

from __future__ import annotations

from typing import Final

#: Clipboard commands, tried in this order until one works; each reads the
#: value on its standard input. ``pbcopy`` is the Mac's, ``clip`` Windows',
#: ``wl-copy`` Linux with Wayland's, ``xclip`` and ``xsel`` Linux with X11's.
CLIPBOARD_COMMANDS: Final[tuple[tuple[str, ...], ...]] = (
    ("pbcopy",),
    ("clip",),
    ("wl-copy",),
    ("xclip", "-selection", "clipboard"),
    ("xsel", "--clipboard", "--input"),
)

#: Commands that print the clipboard's text, tried in the same way: the Mac's,
#: Windows' (PowerShell, present on every Windows), then Linux's.
CLIPBOARD_READ_COMMANDS: Final[tuple[tuple[str, ...], ...]] = (
    ("pbpaste",),
    ("powershell", "-NoProfile", "-NonInteractive", "-Command", "Get-Clipboard -Raw"),
    ("wl-paste", "--no-newline"),
    ("xclip", "-selection", "clipboard", "-out"),
    ("xsel", "--clipboard", "--output"),
)

#: Seconds a clipboard command may take before the next one is tried.
CLIPBOARD_TIMEOUT_SECONDS: Final[float] = 5.0

#: Seconds between two looks at the clipboard while a copied value is awaited.
CLIPBOARD_POLL_SECONDS: Final[float] = 1.0

#: Seconds the clipboard is watched for a copied value before only the
#: keyboard is listened to; enough to make an app password, not to linger.
CLIPBOARD_WATCH_SECONDS: Final[float] = 300.0

#: Seconds between two checks for a key press on Windows while the clipboard
#: is watched; short enough that typing never feels held up.
KEY_CHECK_SECONDS: Final[float] = 0.05

#: Answers to a question with a suggestion in brackets that mean "keep the
#: suggestion": people type them out of habit from the yes/no questions.
#: Compared without regard to case or surrounding spaces.
KEEP_SUGGESTION_ANSWERS: Final[frozenset[str]] = frozenset({"y", "yes", "ok"})

#: Seconds a hidden prompt waits, after a line, for more lines of the same
#: paste. A key that ``claude setup-token`` wraps over two lines arrives as two
#: lines at once; a person typing never presses Enter that fast.
PASTE_GAP_SECONDS: Final[float] = 0.2

#: Most bytes read from the terminal at once: well over one pasted line.
TERMINAL_READ_BYTES: Final[int] = 4096

#: One terminal control sequence: a colour, a cursor movement, erasing a line,
#: a link around some text, or a two-character code.
TERMINAL_CONTROL_PATTERN: Final[str] = (
    r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-Z\\-_]"
)
