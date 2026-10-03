"""The workflow's gate, run for real: bash, a stand-in ``gh`` and a ``sleep`` that does not wait.

The gate decides whether a daily run and a refresh may go ahead side by side.
These tests run its script as GitHub would, with every required secret present
and GitHub's answers scripted, so its decisions are checked rather than read.
The stand-in ``sleep`` moves bash's own clock (``SECONDS``) on instead of
waiting, so the gate's sense of elapsed time is tested without real time passing.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import pytest
import yaml

from tracker.shared.constants.github import REQUIRED_SECRETS, WORKFLOW_FILE

WORKFLOW: Final[dict[Any, Any]] = yaml.safe_load(WORKFLOW_FILE.read_text(encoding="utf-8"))
JOB: Final[dict[str, Any]] = WORKFLOW["jobs"]["run"]
GATE: Final[str] = next(step for step in JOB["steps"] if step.get("id") == "gate")["run"]
RECIPE_STEP: Final[dict[str, Any]] = next(
    step for step in JOB["steps"] if step.get("name") == "Run the recipe with Claude"
)

#: Time a daily run's limit must leave over beyond its worst case, so that a
#: slow set-up or a slow GitHub never cuts a morning's recipe short.
DAILY_SLACK_MINUTES: Final[int] = 10

#: The stand-in ``gh``: answers from a script of replies, one line per call.
#: ``fail`` makes that call fail the way an API hiccup does; ``hang`` ends it
#: the way ``timeout`` ends a lookup that hung (status 124); anything else is
#: printed as the answer, numbers and nonsense alike. The last reply repeats
#: once the script runs out.
_FAKE_GH: Final[str] = """#!/bin/bash
echo "$*" >> "$FAKE_DIR/gh-calls"
calls=$(wc -l < "$FAKE_DIR/gh-calls")
reply=$(sed -n "${calls}p" "$FAKE_DIR/gh-replies")
if [ -z "$reply" ]; then reply=$(tail -n 1 "$FAKE_DIR/gh-replies"); fi
if [ "$reply" = fail ]; then echo "HTTP 502: Server Error" >&2; exit 1; fi
if [ "$reply" = hang ]; then exit 124; fi
echo "$reply"
"""

#: The stand-in ``timeout``: notes the limit it was given, then runs the command.
_FAKE_TIMEOUT: Final[str] = """#!/bin/bash
echo "$1" >> "$FAKE_DIR/timeouts"
shift
exec "$@"
"""

#: The stand-in ``sleep``, put in front of the gate as a shell function: it
#: notes the wait and moves bash's clock on by it (or by ``FAKE_SECONDS_PER_SLEEP``
#: when set, standing in for slow lookups) instead of waiting. Inside a lookup,
#: which runs in a subshell, the clock it moves is the subshell's.
_FAKE_SLEEP: Final[str] = """sleep() {
  echo "$1" >> "$FAKE_DIR/sleeps"
  SECONDS=$((SECONDS + ${FAKE_SECONDS_PER_SLEEP:-$1}))
}
"""

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="the gate is a bash script")


@dataclass(frozen=True, slots=True)
class GateRun:
    """What one run of the gate printed, decided and asked GitHub."""

    stdout: str
    outputs: dict[str, str]
    gh_calls: int
    sleeps: list[int]
    timeouts: list[int]


def _install(directory: Path, name: str, text: str) -> None:
    path = directory / name
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


def _numbers(path: Path) -> list[int]:
    """The numbers a stand-in noted, one per line; none when it was never called."""
    return [int(line) for line in path.read_text(encoding="utf-8").split()] if path.exists() else []


def run_gate(
    tmp_path: Path,
    mode: str,
    replies: list[str],
    *,
    seconds_per_sleep: int | None = None,
    pipefail: bool = False,
) -> GateRun:
    """Run the gate in one mode, with GitHub answering ``replies`` in turn.

    Args:
        tmp_path: Where the stand-ins keep their notes.
        mode: ``daily`` or ``refresh``.
        replies: GitHub's answers, in turn (see :data:`_FAKE_GH`).
        seconds_per_sleep: How far each wait moves the clock, when not by
            what it was asked to wait.
        pipefail: Also run with ``-o pipefail``, as ``shell: bash`` would.
    """
    tools = tmp_path / "bin"
    tools.mkdir()
    _install(tools, "gh", _FAKE_GH)
    _install(tools, "timeout", _FAKE_TIMEOUT)
    (tmp_path / "gh-replies").write_text("\n".join(replies) + "\n", encoding="utf-8")
    output = tmp_path / "github-output"
    output.touch()
    environment = {
        "PATH": f"{tools}{os.pathsep}{os.environ['PATH']}",
        "FAKE_DIR": str(tmp_path),
        "GITHUB_OUTPUT": str(output),
        "MODE": mode,
        "RUN_ID": "1001",
        **dict.fromkeys(REQUIRED_SECRETS, "set"),
    }
    if seconds_per_sleep is not None:
        environment["FAKE_SECONDS_PER_SLEEP"] = str(seconds_per_sleep)
    # GitHub runs a step's script with "bash -e"; so does this test.
    flags = ["-e", "-o", "pipefail"] if pipefail else ["-e"]
    finished = subprocess.run(
        ["bash", *flags, "-c", _FAKE_SLEEP + GATE],
        env=environment,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    calls = tmp_path / "gh-calls"
    return GateRun(
        stdout=finished.stdout,
        outputs=dict(
            line.split("=", 1) for line in output.read_text(encoding="utf-8").splitlines()
        ),
        gh_calls=len(calls.read_text(encoding="utf-8").splitlines()) if calls.exists() else 0,
        sleeps=_numbers(tmp_path / "sleeps"),
        timeouts=_numbers(tmp_path / "timeouts"),
    )


def _gate_number(name: str) -> int:
    """A number the gate's script sets, such as ``wait_limit_seconds``."""
    found = re.search(rf"^\s*{name}=(\d+)$", GATE, flags=re.MULTILINE)
    assert found is not None, name
    return int(found.group(1))


