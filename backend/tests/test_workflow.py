"""The GitHub Actions workflow: its shape, and that it reads every setting from one agreed place."""

from __future__ import annotations

import json
import re
from typing import Any, Final

import pytest
import typer
import yaml

from tracker.cli import main as cli_main
from tracker.domain.enums import RunTrigger
from tracker.services.collection.models import READ_IN_PART_LINE
from tracker.shared.config import AppEnv, LogLevel, Settings
from tracker.shared.constants.claude import CLAUDE_STOPPED_TITLE
from tracker.shared.constants.github import (
    CLAUDE_TOKEN_SECRET,
    DAILY_RUN_TITLE,
    REQUIRED_SECRETS,
    VARIABLE_SETTINGS,
    WORKFLOW_DISPLAY_NAME,
    WORKFLOW_FILE,
    WORKFLOW_FILE_NAME,
    WORKFLOW_FIXED_SETTINGS,
    WORKFLOW_MODE_INPUT,
    WorkflowMode,
)
from tracker.shared.errors import ValidationFailedError

TEXT: Final[str] = WORKFLOW_FILE.read_text(encoding="utf-8")
WORKFLOW: Final[dict[Any, Any]] = yaml.safe_load(TEXT)
#: PyYAML reads the bare key ``on`` as the boolean true (YAML 1.1).
TRIGGERS: Final[dict[str, Any]] = WORKFLOW.get("on") or WORKFLOW[True]
STEPS: Final[list[dict[str, Any]]] = WORKFLOW["jobs"]["run"]["steps"]
SETTINGS: Final[frozenset[str]] = frozenset(name.upper() for name in Settings.model_fields)


def _step(name: str) -> dict[str, Any]:
    return next(step for step in STEPS if step.get("name") == name)


def _recipe(name: str) -> str:
    """The text of one of the recipes the session follows."""
    path = WORKFLOW_FILE.parents[2] / ".claude" / "commands" / f"{name}.md"
    return path.read_text(encoding="utf-8")


def _commands(recipe: str) -> list[str]:
    """Every ``tracker`` command a recipe tells the session to run, in order."""
    return re.findall(r"^\s*cd backend && uv run (tracker .+)$", recipe, flags=re.MULTILINE)


CLAUDE_STEP: Final[dict[str, Any]] = _step("Run the recipe with Claude")
GATE_STEP: Final[dict[str, Any]] = _step("Check the set-up")
EXPLAIN_STEP: Final[dict[str, Any]] = _step("Say why Claude stopped")
#: The first setup-uv release whose action runs on Node.js 24 (v6 ran on Node.js 20).
SETUP_UV_FIRST_NODE_24_MAJOR: Final[int] = 7


def test_the_file_name_is_the_one_the_refresh_button_calls() -> None:
    assert WORKFLOW_FILE.name == WORKFLOW_FILE_NAME == "threadline-run.yml"


def test_it_runs_on_a_schedule_with_a_time_zone_and_by_hand_in_two_modes() -> None:
    [schedule] = TRIGGERS["schedule"]
    assert re.fullmatch(r"\d{1,2} \d{1,2} \* \* \*", schedule["cron"])
    assert schedule["timezone"]
    mode = TRIGGERS["workflow_dispatch"]["inputs"][WORKFLOW_MODE_INPUT]
    assert mode["type"] == "choice"
    assert mode["options"] == ["daily", "refresh"] == [str(choice) for choice in WorkflowMode]
    assert mode["default"] == WorkflowMode.DAILY


def test_the_set_up_names_the_workflow_as_the_actions_tab_lists_it() -> None:
    assert WORKFLOW["name"] == WORKFLOW_DISPLAY_NAME


def test_it_can_only_read_the_repository_and_never_overlaps() -> None:
    assert WORKFLOW["permissions"] == {"contents": "read", "actions": "read"}
    assert WORKFLOW["concurrency"]["cancel-in-progress"] is False
    # A refresh and a daily run each have their own limit; test_workflow_gate
    # checks the two numbers against the gate's wait.
    assert "inputs.mode == 'refresh'" in WORKFLOW["jobs"]["run"]["timeout-minutes"]


def test_a_refresh_never_queues_in_the_daily_runs_group() -> None:
    group = WORKFLOW["concurrency"]["group"]

    assert group == "threadline-${{ inputs.mode == 'refresh' && 'refresh' || 'daily' }}"


