"""Making the Claude key with ``claude setup-token`` instead of pasting it.

The service is tested with a fake key maker. The pseudo-terminal is tested by
running a stand-in ``claude`` (``fixtures/fake_claude.py``) that draws a screen
like the real one: the real command is never run, as it would make a key.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from tests.setup_world import World, make_world
from tests.test_github_setup import CLAUDE_KEY, github_env
from tracker.infrastructure.claude_key_screen import KeyBlanker
from tracker.infrastructure.claude_setup_token import (
    ClaudeCodeState,
    ClaudeKeyScreen,
    PtyClaudeKeyMaker,
)
from tracker.services.setup.claude_key_maker import key_from_screen
from tracker.services.setup.step_github import GitHubStep
from tracker.shared.constants.claude import CLAUDE_CODE_SETUP_PAGE, CLAUDE_KEY_HIDDEN
from tracker.shared.constants.github import CLAUDE_TOKEN_SECRET
from tracker.shared.errors import ClaudeKeyNotMadeError

FAKE_CLAUDE = Path(__file__).parent / "fixtures" / "fake_claude.py"
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


def secret_parts(key: str) -> Iterator[str]:
    """Every stretch of a key's secret part long enough to give it away."""
    secret = key.removeprefix("sk-ant-oat01-")
    return (secret[start : start + 12] for start in range(len(secret) - 11))


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


# --- Blanking the key out ---------------------------------------------------------


def test_the_key_is_blanked_out_wherever_the_output_is_cut() -> None:
    whole = KeyBlanker()
    expected = whole.feed(MADE_SCREEN) + whole.flush()
    for cut in range(len(MADE_SCREEN)):
        blanker = KeyBlanker()
        shown = blanker.feed(MADE_SCREEN[:cut]) + blanker.feed(MADE_SCREEN[cut:]) + blanker.flush()

        assert shown == expected
    assert expected.count(CLAUDE_KEY_HIDDEN) == 1
    assert "sk-ant-" not in expected


def test_a_key_wrapped_onto_a_second_line_is_blanked_on_both() -> None:
    wrapped = f"\x1b[33m{CLAUDE_KEY[:NARROW]}\x1b[39m\r\n\x1b[33m{CLAUDE_KEY[NARROW:]}\x1b[39m\r\n"
    blanker = KeyBlanker()

    shown = blanker.feed(wrapped) + blanker.flush()

    assert not any(part in shown for part in secret_parts(CLAUDE_KEY))


def test_the_start_of_a_word_that_could_begin_a_key_waits_only_until_output_pauses() -> None:
    blanker = KeyBlanker()

    assert blanker.feed("Press Enter or ask") == "Press Enter or a"
    assert blanker.idle() == "sk"


def test_a_key_that_may_go_on_is_held_even_when_output_pauses() -> None:
    blanker = KeyBlanker()

    assert blanker.feed(f"token:\r\n{CLAUDE_KEY[:40]}") == "token:\r\n"
    assert blanker.idle() == ""
    assert blanker.feed(f"{CLAUDE_KEY[40:]}\r\n\r\nDone") == f"{CLAUDE_KEY_HIDDEN}\r\n\r\nDone"


# --- Running claude in a pseudo-terminal --------------------------------------------


def fake_claude(
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
    *,
    columns: int = WIDE,
    keyboard: int | None = None,
    wait_seconds: float = 20.0,
    on_screen: Callable[[str], None] | None = None,
) -> tuple[PtyClaudeKeyMaker, list[str]]:
    """A key maker that runs the stand-in ``claude``, and what it showed."""
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", scenario)
    monkeypatch.setenv("FAKE_CLAUDE_KEY", CLAUDE_KEY)
    shown: list[str] = []
    maker = PtyClaudeKeyMaker(
        screen=on_screen or shown.append,
        keyboard=keyboard,
        command=(sys.executable, str(FAKE_CLAUDE)),
        columns=columns,
        wait_seconds=wait_seconds,
    )
    return maker, shown


def made_key(screen: ClaudeKeyScreen) -> str | None:
    """The key on what the stand-in wrote."""
    return key_from_screen(screen.text.get_secret_value(), screen.columns)


