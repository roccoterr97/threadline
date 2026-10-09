"""The words that depend on where the program runs."""

from __future__ import annotations

import pytest

from tracker.shared.runtime import configuration_fix, running_on_github


def test_a_computer_is_told_to_run_the_set_up(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)

    assert running_on_github() is False
    assert configuration_fix() == "run 'uv run tracker setup'"


def test_a_workflow_run_is_told_to_add_the_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")

    assert running_on_github() is True
    assert configuration_fix() == "add the missing secrets with 'uv run tracker setup github'"


def test_any_other_value_of_the_flag_is_a_computer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "false")

    assert running_on_github() is False