def test_the_daily_run_and_a_refresh_take_turns_by_their_titles() -> None:
    title = WORKFLOW["run-name"]
    gate = GATE_STEP["run"]

    assert title == (
        "${{ inputs.mode == 'refresh' && 'Threadline refresh' || 'Threadline daily run' }}"
    )
    assert "daily=$(going 'Threadline daily run')" in gate
    # The set-up finds the first run it started by this title.
    assert f"'{DAILY_RUN_TITLE}'" in title
    assert "refreshes=$(going 'Threadline refresh')" in gate
    # An error from GitHub must never read as "nothing is going".
    assert "count=0" not in gate
    assert GATE_STEP["env"]["GH_TOKEN"] == "${{ github.token }}"


def test_every_action_is_pinned_to_a_major_version_or_a_releases_commit() -> None:
    used = [step["uses"] for step in STEPS if "uses" in step]

    assert used
    for action in used:
        assert re.fullmatch(r"[\w.-]+/[\w.-]+@(v\d+|[0-9a-f]{40})", action), action
        if "@v" not in action:
            # A commit says which release it is, so it can be checked and updated.
            assert re.search(rf"{re.escape(action)} # v\d+\.\d+\.\d+$", TEXT, re.MULTILINE)


@pytest.mark.parametrize("name", ["threadline-run.yml", "ci.yml"])
def test_uv_is_installed_by_a_setup_uv_release_that_runs_on_node_24(name: str) -> None:
    text = (WORKFLOW_FILE.parent / name).read_text(encoding="utf-8")
    pins = re.findall(r"astral-sh/setup-uv@(\S+) # (v\d+)\.", text)

    assert pins
    for commit, release in pins:
        assert re.fullmatch(r"[0-9a-f]{40}", commit)
        assert int(release.removeprefix("v")) >= SETUP_UV_FIRST_NODE_24_MAJOR


def test_every_setting_is_read_from_the_place_the_setup_puts_it() -> None:
    env: dict[str, str] = CLAUDE_STEP["env"]

    assert set(env) == SETTINGS
    for name, value in env.items():
        if name in WORKFLOW_FIXED_SETTINGS:
            assert "${{" not in value
        elif name in VARIABLE_SETTINGS:
            assert value == f"${{{{ vars.{name} }}}}"
        else:
            assert value == f"${{{{ secrets.{name} }}}}"


def test_the_workflow_reads_no_secret_outside_the_agreed_list() -> None:
    referenced = set(re.findall(r"secrets\.([A-Z0-9_]+)", TEXT))
    allowed = (SETTINGS - VARIABLE_SETTINGS - WORKFLOW_FIXED_SETTINGS) | {CLAUDE_TOKEN_SECRET}

    assert referenced <= allowed
    assert set(re.findall(r"vars\.([A-Z0-9_]+)", TEXT)) <= VARIABLE_SETTINGS


def test_the_gate_checks_exactly_the_required_secrets() -> None:
    env = GATE_STEP["env"]
    loop = re.search(r"for name in ([A-Z_ ]+); do", GATE_STEP["run"])

    assert loop is not None
    assert tuple(loop.group(1).split()) == REQUIRED_SECRETS
    assert set(REQUIRED_SECRETS) <= set(env)


def test_a_missing_secret_ends_the_run_green_and_every_later_step_is_skipped() -> None:
    assert "exit 0" in GATE_STEP["run"]
    for step in STEPS:
        if step is GATE_STEP:
            continue
        if step is EXPLAIN_STEP:
            # It follows the Claude step, which is skipped whenever the gate stops.
            assert step["if"] == "failure() && steps.claude.outcome == 'failure'"
            continue
        assert step["if"] == "steps.gate.outputs.ready == 'true'"


def test_when_claude_stops_with_an_error_one_plain_line_says_why() -> None:
    names = [step.get("name") for step in STEPS]
    script = EXPLAIN_STEP["run"]

    assert CLAUDE_STEP["id"] == "claude"
    assert names.index("Say why Claude stopped") == names.index("Run the recipe with Claude") + 1
    assert EXPLAIN_STEP["env"] == {"EXECUTION_FILE": "${{ steps.claude.outputs.execution_file }}"}
    assert EXPLAIN_STEP["working-directory"] == "backend"
    assert 'uv run tracker run why-claude-stopped "$EXECUTION_FILE"' in script
    assert f"::error title={CLAUDE_STOPPED_TITLE}::$reason" in script
    assert '>> "$GITHUB_STEP_SUMMARY"' in script
    # Claude's own words stay hidden: the action is never asked to show them.
    assert "show_full_output" not in CLAUDE_STEP["with"]
    assert "display_report" not in CLAUDE_STEP["with"]


@pytest.mark.parametrize("step", STEPS, ids=lambda step: step.get("name", "?"))
def test_no_script_ever_touches_a_secret_directly(step: dict[str, Any]) -> None:
    assert "secrets." not in step.get("run", "")


