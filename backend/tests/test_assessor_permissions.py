"""The assessor reads hostile mail, so the session may write nowhere but ``work/``.

A message that talks the assistant into writing ``backend/src/tracker/__init__.py``
would have the next ``uv run tracker`` command run attacker code with the
secrets in its environment. These tests keep the permission files, the
workflow and the assessor's own page saying the same narrow thing.
"""

from __future__ import annotations

import json
import re
import shlex
from typing import Any, Final

import pytest
import yaml

from tracker.shared.constants.assessment import REPOSITORY_ROOT, RESULT_DIRECTORY
from tracker.shared.constants.github import WORKFLOW_FILE

SETTINGS: Final[dict[str, Any]] = json.loads(
    (REPOSITORY_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8")
)
ALLOWED: Final[list[str]] = SETTINGS["permissions"]["allow"]
ASSESSOR_PAGE: Final[str] = (
    REPOSITORY_ROOT / ".claude" / "agents" / "conversation-assessor.md"
).read_text(encoding="utf-8")

#: The one rule that lets the assessor leave its verdict files; ``/`` is the repository root.
WORK_RULE: Final[str] = "Edit(/work/**)"

#: Every place a write could turn into code that runs, or into instructions that are followed.
PROTECTED_RULES: Final[tuple[str, ...]] = (
    "Edit(/backend/**)",
    "Edit(/frontend/**)",
    "Edit(/website/**)",
    "Edit(/supabase/**)",
    "Edit(/docs/**)",
    "Edit(/profile/**)",
    "Edit(/.claude/**)",
    "Edit(/.github/**)",
    "Edit(/.*)",
    "Edit(/*.md)",
    "Edit(/LICENSE)",
    "Edit(/install.sh)",
    "Edit(/install.ps1)",
)


def _flag(arguments: str, name: str) -> list[str]:
    """The comma-separated rules after one command-line flag."""
    words = shlex.split(arguments)
    return words[words.index(name) + 1].split(",")


def _workflow_arguments() -> str:
    workflow = yaml.safe_load(WORKFLOW_FILE.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["run"]["steps"]
    step = next(item for item in steps if item.get("name") == "Run the recipe with Claude")
    return step["with"]["claude_args"]


def test_the_verdict_folder_sits_under_the_one_place_writing_is_allowed() -> None:
    assert RESULT_DIRECTORY.is_relative_to(REPOSITORY_ROOT / "work")
    assert WORK_RULE in ALLOWED


@pytest.mark.parametrize("rule", ["Write", "Edit", "Edit(**)", "Edit(/**)", "Edit(/*)"])
def test_the_session_is_not_allowed_to_write_anywhere(rule: str) -> None:
    assert rule not in ALLOWED
    assert rule not in _flag(_workflow_arguments(), "--allowedTools")


def test_no_project_default_accepts_edits_without_asking() -> None:
    # Accepting edits would let a write outside work/ through without any rule saying so.
    assert "defaultMode" not in SETTINGS["permissions"]


def test_the_workflow_allows_what_the_settings_allow_and_only_the_work_folder_for_writing() -> None:
    allowed = _flag(_workflow_arguments(), "--allowedTools")

    assert set(ALLOWED) <= set(allowed)
    assert [rule for rule in allowed if rule.startswith(("Edit", "Write"))] == [WORK_RULE]


def test_the_workflow_refuses_writes_to_code_settings_recipes_and_itself() -> None:
    refused = _flag(_workflow_arguments(), "--disallowedTools")

    assert set(PROTECTED_RULES) <= set(refused)
    assert WORK_RULE not in refused


def test_every_top_level_folder_but_work_is_refused() -> None:
    """A folder added later must be added to the refused list, or this fails."""
    refused = set(_flag(_workflow_arguments(), "--disallowedTools"))
    folders = {
        path.name
        for path in REPOSITORY_ROOT.iterdir()
        if path.is_dir() and path.name != "work" and not path.name.startswith(".")
    }

    assert folders
    assert {f"Edit(/{name}/**)" for name in folders} <= refused


def test_the_assessor_has_only_read_and_write_and_is_told_where_to_write() -> None:
    assert re.search(r"^tools: Read, Write$", ASSESSOR_PAGE, flags=re.MULTILINE)
    assert "directly inside the `work/results/`" in ASSESSOR_PAGE