def _job_timeouts() -> tuple[int, int]:
    """The job's time limit for a refresh and for a daily run, in minutes."""
    found = re.fullmatch(
        r"\$\{\{ inputs\.mode == 'refresh' && (\d+) \|\| (\d+) \}\}", JOB["timeout-minutes"]
    )
    assert found is not None
    return int(found.group(1)), int(found.group(2))


# --- a refresh ----------------------------------------------------------------------


def test_a_refresh_goes_ahead_when_nothing_else_is_going(tmp_path: Path) -> None:
    gate = run_gate(tmp_path, "refresh", ["0"])

    assert gate.outputs == {"ready": "true", "mode": "refresh", "trigger": "refresh"}
    assert gate.gh_calls == 1


def test_a_refresh_stops_while_the_daily_run_is_going(tmp_path: Path) -> None:
    gate = run_gate(tmp_path, "refresh", ["1"])

    assert gate.outputs == {"ready": "false"}
    assert "The daily run is going" in gate.stdout


def test_a_refresh_asks_again_after_a_hiccup(tmp_path: Path) -> None:
    gate = run_gate(tmp_path, "refresh", ["fail", "0"])

    assert gate.outputs["ready"] == "true"
    assert gate.gh_calls == 2


def test_a_refresh_stops_when_github_cannot_say_what_is_going(tmp_path: Path) -> None:
    """An error is never read as "nothing is going": the refresh steps aside."""
    gate = run_gate(tmp_path, "refresh", ["fail"])

    assert gate.outputs == {"ready": "false"}
    assert gate.gh_calls == _gate_number("lookup_attempts")
    assert "could not say whether the daily run is going" in gate.stdout


@pytest.mark.parametrize("pipefail", [False, True])
@pytest.mark.parametrize("unclear", ["hang", "not a number"])
def test_a_refresh_never_reads_a_hang_or_nonsense_as_nothing_going(
    tmp_path: Path, unclear: str, *, pipefail: bool
) -> None:
    gate = run_gate(tmp_path, "refresh", [unclear], pipefail=pipefail)

    assert gate.outputs == {"ready": "false"}
    assert gate.gh_calls == _gate_number("lookup_attempts")


def test_every_lookup_is_cut_off_after_its_time_limit(tmp_path: Path) -> None:
    gate = run_gate(tmp_path, "refresh", ["hang", "fail", "0"])

    assert gate.outputs["ready"] == "true"
    assert gate.timeouts == [_gate_number("lookup_timeout_seconds")] * gate.gh_calls


# --- a daily run --------------------------------------------------------------------