def test_the_recipe_is_told_its_mode_and_uses_the_projects_permissions() -> None:
    options = CLAUDE_STEP["with"]

    assert options["prompt"].startswith("/daily-run --trigger ")
    assert "--mode ${{ steps.gate.outputs.mode }}" in options["prompt"]
    assert options["settings"] == ".claude/settings.json"
    assert options["claude_code_oauth_token"] == f"${{{{ secrets.{CLAUDE_TOKEN_SECRET} }}}}"
    assert CLAUDE_TOKEN_SECRET not in CLAUDE_STEP["env"]


def test_the_recipe_knows_every_trigger_the_workflow_passes() -> None:
    recipe = _recipe("daily-run")
    hint = re.search(r"argument-hint: \[--trigger ([a-z|]+)\] \[--mode ([a-z|]+)\]", recipe)

    assert hint is not None
    assert set(hint.group(1).split("|")) == {trigger.value for trigger in RunTrigger}
    assert hint.group(2).split("|") == TRIGGERS["workflow_dispatch"]["inputs"]["mode"]["options"]
    assert "uv run tracker collect all --record --refresh" in recipe
    assert "uv run tracker summary send" in recipe
    for trigger in ("trigger=github", "trigger=refresh"):
        assert trigger in GATE_STEP["run"]


def test_the_daily_recipe_runs_each_folded_step_as_one_command() -> None:
    # Every step costs the session the same few seconds whatever it does, so the
    # small commands are folded: the health check and the profile into the
    # opening, the merge and the link into one, the cleaning into the closing.
    assert _commands(_recipe("daily-run")) == [
        "tracker run start --trigger cloud --prepare",
        "tracker collect all --record",
        "tracker collect all --record --refresh",
        "tracker people tidy",
        "tracker run step --step assess --result failed --error-code <code>",
        "tracker summary build --out ../work/summary.json",
        "tracker summary send",
        "tracker run step --step summary_email --result success --found 1 --new 1",
        "tracker run step --step summary_email --result failed --error-code source_unavailable",
        "tracker run finish --clean",
        "tracker run finish --clean --refresh",
    ]


def test_the_daily_recipe_still_says_what_to_do_about_each_failure() -> None:
    recipe = _recipe("daily-run")

    for line in (
        "ready: yes",
        "ready: no",
        "healthcheck failed · code=<code>",
        "profile apply failed · code=<code>",
        "people merge failed · code=<code>",
        "people link failed · code=<code>",
        "ai clean failed · code=<code>",
        "no run is open",
        "work files kept · the run could not be closed",
        "verdicts saved, step not recorded",
        "step not recorded · code=<code>",
        f"{READ_IN_PART_LINE}<code>",
        "sources collected: N",
    ):
        assert line in recipe
    assert "/assess --record" in recipe
    assert "/assess --record --refresh" in recipe
    assert "step recorded" in recipe


def _failed_command_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], app_env: AppEnv
) -> str:
    """The last line a command that stops on ``no run is open`` really prints."""

    def refuse() -> None:
        message = "no run is open: the latest daily run has already finished"
        raise ValidationFailedError(message)

    cli = typer.Typer()
    cli.command()(refuse)
    monkeypatch.setattr(cli_main, "_logging_preferences", lambda: (LogLevel.INFO, app_env))
    monkeypatch.setattr(cli_main, "build_cli", lambda: cli)
    monkeypatch.setattr("sys.argv", ["tracker"])
    with pytest.raises(SystemExit):
        cli_main.main()
    return capsys.readouterr().err.strip().splitlines()[-1]


def test_the_daily_recipe_reads_a_failure_the_way_github_prints_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    recipe = _recipe("daily-run")
    line = json.loads(_failed_command_line(monkeypatch, capsys, AppEnv.PRODUCTION))

    assert list(line)[:3] == ["code", "detail", "event"]
    assert (line["code"], line["event"]) == ("validation_failed", "command_failed")
    assert line["detail"].startswith("no run is open")
    assert '{"code": "<code>", "detail": "<reason>", "event": "command_failed", …}' in recipe


def test_the_daily_recipe_reads_a_failure_the_way_a_computer_prints_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    recipe = _recipe("daily-run")
    line = _failed_command_line(monkeypatch, capsys, AppEnv.DEVELOPMENT)

    assert re.search(r"command_failed\s+code=validation_failed detail=.no run is open", line)
    assert "`command_failed`, then `code=<code>`, then the reason after `detail=`" in recipe


def test_the_assess_recipe_makes_no_directory_and_passes_record_on() -> None:
    recipe = _recipe("assess")

    assert _commands(recipe) == [
        "tracker ai export $ARGUMENTS",
        "tracker ai import",
        "tracker ai import --record",
        "tracker ai import --record --refresh",
    ]
    assert "mkdir" not in recipe
    assert "argument-hint: [--limit N] [--record] [--refresh]" in recipe
