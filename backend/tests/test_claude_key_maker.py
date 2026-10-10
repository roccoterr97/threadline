"""Making the Claude key with ``claude setup-token`` instead of pasting it.

The service is tested with a fake key maker. The pseudo-terminal is tested by
running a stand-in ``claude`` (``fixtures/fake_claude.py``) that draws a screen
like the real one: the real command is never run, as it would make a key.
Claude's screen is never shown, so what reaches the owner is only what the
listener is told: the sign-in address, and that a code can be pasted.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from tests.fixtures.fake_claude import SIGN_IN_ADDRESS
from tests.setup_world import World, make_world
from tests.test_github_setup import CLAUDE_KEY, github_env
from tracker.infrastructure.claude_setup_token import (
    ClaudeCodeState,
    ClaudeKeyScreen,
    PtyClaudeKeyMaker,
    sign_in_address,
)
from tracker.services.setup.claude_key_maker import key_from_screen
from tracker.services.setup.step_github import GitHubStep
from tracker.shared.constants.claude import CLAUDE_CODE_SETUP_PAGE
from tracker.shared.constants.github import CLAUDE_TOKEN_SECRET
from tracker.shared.errors import ClaudeKeyNotMadeError

FAKE_CLAUDE = Path(__file__).parent / "fixtures" / "fake_claude.py"
ADDRESS_LINE = f"If no page opened, open this address: {SIGN_IN_ADDRESS}"
CODE_HINT = "If the Claude page shows a code, paste it here and press Enter."
WIDE = 1000
NARROW = 60
#: Claude's screen when it made the key, as the real one draws it (colours included).
MADE_SCREEN = (
    "\x1b[2mWelcome to Claude Code\x1b[22m\r\n"
    "\x1b[32m✓ Long-lived authentication token created successfully!\x1b[39m\r\n\r\n"
    "Your OAuth token (valid for 1 year):\r\n\r\n"
    f"\x1b[33m{CLAUDE_KEY}\x1b[39m\r\n\r\n"
    "\x1b[2mStore this token securely. You won't be able to see it again.\x1b[22m\r\n"
)

needs_pseudo_terminal = pytest.mark.skipif(
    sys.platform == "win32", reason="Windows has no pseudo-terminal; the key is pasted there"
)


def claude_world(
    answers: list[str | bool], state: ClaudeCodeState = ClaudeCodeState.READY
) -> World:
    """The GitHub step's world, with Claude Code on the computer."""
    world = make_world(answers, github_env())
    world.claude.state_now = state
    world.claude.screen = MADE_SCREEN
    return world


def secret_on_github(world: World) -> str | None:
    """The Claude key the step saved on GitHub, if any."""
    return world.github.secrets.get(CLAUDE_TOKEN_SECRET)


# --- The GitHub step ------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_key_claude_made_is_handed_to_github_without_a_paste() -> None:
    world = claude_world([True, True, False])

    await GitHubStep().run(world.context())

    assert secret_on_github(world) == CLAUDE_KEY
    assert world.claude.runs == 1
    assert world.io.secret_prompts == []
    assert CLAUDE_KEY not in world.io.text()
    assert "click Authorize" in world.io.text()
    assert any(line.startswith("Got the Claude key.") for line in world.io.said)


@pytest.mark.asyncio
async def test_the_owner_sees_only_threadlines_lines_with_the_address_once() -> None:
    world = claude_world([True, True, False])
    world.claude.address = SIGN_IN_ADDRESS
    world.claude.slow = True

    await GitHubStep().run(world.context())

    assert world.io.said.count(ADDRESS_LINE) == 1
    assert CODE_HINT in world.io.said
    assert "Welcome to Claude Code" not in world.io.text()
    assert "Long-lived authentication token" not in world.io.text()
    assert secret_on_github(world) == CLAUDE_KEY


@pytest.mark.asyncio
async def test_a_key_split_over_two_lines_of_a_narrow_screen_is_joined() -> None:
    world = claude_world([True, True, False])
    world.claude.columns = NARROW
    world.claude.screen = MADE_SCREEN.replace(
        CLAUDE_KEY, f"{CLAUDE_KEY[:NARROW]}\x1b[39m\r\n\x1b[33m{CLAUDE_KEY[NARROW:]}"
    )

    await GitHubStep().run(world.context())

    assert secret_on_github(world) == CLAUDE_KEY


@pytest.mark.parametrize(
    ("screen", "exit_code", "said"),
    [
        (MADE_SCREEN.replace(CLAUDE_KEY, ""), 0, "no key came back from Claude"),
        (MADE_SCREEN, 1, "Claude stopped before it made one"),
        (
            MADE_SCREEN.replace(CLAUDE_KEY, CLAUDE_KEY[:60]),
            0,
            "the key that came back was not whole",
        ),
    ],
    ids=["no key", "stopped", "cut short"],
)
@pytest.mark.asyncio
async def test_a_run_without_a_usable_key_falls_back_to_pasting(
    screen: str, exit_code: int, said: str
) -> None:
    world = claude_world([True, CLAUDE_KEY, True, False])
    world.claude.screen = screen
    world.claude.exit_code = exit_code

    await GitHubStep().run(world.context())

    assert f"The key could not be made here ({said}). Paste it by hand instead." in world.io.said
    assert len(world.io.secret_prompts) == 1
    assert secret_on_github(world) == CLAUDE_KEY