def test_a_daily_run_goes_ahead_when_no_refresh_is_going(tmp_path: Path) -> None:
    gate = run_gate(tmp_path, "daily", ["0"])

    assert gate.outputs == {"ready": "true", "mode": "daily", "trigger": "github"}
    assert gate.sleeps == []


def test_a_daily_run_waits_for_a_refresh_to_finish(tmp_path: Path) -> None:
    gate = run_gate(tmp_path, "daily", ["1", "1", "0"])

    assert gate.outputs["ready"] == "true"
    assert gate.sleeps == [_gate_number("poll_seconds")] * 2


@pytest.mark.parametrize("pipefail", [False, True])
@pytest.mark.parametrize("unclear", ["fail", "hang", "not a number"])
def test_a_daily_run_keeps_asking_when_github_cannot_say(
    tmp_path: Path, unclear: str, *, pipefail: bool
) -> None:
    """Not knowing is never "nothing is going": the daily run waits and asks again."""
    attempts = _gate_number("lookup_attempts")
    gate = run_gate(tmp_path, "daily", [unclear] * attempts + ["0"], pipefail=pipefail)

    assert gate.outputs["ready"] == "true"
    assert gate.gh_calls == attempts + 1
    assert gate.sleeps[-1] == _gate_number("poll_seconds")
    assert "asking again" in gate.stdout
    assert "::warning::" not in gate.stdout


@pytest.mark.parametrize("pipefail", [False, True])
def test_a_daily_run_never_skips_the_morning_when_github_never_says(
    tmp_path: Path, *, pipefail: bool
) -> None:
    # Each wait stands for a lookup and a pause that took 20 minutes in all, so
    # the 55-minute wait is used up after three of them.
    gate = run_gate(tmp_path, "daily", ["fail"], seconds_per_sleep=1200, pipefail=pipefail)

    poll = _gate_number("poll_seconds")
    assert gate.outputs["ready"] == "true"
    assert gate.sleeps.count(poll) == 3
    assert "::warning::GitHub could not say whether a refresh is going" in gate.stdout


def test_a_daily_run_stops_waiting_once_any_refresh_must_be_over(tmp_path: Path) -> None:
    gate = run_gate(tmp_path, "daily", ["1"])

    polls = _gate_number("wait_limit_seconds") // _gate_number("poll_seconds")
    assert gate.outputs["ready"] == "true"
    assert gate.sleeps == [_gate_number("poll_seconds")] * polls
    assert "::warning::A refresh still looked busy" in gate.stdout


def test_the_time_lookups_take_counts_towards_the_wait(tmp_path: Path) -> None:
    """The wait is measured on the clock, not by adding up the pauses."""
    gate = run_gate(tmp_path, "daily", ["1"], seconds_per_sleep=600)

    assert gate.outputs["ready"] == "true"
    assert len(gate.sleeps) == -(-_gate_number("wait_limit_seconds") // 600)
    assert "::warning::A refresh still looked busy" in gate.stdout


# --- the numbers agree --------------------------------------------------------------


def test_the_daily_run_waits_at_least_as_long_as_a_refresh_can_live() -> None:
    refresh_limit, _ = _job_timeouts()

    assert _gate_number("wait_limit_seconds") >= refresh_limit * 60


def _longest_lookup_seconds() -> int:
    """How long one lookup can take: every attempt cut off, with the pauses between."""
    attempts = _gate_number("lookup_attempts")
    return attempts * _gate_number("lookup_timeout_seconds") + (attempts - 1) * _gate_number(
        "lookup_pause_seconds"
    )


def test_a_refresh_has_time_to_ask_github_and_then_run_the_whole_recipe() -> None:
    refresh_limit, _ = _job_timeouts()
    recipe_limit = RECIPE_STEP["timeout-minutes"]

    assert _longest_lookup_seconds() + recipe_limit * 60 < refresh_limit * 60


def test_a_daily_run_has_time_to_wait_and_then_run_the_whole_recipe_with_time_to_spare() -> None:
    refresh_limit, daily_limit = _job_timeouts()
    # The wait can run over its limit by one pause and one last lookup.
    gate_at_most = (
        _gate_number("wait_limit_seconds")
        + _gate_number("poll_seconds")
        + _longest_lookup_seconds()
    )
    # After the gate, a daily run needs what a whole refresh may take.
    needed = gate_at_most + refresh_limit * 60

    assert daily_limit * 60 - needed >= DAILY_SLACK_MINUTES * 60
