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

#: Seconds a clipboard command may take before the next one is tried.
CLIPBOARD_TIMEOUT_SECONDS: Final[float] = 5.0

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

#: Puts back the window's ordinary behaviour after a program that drew in it
#: (``claude setup-token``) ends, even one stopped before it could: the cursor
#: shown, colours reset, and the keyboard and paste modes it may have switched
#: on turned off. A window that never had a mode ignores the code for it.
TERMINAL_RESTORE_SEQUENCE: Final[str] = (
    "\x1b[0m\x1b[?25h\x1b[?2004l\x1b[?1004l\x1b[<u\x1b[>4;0m\r\n"
)
