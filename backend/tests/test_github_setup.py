"""The GitHub route of the set-up: the daily time, the secrets, and the gh and git helpers."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import time

import pytest
import yaml
from pydantic import SecretStr

from tests.setup_world import (
    GOOD_SECRET,
    OWNER_EMAIL,
    FakeWorkflow,
    configured_env,
    make_world,
)
from tracker.infrastructure.github_cli import GitHubCli, GitRepository
from tracker.services.setup.models import StepName
from tracker.services.setup.step_github import GitHubStep
from tracker.services.setup.step_schedule import (
    WORKFLOW_PATH,
    Schedule,
    ScheduleStep,
    read_schedule,
    write_schedule,
)
from tracker.services.setup.wizard import default_steps
from tracker.shared.constants.github import CLAUDE_TOKEN_SECRET, SCHEDULE_COMMIT_MESSAGE
from tracker.shared.errors import SourceUnavailableError, ValidationFailedError

CLAUDE_KEY = "sk-ant-oat01-made-up-subscription-key"
APP_PASSWORD_LIKE = "zzzz-not-a-real-value"


def github_env() -> dict[str, str]:
    """A finished local set-up: the Supabase keys, an owner, a Gmail mailbox."""
    return configured_env() | {
        "OWNER_EMAIL_ADDRESSES": OWNER_EMAIL,
        "MAIL_SOURCES": "imap",
        "IMAP_PROVIDER": "gmail",
        "IMAP_USERNAME": OWNER_EMAIL,
        "OWNER_TIME_ZONE": "Europe/Rome",
        "APP_ENV": "development",
    }


def schedule_of(text: str) -> dict[str, str]:
    """The schedule entry of a workflow, as GitHub would read it."""
    workflow = yaml.safe_load(text)
    triggers = workflow.get("on") or workflow[True]
    return triggers["schedule"][0]


# --- The daily time -------------------------------------------------------------


@pytest.mark.parametrize(
    ("typed", "zone", "cron"),
    [
        ("07:00", "Europe/Rome", "0 7 * * *"),
        ("6:45", "America/New_York", "45 6 * * *"),
        ("18.30", "Asia/Tokyo", "30 18 * * *"),
        ("0", "UTC", "0 0 * * *"),
    ],
)
@pytest.mark.asyncio
async def test_the_time_and_zone_are_written_as_github_reads_them(
    typed: str, zone: str, cron: str
) -> None:
    world = make_world([typed, False], github_env() | {"OWNER_TIME_ZONE": zone})

    await ScheduleStep().run(world.context())

    assert schedule_of(world.workflow.text) == {"cron": cron, "timezone": zone}
    assert world.git.pushed == []
    assert f"  git add :/{WORKFLOW_PATH}" in world.io.said


@pytest.mark.asyncio
async def test_only_the_two_schedule_lines_change_and_the_change_is_shown() -> None:
    world = make_world(["08:15", False], github_env())
    before = world.workflow.text

    await ScheduleStep().run(world.context())

    changed = [
        (old, new)
        for old, new in zip(before.splitlines(), world.workflow.text.splitlines(), strict=True)
        if old != new
    ]
    assert len(changed) == 2
    assert '  +    - cron: "15 8 * * *"' in world.io.said
    assert '  +      timezone: "Europe/Rome"' in world.io.said


@pytest.mark.asyncio
async def test_a_new_zone_is_saved_as_the_owners_time_zone_too() -> None:
    env = github_env()
    del env["OWNER_TIME_ZONE"]
    world = make_world(["07:00", "Europe/Berlin", False], env)

    await ScheduleStep().run(world.context())

    assert world.env.values["OWNER_TIME_ZONE"] == "Europe/Berlin"
    assert schedule_of(world.workflow.text)["timezone"] == "Europe/Berlin"


@pytest.mark.asyncio
async def test_the_saved_time_zone_is_used_without_asking_again() -> None:
    world = make_world(["07:30", False], github_env())

    await ScheduleStep().run(world.context())

    assert schedule_of(world.workflow.text)["timezone"] == "Europe/Rome"
    assert "uv run tracker setup timezone" in world.io.text()


@pytest.mark.asyncio
async def test_pushing_happens_only_after_an_explicit_yes() -> None:
    world = make_world(["09:00", True], github_env())

    await ScheduleStep().run(world.context())

    assert world.git.pushed == [(WORKFLOW_PATH, SCHEDULE_COMMIT_MESSAGE)]


@pytest.mark.asyncio
async def test_keeping_the_same_time_changes_nothing() -> None:
    world = make_world([""], github_env() | {"OWNER_TIME_ZONE": "UTC"})

    await ScheduleStep().run(world.context())

    assert world.workflow.writes == 0
    assert "Nothing to change" in world.io.text()


@pytest.mark.asyncio
async def test_a_wrong_time_is_asked_again() -> None:
    world = make_world(["25:00", "7 pm", "19:00", False], github_env())

    await ScheduleStep().run(world.context())

    assert schedule_of(world.workflow.text)["cron"] == "0 19 * * *"
    assert "24-hour clock" in world.io.text()


@pytest.mark.asyncio
async def test_an_unknown_zone_is_refused() -> None:
    env = github_env()
    del env["OWNER_TIME_ZONE"]
    world = make_world(["07:00", "Mars/Olympus", "Nowhere", "Atlantis"], env)

    with pytest.raises(ValidationFailedError, match="time-zone name"):
        await ScheduleStep().run(world.context())

    assert world.workflow.writes == 0


def test_the_schedule_is_read_back_from_the_file() -> None:
    text = write_schedule(FakeWorkflow().text, Schedule(time(6, 5), "Europe/Rome"))

    assert read_schedule(text) == Schedule(time(6, 5), "Europe/Rome")


def test_a_workflow_without_its_schedule_lines_is_not_guessed_at() -> None:
    with pytest.raises(ValidationFailedError, match="cron line"):
        write_schedule("name: something else\n", Schedule(time(7, 0), "UTC"))


# --- The secrets -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_gh_every_value_goes_to_github_and_none_is_shown() -> None:
    world = make_world([CLAUDE_KEY, True], github_env())

    await GitHubStep().run(world.context())

    github = world.github
    assert github.secrets[CLAUDE_TOKEN_SECRET] == CLAUDE_KEY
    assert github.secrets["SUPABASE_SERVICE_ROLE_KEY"] == GOOD_SECRET
    assert github.secrets["IMAP_USERNAME"] == OWNER_EMAIL
    assert github.variables == {
        "OWNER_TIME_ZONE": "Europe/Rome",
        "MAIL_SOURCES": "imap",
        "IMAP_PROVIDER": "gmail",
    }
    assert "APP_ENV" not in github.secrets | github.variables
    shown = world.io.text()
    for value in (CLAUDE_KEY, GOOD_SECRET, OWNER_EMAIL):
        assert value not in shown
    assert "  secret SUPABASE_SERVICE_ROLE_KEY saved" in world.io.said


@pytest.mark.asyncio
async def test_the_claude_key_is_never_written_to_env() -> None:
    world = make_world([CLAUDE_KEY, True], github_env())

    await GitHubStep().run(world.context())

    assert CLAUDE_KEY not in world.env.values.values()
    assert CLAUDE_TOKEN_SECRET not in world.env.values
    assert world.io.secret_prompts
    assert CLAUDE_TOKEN_SECRET in world.io.secret_prompts[0]


@pytest.mark.asyncio
async def test_without_gh_the_names_and_page_are_shown_and_values_copied() -> None:
    world = make_world([CLAUDE_KEY, True], github_env())
    world.github.signed_in = False

    await GitHubStep().run(world.context())

    said = world.io.said
    assert "  SUPABASE_SERVICE_ROLE_KEY" in said
    assert f"  {CLAUDE_TOKEN_SECRET}" in said
    assert "  OWNER_TIME_ZONE" in said
    assert "Settings > Secrets and variables > Actions" in world.io.text()
    assert world.github.secrets == {}
    assert CLAUDE_KEY in world.io.copied
    assert GOOD_SECRET in world.io.copied
    assert world.io.copied[-1] == ""
    assert CLAUDE_KEY not in world.io.text()


@pytest.mark.asyncio
async def test_declining_gh_opens_the_repositorys_own_page() -> None:
    world = make_world(["", False, False], github_env())

    await GitHubStep().run(world.context())

    assert world.io.opened == ["https://github.com/you/threadline/settings/secrets/actions"]
    assert world.github.secrets == {}


@pytest.mark.asyncio
async def test_a_skipped_key_is_left_for_the_page() -> None:
    world = make_world(["", True], github_env())

    await GitHubStep().run(world.context())

    assert CLAUDE_TOKEN_SECRET not in world.github.secrets
    assert "add CLAUDE_CODE_OAUTH_TOKEN on GitHub yourself" in world.io.text()


@pytest.mark.asyncio
async def test_a_local_set_up_that_is_not_finished_is_refused() -> None:
    world = make_world([], configured_env())

    with pytest.raises(ValidationFailedError, match="OWNER_EMAIL_ADDRESSES"):
        await GitHubStep().run(world.context())


@pytest.mark.asyncio
async def test_the_claude_key_instruction_says_where_and_what_it_looks_like() -> None:
    world = make_world(["", True], github_env())

    await GitHubStep().run(world.context())

    shown = world.io.text()
    assert "second Terminal window (⌘ + N), run claude setup-token" in shown
    assert "sk-ant-" in shown


@pytest.mark.asyncio
async def test_without_a_copy_gh_creates_it_after_a_yes_and_then_saves_the_settings() -> None:
    world = make_world([True, "my copy", "tracker", CLAUDE_KEY, True], github_env())
    world.git.origin = None
    world.github.name = None

    await GitHubStep().run(world.context())

    assert world.github.created == ["tracker"]
    assert world.github.secrets[CLAUDE_TOKEN_SECRET] == CLAUDE_KEY
    text = world.io.text()
    assert "your own private copy" in text
    assert "use only letters, digits" in text
    assert "Created your private copy you/tracker" in text


@pytest.mark.asyncio
async def test_a_link_to_someone_elses_copy_is_kept_under_another_name() -> None:
    world = make_world([True, "", CLAUDE_KEY, True], github_env())
    world.github.name = None

    await GitHubStep().run(world.context())

    assert world.git.remotes == {"template": "https://github.com/you/threadline.git"}
    assert world.github.created == ["threadline"]


@pytest.mark.asyncio
async def test_without_a_copy_and_no_yes_the_step_explains_and_stops() -> None:
    world = make_world([False], github_env())
    world.git.origin = None

    with pytest.raises(ValidationFailedError, match="no private copy on GitHub yet"):
        await GitHubStep().run(world.context())

    assert "'Use this template'" in world.io.text()
    assert world.github.created == []
    assert world.io.secret_prompts == []


@pytest.mark.asyncio
async def test_without_a_copy_or_gh_the_template_steps_are_given_and_nothing_is_asked() -> None:
    world = make_world([], github_env())
    world.git.origin = None
    world.github.signed_in = False

    with pytest.raises(ValidationFailedError):
        await GitHubStep().run(world.context())

    assert "brew install gh" in world.io.text()
    assert world.github.secrets == {}


@pytest.mark.asyncio
async def test_without_a_copy_the_schedule_is_committed_but_never_pushed() -> None:
    world = make_world(["08:07", True], github_env())
    world.git.origin = None

    await ScheduleStep().run(world.context())

    assert world.git.committed == [(WORKFLOW_PATH, SCHEDULE_COMMIT_MESSAGE)]
    assert world.git.pushed == []
    assert "nothing to push to" in world.io.text()


def test_the_github_steps_come_before_the_cloud_alternative() -> None:
    names = [step.name for step in default_steps()]

    assert names[-4:] == [StepName.SCHEDULE, StepName.GITHUB, StepName.REFRESH, StepName.CLOUD]


# --- The gh and git helpers ----------------------------------------------------------


class Recorder:
    """Stands in for the command runner; remembers every call."""

    def __init__(self, status: int = 0, output: str = "") -> None:
        self.calls: list[tuple[list[str], str | None]] = []
        self.status = status
        self.output = output

    def __call__(self, arguments: Sequence[str], stdin: str | None) -> tuple[int, str]:
        self.calls.append((list(arguments), stdin))
        return self.status, self.output


def test_a_secret_goes_to_gh_on_standard_input_and_never_as_an_argument() -> None:
    run = Recorder()

    GitHubCli(run, which=lambda _: "/usr/bin/gh").set_secret(
        "you/threadline", "SUPABASE_SERVICE_ROLE_KEY", SecretStr(APP_PASSWORD_LIKE)
    )

    [(arguments, stdin)] = run.calls
    assert arguments == [
        "gh",
        "secret",
        "set",
        "SUPABASE_SERVICE_ROLE_KEY",
        "--repo",
        "you/threadline",
    ]
    assert stdin == APP_PASSWORD_LIKE
    assert all(APP_PASSWORD_LIKE not in argument for argument in arguments)


def test_a_refusal_by_gh_names_the_setting_and_not_its_value() -> None:
    cli = GitHubCli(Recorder(status=1), which=lambda _: "/usr/bin/gh")

    with pytest.raises(SourceUnavailableError) as raised:
        cli.set_variable("you/threadline", "OWNER_TIME_ZONE", "Europe/Rome")

    assert "OWNER_TIME_ZONE" in raised.value.message
    assert "Europe/Rome" not in raised.value.message


def test_gh_that_is_not_installed_is_not_ready() -> None:
    run = Recorder()

    assert not GitHubCli(run, which=lambda _: None).ready()
    assert run.calls == []


def test_gh_that_is_not_signed_in_is_not_ready() -> None:
    assert not GitHubCli(Recorder(status=1), which=lambda _: "/usr/bin/gh").ready()


def test_the_repository_is_read_from_gh() -> None:
    cli = GitHubCli(Recorder(output="you/threadline\n"), which=lambda _: "/usr/bin/gh")

    assert cli.repository() == "you/threadline"
    assert GitHubCli(Recorder(status=1), which=lambda _: "/usr/bin/gh").repository() is None


def test_git_adds_commits_and_pushes_the_one_file() -> None:
    run = Recorder()

    GitRepository(run).commit_and_push(WORKFLOW_PATH, SCHEDULE_COMMIT_MESSAGE)

    assert [call[0][:2] for call in run.calls] == [
        ["git", "add"],
        ["git", "commit"],
        ["git", "push"],
    ]
    assert run.calls[1][0][-1] == WORKFLOW_PATH


def test_a_failed_git_command_stops_the_rest() -> None:
    run = Recorder(status=1)

    with pytest.raises(SourceUnavailableError, match="git add"):
        GitRepository(run).commit_and_push(WORKFLOW_PATH, SCHEDULE_COMMIT_MESSAGE)

    assert len(run.calls) == 1


def test_the_origin_link_is_read_from_git() -> None:
    assert GitRepository(Recorder(output="git@github.com:you/x.git\n")).origin_url() == (
        "git@github.com:you/x.git"
    )
    assert GitRepository(Recorder(status=2)).origin_url() is None


def test_gh_creates_a_private_copy_linked_as_origin_and_pushes() -> None:
    run = Recorder()

    GitHubCli(run, which=lambda _: "/usr/bin/gh").create_private_copy("threadline")

    [(arguments, _)] = run.calls
    assert arguments == [
        "gh", "repo", "create", "threadline", "--private",
        "--source", ".", "--remote", "origin", "--push",
    ]  # fmt: skip


def test_a_copy_gh_could_not_create_is_a_plain_error() -> None:
    with pytest.raises(SourceUnavailableError, match="could not create your copy"):
        GitHubCli(Recorder(status=1), which=lambda _: "/usr/bin/gh").create_private_copy("x")


def test_git_can_commit_without_pushing_and_rename_origin() -> None:
    run = Recorder()
    repository = GitRepository(run)

    repository.commit(WORKFLOW_PATH, SCHEDULE_COMMIT_MESSAGE)
    repository.rename_origin("template")

    assert [call[0][:3] for call in run.calls] == [
        ["git", "add", "--"],
        ["git", "commit", "-m"],
        ["git", "remote", "rename"],
    ]