@pytest.mark.asyncio
async def test_a_claude_that_could_not_finish_falls_back_to_pasting() -> None:
    world = claude_world([True, CLAUDE_KEY, True, False])
    world.claude.error = ClaudeKeyNotMadeError("no key came within 5 minutes")

    await GitHubStep().run(world.context())

    assert any("(no key came within 5 minutes)" in line for line in world.io.said)
    assert secret_on_github(world) == CLAUDE_KEY


@pytest.mark.asyncio
async def test_without_claude_code_the_key_is_pasted_and_the_install_page_named() -> None:
    world = claude_world([CLAUDE_KEY, True, False], ClaudeCodeState.MISSING)

    await GitHubStep().run(world.context())

    assert world.claude.runs == 0
    assert any(CLAUDE_CODE_SETUP_PAGE in line for line in world.io.said)
    assert secret_on_github(world) == CLAUDE_KEY


@pytest.mark.asyncio
async def test_where_the_key_cannot_be_made_the_paste_prompt_comes_straight_away() -> None:
    world = claude_world([CLAUDE_KEY, True, False], ClaudeCodeState.UNSUPPORTED)

    await GitHubStep().run(world.context())

    assert world.claude.runs == 0
    assert not any("could not be made" in line for line in world.io.said)
    assert secret_on_github(world) == CLAUDE_KEY


@pytest.mark.asyncio
async def test_saying_no_to_making_the_key_asks_for_it_instead() -> None:
    world = claude_world([False, CLAUDE_KEY, True, False])

    await GitHubStep().run(world.context())

    assert world.claude.runs == 0
    assert secret_on_github(world) == CLAUDE_KEY


@pytest.mark.asyncio
async def test_a_key_already_on_github_is_kept_unless_a_new_one_is_wanted() -> None:
    world = claude_world(["", True, False])
    world.github.secrets = {CLAUDE_TOKEN_SECRET: "the-old-key"}

    await GitHubStep().run(world.context())

    assert world.claude.runs == 0
    assert secret_on_github(world) == "the-old-key"
    assert world.io.secret_prompts == []
    assert "GitHub keeps the" in world.io.text()


# --- Finding the key on the screen ------------------------------------------------


def test_the_key_is_found_among_colours_and_redrawn_screens() -> None:
    redrawn = MADE_SCREEN + "\x1b[2K\x1b[1A\x1b[2K\x1b[G" + MADE_SCREEN

    assert key_from_screen(redrawn, WIDE) == CLAUDE_KEY


def test_a_key_at_the_screen_edge_goes_on_at_the_start_of_the_next_line() -> None:
    screen = f"{CLAUDE_KEY[:NARROW]}\r\n{CLAUDE_KEY[NARROW:]}\r\n\r\nStore this token"

    assert key_from_screen(screen, NARROW) == CLAUDE_KEY


def test_a_line_shorter_than_the_screen_ends_the_key() -> None:
    screen = f"{CLAUDE_KEY}\r\nStore this token"

    assert key_from_screen(screen, WIDE) == CLAUDE_KEY


def test_a_screen_without_a_key_has_none() -> None:
    assert (
        key_from_screen("Use this token by setting: CLAUDE_CODE_OAUTH_TOKEN=<token>", WIDE) is None
    )


# --- Finding the sign-in address ------------------------------------------------


def test_the_address_is_found_inside_a_link_and_colours() -> None:
    screen = (
        "\x1b[2mBrowser didn't open? Use the url below to sign in\x1b[22m\r\n\r\n"
        f"\x1b]8;;{SIGN_IN_ADDRESS}\x07\x1b[34m{SIGN_IN_ADDRESS}\x1b[39m\x1b]8;;\x07\r\n"
    )

    assert sign_in_address(screen) == SIGN_IN_ADDRESS


def test_an_address_still_arriving_is_not_found_yet() -> None:
    assert sign_in_address(f"sign in\r\n{SIGN_IN_ADDRESS[:50]}") is None


def test_an_address_holding_a_key_is_never_handed_on() -> None:
    assert sign_in_address(f"https://example.com/?token={CLAUDE_KEY}\r\n") is None


# --- Running claude in a pseudo-terminal --------------------------------------------


@dataclass
class Listener:
    """Hears what the key maker passes on, and can act when the address comes."""

    on_address: Callable[[], None] | None = None
    addresses: list[str] = field(default_factory=list)
    hints: int = 0

    def sign_in_address(self, address: str) -> None:
        self.addresses.append(address)
        if self.on_address is not None:
            self.on_address()

    def no_key_yet(self) -> None:
        self.hints += 1


