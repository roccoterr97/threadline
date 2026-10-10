"""A stand-in for ``claude setup-token``, drawing a screen like the real one.

It never signs in anywhere. ``FAKE_CLAUDE_SCENARIO`` says how it ends:

* ``made``: a banner, the line saying the key was made, then the key in colour,
  wrapped at the terminal's width as the real screen does, then the closing lines.
* ``no_key``: everything but the key, ending as if all went well.
* ``fails``: an error line, ending with code 1.
* ``asks``: waits for typing, as the real one does for a pasted sign-in code:
  Enter makes the key, Ctrl+C stops with code 130.
* ``hangs``: waits for ever, as when nobody clicks Authorize.

``FAKE_CLAUDE_KEY`` is the key it prints.
"""

from __future__ import annotations

import os
import sys
import time

YELLOW = "\x1b[33m"
GREEN = "\x1b[32m"
DIM = "\x1b[2m"
RESET = "\x1b[39m\x1b[22m"
CTRL_C = b"\x03"
ENTER = b"\r"


def show(text: str) -> None:
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def show_key(key: str) -> None:
    width = os.get_terminal_size(sys.stdout.fileno()).columns
    for start in range(0, len(key), width):
        show(f"{YELLOW}{key[start : start + width]}{RESET}")


def made(key: str) -> None:
    show("")
    show(f"{GREEN}✓ Long-lived authentication token created successfully!{RESET}")
    show("")
    show("Your OAuth token (valid for 1 year):")
    show("")
    show_key(key)
    show("")
    show(f"{DIM}Store this token securely. You won't be able to see it again.{RESET}")
    show("")
    show(f"{DIM}Use this token by setting: export CLAUDE_CODE_OAUTH_TOKEN=<token>{RESET}")


def wait_for_typing(key: str) -> int:
    if sys.platform == "win32":  # the tests that type into it skip Windows
        return 1
    import termios
    import tty

    saved = termios.tcgetattr(0)
    tty.setraw(0)
    try:
        show("Paste code here if prompted > ")
        while True:
            typed = os.read(0, 1)
            if typed in (CTRL_C, b""):
                return 130
            if typed == ENTER:
                break
    finally:
        termios.tcsetattr(0, termios.TCSADRAIN, saved)
    made(key)
    return 0


def main() -> int:
    scenario = os.environ.get("FAKE_CLAUDE_SCENARIO", "made")
    key = os.environ.get("FAKE_CLAUDE_KEY", "")
    show(f"{DIM}Welcome to Claude Code{RESET}")
    show("⠋ Opening browser to sign in…")
    if scenario == "made":
        made(key)
    elif scenario == "no_key":
        show(f"{GREEN}✓ Done.{RESET}")
    elif scenario == "fails":
        show("\x1b[31mOAuth error: Failed to exchange authorization code for access token.\x1b[39m")
        return 1
    elif scenario == "asks":
        return wait_for_typing(key)
    elif scenario == "hangs":
        time.sleep(3600)
    return 0


if __name__ == "__main__":
    sys.exit(main())
