"""Running on Windows as on macOS and Linux: time zone, clipboard, files and commands.

Nothing here starts a real program: every command is answered by a stand-in,
so these tests give the same result on any computer.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from structlog.testing import capture_logs

from tracker.infrastructure import github_cli, local_time_zone, terminal_io
from tracker.infrastructure.env_file import EnvFile
from tracker.infrastructure.github_cli import TextFile, run_command
from tracker.infrastructure.local_time_zone import (
    detect_time_zone,
    read_windows_zone,
    zone_from_windows_name,
)
from tracker.infrastructure.terminal_io import TerminalIO
from tracker.shared.constants.terminal import CLIPBOARD_COMMANDS
from tracker.shared.constants.windows_time_zones import WINDOWS_TO_IANA
from tracker.shared.time_zones import canonical_zone_name


class FakeRun:
    """Stands in for ``subprocess.run``: records each call and answers from a script."""

    def __init__(
        self,
        *,
        stdout: str = "",
        returncode: int = 0,
        fail_for: frozenset[str] = frozenset(),
        error: Exception | None = None,
    ) -> None:
        self.calls: list[tuple[list[str], dict[str, Any]]] = []
        self.stdout = stdout
        self.returncode = returncode
        self.fail_for = fail_for
        self.error = error

    def __call__(
        self, arguments: Sequence[str], **options: Any
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append((list(arguments), options))
        if self.error is not None:
            raise self.error
        if Path(arguments[0]).name in self.fail_for:
            raise subprocess.CalledProcessError(1, list(arguments))
        return subprocess.CompletedProcess(list(arguments), self.returncode, self.stdout, "")


def only_programs(*names: str) -> Any:
    """A ``shutil.which`` that finds only the named programs, in a made-up folder."""
    return lambda name: f"C:/Tools/{name}.exe" if name in names else None


# --- The computer's time zone on Windows -----------------------------------------


@pytest.mark.parametrize(
    ("windows_name", "expected"),
    [
        ("Romance Standard Time", "Europe/Paris"),
        ("W. Europe Standard Time\r\n", "Europe/Berlin"),
        ("Pacific Standard Time_dstoff", "America/Los_Angeles"),
        ("India Standard Time", "Asia/Kolkata"),
        ("UTC", "UTC"),
    ],
)
def test_a_windows_zone_name_becomes_the_standard_name(windows_name: str, expected: str) -> None:
    assert zone_from_windows_name(windows_name) == expected


def test_an_unknown_or_empty_windows_zone_name_has_no_standard_name() -> None:
    assert zone_from_windows_name("Mars Standard Time") is None
    assert zone_from_windows_name("") is None


def test_every_zone_in_the_windows_table_is_a_real_zone() -> None:
    unknown = [name for name in WINDOWS_TO_IANA.values() if canonical_zone_name(name) != name]

    assert unknown == []


def test_windows_is_asked_only_when_tz_and_the_link_say_nothing(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    asked: list[bool] = []

    def windows() -> str:
        asked.append(True)
        return "Tokyo Standard Time"

    assert detect_time_zone(missing, {}, windows) == "Asia/Tokyo"
    assert detect_time_zone(missing, {"TZ": "Europe/Rome"}, windows) == "Europe/Rome"
    assert asked == [True]


def test_an_unknown_windows_zone_falls_back_to_utc(tmp_path: Path) -> None:
    assert detect_time_zone(tmp_path / "missing", {}, lambda: "Mars Standard Time") == "UTC"
    assert detect_time_zone(tmp_path / "missing", {}, lambda: "") == "UTC"


def test_tzutil_is_asked_for_the_zone(monkeypatch: pytest.MonkeyPatch) -> None:
    run = FakeRun(stdout="Romance Standard Time")
    monkeypatch.setattr(local_time_zone.shutil, "which", only_programs("tzutil"))
    monkeypatch.setattr(local_time_zone.subprocess, "run", run)

    assert read_windows_zone() == "Romance Standard Time"
    assert run.calls[0][0] == ["C:/Tools/tzutil.exe", "/g"]


def test_without_tzutil_nothing_is_run(monkeypatch: pytest.MonkeyPatch) -> None:
    run = FakeRun()
    monkeypatch.setattr(local_time_zone.shutil, "which", only_programs())
    monkeypatch.setattr(local_time_zone.subprocess, "run", run)

    assert read_windows_zone() == ""
    assert run.calls == []


@pytest.mark.parametrize(
    "run",
    [
        FakeRun(stdout="Romance Standard Time", returncode=1),
        FakeRun(error=OSError("cannot start")),
        FakeRun(error=subprocess.TimeoutExpired("tzutil", 5)),
    ],
)
def test_a_tzutil_that_fails_gives_no_zone(monkeypatch: pytest.MonkeyPatch, run: FakeRun) -> None:
    monkeypatch.setattr(local_time_zone.shutil, "which", only_programs("tzutil"))
    monkeypatch.setattr(local_time_zone.subprocess, "run", run)

    assert read_windows_zone() == ""


# --- The clipboard on every system ---------------------------------------------


def test_the_mac_clipboard_comes_first(monkeypatch: pytest.MonkeyPatch) -> None:
    run = FakeRun()
    monkeypatch.setattr(terminal_io.shutil, "which", only_programs("pbcopy", "clip", "xclip"))
    monkeypatch.setattr(terminal_io.subprocess, "run", run)

    assert TerminalIO().copy("value") is True
    assert [arguments for arguments, _ in run.calls] == [["C:/Tools/pbcopy.exe"]]
    assert run.calls[0][1]["input"] == "value"


def test_windows_copies_with_clip(monkeypatch: pytest.MonkeyPatch) -> None:
    run = FakeRun()
    monkeypatch.setattr(terminal_io.shutil, "which", only_programs("clip"))
    monkeypatch.setattr(terminal_io.subprocess, "run", run)

    assert TerminalIO().copy("value") is True
    assert run.calls[0][0] == ["C:/Tools/clip.exe"]


def test_linux_moves_on_to_the_next_clipboard_when_one_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun(fail_for=frozenset({"wl-copy.exe"}))
    monkeypatch.setattr(terminal_io.shutil, "which", only_programs("wl-copy", "xclip", "xsel"))
    monkeypatch.setattr(terminal_io.subprocess, "run", run)

    assert TerminalIO().copy("value") is True
    assert [arguments for arguments, _ in run.calls] == [
        ["C:/Tools/wl-copy.exe"],
        ["C:/Tools/xclip.exe", "-selection", "clipboard"],
    ]


def test_the_value_never_goes_on_the_command_line_and_nothing_is_shown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun()
    monkeypatch.setattr(terminal_io.shutil, "which", only_programs("xsel"))
    monkeypatch.setattr(terminal_io.subprocess, "run", run)

    TerminalIO().copy("hidden-value")

    arguments, options = run.calls[0]
    assert "hidden-value" not in arguments
    assert options["stdout"] == subprocess.DEVNULL
    assert options["stderr"] == subprocess.DEVNULL


def test_when_every_clipboard_fails_copy_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    names = frozenset(f"{command[0]}.exe" for command in CLIPBOARD_COMMANDS)
    run = FakeRun(fail_for=names)
    monkeypatch.setattr(
        terminal_io.shutil, "which", only_programs(*(command[0] for command in CLIPBOARD_COMMANDS))
    )
    monkeypatch.setattr(terminal_io.subprocess, "run", run)

    assert TerminalIO().copy("value") is False
    assert len(run.calls) == len(CLIPBOARD_COMMANDS)


def test_a_clipboard_that_hangs_is_given_up(monkeypatch: pytest.MonkeyPatch) -> None:
    run = FakeRun(error=subprocess.TimeoutExpired("xclip", 5))
    monkeypatch.setattr(terminal_io.shutil, "which", only_programs("xclip"))
    monkeypatch.setattr(terminal_io.subprocess, "run", run)

    assert TerminalIO().copy("value") is False


# --- The .env file -----------------------------------------------------------------


def test_a_disk_without_permissions_still_gets_the_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(self: Path, mode: int) -> None:
        raise OSError("this disk keeps no permissions")

    monkeypatch.setattr(Path, "chmod", refuse)
    path = tmp_path / ".env"

    with capture_logs() as logs:
        EnvFile(path).set("SUPABASE_URL", "https://abcdefghijklmnop.supabase.co")

    assert EnvFile(path).get("SUPABASE_URL") == "https://abcdefghijklmnop.supabase.co"
    assert logs[-1]["event"] == "env_file_permissions_not_set"
    assert "this disk" not in repr(logs)


def test_env_lines_end_the_same_way_on_every_system(tmp_path: Path) -> None:
    path = tmp_path / ".env"

    EnvFile(path).set("A", "1")
    EnvFile(path).set("B", "2")

    assert path.read_bytes() == b"A=1\nB=2\n"


# --- gh and git ---------------------------------------------------------------------


def test_commands_are_looked_up_first_so_gh_exe_is_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = FakeRun(stdout="you/threadline\n")
    monkeypatch.setattr(github_cli.subprocess, "run", run)

    status, output = run_command(tmp_path, only_programs("gh"))(["gh", "repo", "view"], "input")

    assert (status, output) == (0, "you/threadline\n")
    arguments, options = run.calls[0]
    assert arguments == ["C:/Tools/gh.exe", "repo", "view"]
    assert options["encoding"] == "utf-8"
    assert options["input"] == "input"
    assert options["cwd"] == tmp_path


def test_a_program_that_is_not_found_is_still_tried_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = FakeRun(error=FileNotFoundError("git"))
    monkeypatch.setattr(github_cli.subprocess, "run", run)

    with capture_logs() as logs:
        result = run_command(tmp_path, only_programs())(["git", "status"], None)

    assert result == (1, "")
    assert run.calls[0][0] == ["git", "status"]
    assert logs[-1]["event"] == "command_not_run"


def test_the_workflow_file_keeps_the_line_endings_git_stores(tmp_path: Path) -> None:
    path = tmp_path / "threadline-run.yml"

    TextFile(path).write("on:\n  schedule:\n")

    assert path.read_bytes() == b"on:\n  schedule:\n"