@needs_pseudo_terminal
def test_claude_runs_in_a_wide_terminal_and_its_key_is_taken_but_never_shown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    maker, shown = fake_claude(monkeypatch, "made")

    screen = maker.make_key()

    assert screen.exit_code == 0
    assert made_key(screen) == CLAUDE_KEY
    seen = "".join(shown)
    assert "Long-lived authentication token created successfully!" in seen
    assert CLAUDE_KEY_HIDDEN in seen
    assert not any(part in seen for part in secret_parts(CLAUDE_KEY))


@needs_pseudo_terminal
def test_from_the_set_up_page_claude_still_gets_a_terminal_but_nothing_is_shown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", "made")
    monkeypatch.setenv("FAKE_CLAUDE_KEY", CLAUDE_KEY)
    maker = PtyClaudeKeyMaker(
        screen=None, keyboard=None, command=(sys.executable, str(FAKE_CLAUDE))
    )

    screen = maker.make_key()

    assert screen.exit_code == 0
    assert made_key(screen) == CLAUDE_KEY


@needs_pseudo_terminal
def test_a_key_wrapped_by_a_narrow_terminal_is_joined_and_never_shown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    maker, shown = fake_claude(monkeypatch, "made", columns=NARROW)

    screen = maker.make_key()

    assert made_key(screen) == CLAUDE_KEY
    assert not any(part in "".join(shown) for part in secret_parts(CLAUDE_KEY))


@needs_pseudo_terminal
def test_a_claude_that_fails_says_so_by_its_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    maker, shown = fake_claude(monkeypatch, "fails")

    screen = maker.make_key()

    assert screen.exit_code == 1
    assert made_key(screen) is None
    assert "OAuth error" in "".join(shown)


def run_with_typing(monkeypatch: pytest.MonkeyPatch, keys: bytes) -> ClaudeKeyScreen:
    """Run the stand-in that waits for typing, and type ``keys`` once its prompt shows."""
    typed, keyboard = os.pipe()

    def type_at_prompt(text: str) -> None:
        if "Paste code here" in text:
            os.write(keyboard, keys)

    maker, _ = fake_claude(monkeypatch, "asks", keyboard=typed, on_screen=type_at_prompt)
    try:
        return maker.make_key()
    finally:
        os.close(typed)
        os.close(keyboard)


@needs_pseudo_terminal
def test_typing_reaches_claude_and_ctrl_c_stops_it(monkeypatch: pytest.MonkeyPatch) -> None:
    screen = run_with_typing(monkeypatch, b"\x03")

    assert screen.exit_code == 130
    assert made_key(screen) is None


@needs_pseudo_terminal
def test_enter_typed_for_claude_lets_it_finish(monkeypatch: pytest.MonkeyPatch) -> None:
    screen = run_with_typing(monkeypatch, b"code#state\r")

    assert screen.exit_code == 0
    assert made_key(screen) == CLAUDE_KEY


@needs_pseudo_terminal
def test_a_claude_that_never_finishes_is_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    maker, _ = fake_claude(monkeypatch, "hangs", wait_seconds=1.0)

    with pytest.raises(ClaudeKeyNotMadeError, match="no key came within"):
        maker.make_key()


@needs_pseudo_terminal
def test_a_claude_that_cannot_start_is_reported(tmp_path: Path) -> None:
    maker = PtyClaudeKeyMaker(screen=None, keyboard=None, command=(str(tmp_path / "claude"),))

    with pytest.raises(ClaudeKeyNotMadeError, match="could not be started"):
        maker.make_key()


@needs_pseudo_terminal
def test_without_claude_on_this_computer_the_key_cannot_be_made(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    maker = PtyClaudeKeyMaker(screen=None, keyboard=None)

    assert maker.state() is ClaudeCodeState.MISSING
    with pytest.raises(ClaudeKeyNotMadeError, match="not found"):
        maker.make_key()


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

    assert PtyClaudeKeyMaker(screen=None, keyboard=None).state() is ClaudeCodeState.READY