def fake_claude(
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
    *,
    columns: int = WIDE,
    keyboard: int | None = None,
    wait_seconds: float = 20.0,
    code_hint_seconds: float = 30.0,
) -> PtyClaudeKeyMaker:
    """A key maker that runs the stand-in ``claude``."""
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", scenario)
    monkeypatch.setenv("FAKE_CLAUDE_KEY", CLAUDE_KEY)
    return PtyClaudeKeyMaker(
        keyboard=keyboard,
        command=(sys.executable, str(FAKE_CLAUDE)),
        columns=columns,
        wait_seconds=wait_seconds,
        code_hint_seconds=code_hint_seconds,
    )


def made_key(screen: ClaudeKeyScreen) -> str | None:
    """The key on what the stand-in wrote."""
    return key_from_screen(screen.text.get_secret_value(), screen.columns)


@needs_pseudo_terminal
def test_claude_runs_in_a_wide_terminal_and_only_its_address_is_passed_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listener = Listener()

    screen = fake_claude(monkeypatch, "made").make_key(listener)

    assert screen.exit_code == 0
    assert made_key(screen) == CLAUDE_KEY
    assert listener.addresses == [SIGN_IN_ADDRESS]
    assert listener.hints == 0


@needs_pseudo_terminal
def test_a_key_wrapped_by_a_narrow_terminal_is_joined(monkeypatch: pytest.MonkeyPatch) -> None:
    screen = fake_claude(monkeypatch, "made", columns=NARROW).make_key(Listener())

    assert made_key(screen) == CLAUDE_KEY


@needs_pseudo_terminal
def test_a_claude_that_fails_says_so_by_its_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    screen = fake_claude(monkeypatch, "fails").make_key(Listener())

    assert screen.exit_code == 1
    assert made_key(screen) is None


def run_with_typing(monkeypatch: pytest.MonkeyPatch, keys: bytes) -> ClaudeKeyScreen:
    """Run the stand-in that waits for typing, and type ``keys`` once it shows its address."""
    typed, keyboard = os.pipe()

    def type_keys() -> None:
        os.write(keyboard, keys)

    maker = fake_claude(monkeypatch, "asks", keyboard=typed)
    try:
        return maker.make_key(Listener(on_address=type_keys))
    finally:
        os.close(typed)
        os.close(keyboard)


@needs_pseudo_terminal
def test_typing_reaches_claude_and_ctrl_c_stops_it(monkeypatch: pytest.MonkeyPatch) -> None:
    screen = run_with_typing(monkeypatch, b"\x03")

    assert screen.exit_code == 130
    assert made_key(screen) is None


@needs_pseudo_terminal
@pytest.mark.parametrize("enter", [b"\r", b"\n"], ids=["return", "line break"])
def test_a_code_and_enter_typed_for_claude_let_it_finish(
    monkeypatch: pytest.MonkeyPatch, enter: bytes
) -> None:
    screen = run_with_typing(monkeypatch, b"code#state" + enter)

    assert screen.exit_code == 0
    assert made_key(screen) == CLAUDE_KEY


@needs_pseudo_terminal
def test_a_claude_that_never_finishes_is_stopped_after_one_hint_to_paste_a_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    typed, keyboard = os.pipe()
    listener = Listener()
    maker = fake_claude(
        monkeypatch, "hangs", keyboard=typed, wait_seconds=1.0, code_hint_seconds=0.2
    )
    try:
        with pytest.raises(ClaudeKeyNotMadeError, match="no key came within"):
            maker.make_key(listener)
    finally:
        os.close(typed)
        os.close(keyboard)

    assert listener.hints == 1


@needs_pseudo_terminal
def test_from_the_set_up_page_nobody_is_told_to_paste_a_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listener = Listener()
    maker = fake_claude(monkeypatch, "hangs", wait_seconds=1.0, code_hint_seconds=0.2)

    with pytest.raises(ClaudeKeyNotMadeError):
        maker.make_key(listener)

    assert listener.hints == 0
    assert listener.addresses == [SIGN_IN_ADDRESS]


@needs_pseudo_terminal
def test_a_claude_that_cannot_start_is_reported(tmp_path: Path) -> None:
    maker = PtyClaudeKeyMaker(keyboard=None, command=(str(tmp_path / "claude"),))

    with pytest.raises(ClaudeKeyNotMadeError, match="could not be started"):
        maker.make_key(Listener())


@needs_pseudo_terminal
def test_without_claude_on_this_computer_the_key_cannot_be_made(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    maker = PtyClaudeKeyMaker(keyboard=None)

    assert maker.state() is ClaudeCodeState.MISSING
    with pytest.raises(ClaudeKeyNotMadeError, match="not found"):
        maker.make_key(Listener())


@needs_pseudo_terminal
def test_claude_where_its_installer_puts_it_is_found_off_the_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    installed = tmp_path / ".local" / "bin" / "claude"
    installed.parent.mkdir(parents=True)
    installed.write_text("#!/bin/sh\n")
    installed.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path / "elsewhere"))
    monkeypatch.setenv("HOME", str(tmp_path))

    assert PtyClaudeKeyMaker(keyboard=None).state() is ClaudeCodeState.READY
