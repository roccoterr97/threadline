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
