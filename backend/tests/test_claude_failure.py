"""Why Claude stopped a run on GitHub: read from the action's record, said in one plain line."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tracker.cli.main import build_cli
from tracker.services.runs.claude_failure import explain_execution_file, explain_messages

#: What Claude Code said when the first run failed, as far as the log showed it.
SEEN_ON_GITHUB: dict[str, object] = {
    "type": "result",
    "subtype": "success",
    "is_error": True,
    "duration_ms": 1964,
    "num_turns": 1,
    "total_cost_usd": 0,
    "modelUsage": {},
}

#: Words Claude wrote while reading mail, which must never be repeated.
PRIVATE_WORDS = "Dear Rocco, the offer from Example Ltd is attached"


def _record(result: dict[str, object], error: str | None = None) -> list[object]:
    """A run's messages: the start, Claude's last message, the result."""
    assistant: dict[str, object] = {"type": "assistant", "message": {"content": PRIVATE_WORDS}}
    if error is not None:
        assistant["error"] = error
    return [{"type": "system", "subtype": "init"}, assistant, result]


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        ("authentication_failed", "Claude did not accept the key saved on GitHub"),
        ("billing_error", "does not come from an active Claude subscription"),
        ("rate_limit", "usage limit was reached"),
        ("overloaded", "busy or down for a moment"),
        ("server_error", "busy or down for a moment"),
        ("model_not_found", "would not use its model"),
    ],
)
def test_claudes_error_code_names_the_reason(error: str, expected: str) -> None:
    line = explain_messages(_record(SEEN_ON_GITHUB | {"result": PRIVATE_WORDS}, error))

    assert expected in line
    assert PRIVATE_WORDS not in line
    assert "\n" not in line


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, "did not accept the key"),
        (403, "did not accept the key"),
        (402, "active Claude subscription"),
        (429, "usage limit"),
        (529, "busy or down"),
    ],
)
def test_without_a_code_the_services_status_names_the_reason(status: int, expected: str) -> None:
    line = explain_messages(_record(SEEN_ON_GITHUB | {"api_error_status": status}))

    assert expected in line


@pytest.mark.parametrize(
    ("said", "expected"),
    [
        ("Invalid API key · Please run /login", "did not accept the key"),
        ("Failed to authenticate: OAuth token revoked", "did not accept the key"),
        ("OAuth token has expired. Please obtain a new token", "did not accept the key"),
        ("Credit balance is too low", "active Claude subscription"),
        ("Claude AI usage limit reached|1760000000", "usage limit"),
        ("API Error: 529 Overloaded", "busy or down"),
    ],
)
def test_without_code_or_status_the_error_line_names_the_reason(said: str, expected: str) -> None:
    line = explain_messages(_record(SEEN_ON_GITHUB | {"result": said}))

    assert expected in line


def test_a_refused_key_says_how_to_make_and_save_a_new_one() -> None:
    line = explain_messages(_record(SEEN_ON_GITHUB, "authentication_failed"))

    assert "CLAUDE_CODE_OAUTH_TOKEN" in line
    assert "'claude setup-token'" in line
    assert "'uv run tracker setup github'" in line


def test_an_unknown_service_error_is_shown_cut_short_and_without_any_key() -> None:
    said = "API Error: 400 bad request for sk-ant-oat01-abcdefghijk " + "x" * 300 + "\nmore"

    line = explain_messages(_record(SEEN_ON_GITHUB | {"result": said}))

    assert line.startswith("Claude stopped with an error: API Error: 400 bad request for [removed]")
    assert "sk-ant-" not in line
    assert "more" not in line
    assert len(line) < 400
    assert "If the next run stops the same way" in line


def test_words_that_are_not_a_service_error_are_never_shown() -> None:
    line = explain_messages(_record(SEEN_ON_GITHUB | {"result": PRIVATE_WORDS}))

    assert line.startswith("Claude stopped with an error.")
    assert PRIVATE_WORDS not in line


def test_using_every_allowed_step_is_said_plainly() -> None:
    result = {"type": "result", "subtype": "error_max_turns", "is_error": True}

    assert "every step it is allowed" in explain_messages(_record(result))


def test_a_record_without_a_result_says_claude_stopped_before_saying_why() -> None:
    assert "before it could say why" in explain_messages([{"type": "system"}])


def test_a_missing_or_broken_record_says_claude_stopped_before_saying_why(tmp_path: Path) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")

    for path in (None, tmp_path / "absent.json", broken):
        assert "before it could say why" in explain_execution_file(path)


def test_the_command_prints_one_line_from_the_file(tmp_path: Path) -> None:
    record = tmp_path / "claude-execution-output.json"
    record.write_text(json.dumps(_record(SEEN_ON_GITHUB, "authentication_failed")), "utf-8")

    result = CliRunner().invoke(build_cli(), ["run", "why-claude-stopped", str(record)])

    assert result.exit_code == 0
    assert result.stdout.strip().startswith("Claude did not accept the key saved on GitHub")
    assert len(result.stdout.strip().splitlines()) == 1


def test_the_command_without_a_file_still_prints_a_line() -> None:
    result = CliRunner().invoke(build_cli(), ["run", "why-claude-stopped", ""])

    assert result.exit_code == 0
    assert "before it could say why" in result.stdout
