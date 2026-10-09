"""The GitHub route of the set-up: the daily time, the secrets, and the gh and git helpers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import time
from pathlib import Path

import pytest
import yaml
from pydantic import SecretStr

from tests.setup_world import (
    GOOD_SECRET,
    OWNER_EMAIL,
    FakeWorkflow,
    World,
    configured_env,
    make_world,
)
from tracker.infrastructure.github_cli import GitHubCli, GitHubRepository, GitRepository, TextFile
from tracker.services.setup.context import SetupContext
from tracker.services.setup.first_run import FirstRun
from tracker.services.setup.models import StepName
from tracker.services.setup.step_github import GitHubStep
from tracker.services.setup.step_schedule import ScheduleStep
from tracker.services.setup.step_time_zone import TimeZoneStep
from tracker.services.setup.wizard import SetupWizard, core_steps
from tracker.services.setup.workflow_schedule import (
    WORKFLOW_PATH,
    Schedule,
    read_schedule,
    write_schedule,
)
from tracker.shared.constants.github import (
    CLAUDE_TOKEN_SECRET,
    SCHEDULE_COMMIT_MESSAGE,
    WORKFLOW_FILE,
    WorkflowMode,
)
from tracker.shared.errors import (
    SourceUnavailableError,
    ValidationFailedError,
    WorkflowNotEnabledError,
    WorkflowNotStartedError,
)

CLAUDE_KEY = "sk-ant-oat01-made-up-subscription-key"
APP_PASSWORD_LIKE = "zzzz-not-a-real-value"
WORKFLOW_PAGE = "https://github.com/you/threadline/actions/workflows/threadline-run.yml"


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
async def test_the_timezone_line_uses_the_zone_as_the_database_spells_it() -> None:
    world = make_world(["07:00", False], github_env() | {"OWNER_TIME_ZONE": "europe/berlin"})

    await ScheduleStep().run(world.context())

    assert schedule_of(world.workflow.text)["timezone"] == "Europe/Berlin"
    assert world.env.values["OWNER_TIME_ZONE"] == "Europe/Berlin"


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
    world = make_world([CLAUDE_KEY, True, False], github_env())

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
    world = make_world([CLAUDE_KEY, True, False], github_env())

    await GitHubStep().run(world.context())

    assert CLAUDE_KEY not in world.env.values.values()
    assert CLAUDE_TOKEN_SECRET not in world.env.values
    assert world.io.secret_prompts
    assert CLAUDE_TOKEN_SECRET in world.io.secret_prompts[0]


def _with_emptied_settings(answers: list[str | bool]) -> World:
    """A repository that still holds two settings emptied in .env, and one of its own."""
    world = make_world(answers, github_env())
    world.github.secrets = {"LINKEDIN_ACCESS_TOKEN": "old", "SOMETHING_ELSE": "theirs"}
    world.github.variables = {"SMTP_HOST": "smtp.old.example"}
    return world


@pytest.mark.asyncio
async def test_settings_emptied_in_env_are_deleted_on_github_after_one_yes() -> None:
    world = _with_emptied_settings([CLAUDE_KEY, True, True, False])

    await GitHubStep().run(world.context())

    assert sorted(world.github.deleted) == ["LINKEDIN_ACCESS_TOKEN", "SMTP_HOST"]
    assert "SOMETHING_ELSE" in world.github.secrets
    assert CLAUDE_TOKEN_SECRET in world.github.secrets
    said = world.io.said
    assert "  secret LINKEDIN_ACCESS_TOKEN" in said
    assert "  variable SMTP_HOST" in said
    assert "old" not in world.io.text()


@pytest.mark.asyncio
async def test_settings_emptied_in_env_are_kept_on_github_after_a_no() -> None:
    world = _with_emptied_settings([CLAUDE_KEY, True, False, False])

    await GitHubStep().run(world.context())

    assert world.github.deleted == []
    assert "Kept them on GitHub." in world.io.said


@pytest.mark.asyncio
async def test_a_repository_that_cannot_be_listed_keeps_everything_and_says_so() -> None:
    world = _with_emptied_settings([CLAUDE_KEY, True, False])
    world.github.listable = False

    await GitHubStep().run(world.context())

    assert world.github.deleted == []
    assert "a setting you emptied may still be on GitHub" in world.io.text()


def test_gh_lists_names_and_deletes_one_setting_at_a_time() -> None:
    listing = Recorder(output="SUPABASE_URL\nLINKEDIN_ACCESS_TOKEN\n")
    cli = GitHubCli(listing, which=lambda _: "/usr/bin/gh")
    deleting = Recorder()

    names = cli.secret_names("you/threadline")
    GitHubCli(deleting, which=lambda _: "/usr/bin/gh").delete_variable(
        "you/threadline", "SMTP_HOST"
    )

    assert names == {"SUPABASE_URL", "LINKEDIN_ACCESS_TOKEN"}
    assert listing.calls[0][0][:3] == ["gh", "secret", "list"]
    assert deleting.calls == [
        (["gh", "variable", "delete", "SMTP_HOST", "--repo", "you/threadline"], None)
    ]
    with pytest.raises(SourceUnavailableError):
        GitHubCli(Recorder(status=1), which=lambda _: "/usr/bin/gh").variable_names("x/y")


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


# --- The first run ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_after_saving_the_first_run_is_started_after_one_yes() -> None:
    world = make_world([CLAUDE_KEY, True, ""], github_env())
    step = GitHubStep()

    await step.run(world.context())

    assert world.github.enabled == ["you/threadline"]
    assert world.github.started == [("you/threadline", "daily")]
    assert step.first_run == FirstRun(started=True, page=WORKFLOW_PAGE)
    assert (
        f"The first run has started. You can watch it here, or close this window: {WORKFLOW_PAGE}"
        in world.io.said
    )
    assert "The summary e-mail arrives in about 10 minutes." in world.io.said


@pytest.mark.asyncio
async def test_declining_the_first_run_leaves_the_button_and_names_the_page() -> None:
    world = make_world([CLAUDE_KEY, True, False], github_env())
    step = GitHubStep()

    await step.run(world.context())

    assert world.github.enabled == []
    assert world.github.started == []
    assert step.first_run == FirstRun(started=False, page=WORKFLOW_PAGE)
    assert f"To start the first run yourself: open {WORKFLOW_PAGE}," in world.io.said
    assert "click 'Run workflow', keep mode daily" in world.io.text()


@pytest.mark.asyncio
async def test_a_workflow_github_would_not_switch_on_is_left_to_the_button() -> None:
    world = make_world([CLAUDE_KEY, True, ""], github_env())
    world.github.enable_refused = True
    step = GitHubStep()

    await step.run(world.context())

    assert world.github.started == []
    assert world.github.secrets[CLAUDE_TOKEN_SECRET] == CLAUDE_KEY
    assert step.first_run == FirstRun(started=False, page=WORKFLOW_PAGE)
    text = world.io.text()
    assert "GitHub would not switch on the workflow in you/threadline" in text
    assert f"open {WORKFLOW_PAGE}, click 'Enable workflow' if it shows" in text


@pytest.mark.asyncio
async def test_a_run_github_would_not_start_is_left_to_the_button() -> None:
    world = make_world([CLAUDE_KEY, True, ""], github_env())
    world.github.start_refused = True
    step = GitHubStep()

    await step.run(world.context())

    assert world.github.enabled == ["you/threadline"]
    assert step.first_run == FirstRun(started=False, page=WORKFLOW_PAGE)
    assert f"open {WORKFLOW_PAGE} and click 'Run workflow' yourself" in world.io.text()


@pytest.mark.asyncio
async def test_without_gh_the_first_run_is_explained_by_hand() -> None:
    world = make_world([CLAUDE_KEY, True], github_env())
    world.github.signed_in = False
    step = GitHubStep()

    await step.run(world.context())

    assert world.github.started == []
    page = "your copy on github.com > Actions > Threadline run"
    assert step.first_run == FirstRun(started=False, page=page)
    assert f"To start the first run yourself: open {page}," in world.io.said
    assert "click the green 'Run workflow' button" in world.io.text()


@pytest.mark.asyncio
async def test_declining_gh_opens_the_repositorys_own_page() -> None:
    world = make_world(["", False, False], github_env())

    await GitHubStep().run(world.context())

    assert world.io.opened == ["https://github.com/you/threadline/settings/secrets/actions"]
    assert world.github.secrets == {}


@pytest.mark.asyncio
async def test_a_skipped_key_is_left_for_the_page() -> None:
    world = make_world(["", True, False], github_env())

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
    world = make_world(["", True, False], github_env())

    await GitHubStep().run(world.context())

    shown = world.io.text()
    assert "new terminal window, run claude setup-token" in shown
    assert "⌘" not in shown
    assert "sk-ant-" in shown


@pytest.mark.asyncio
async def test_with_outlook_alone_the_step_says_github_cannot_send_the_summary() -> None:
    env = github_env() | {"MAIL_SOURCES": "outlook", "IMAP_PROVIDER": "", "IMAP_USERNAME": ""}
    world = make_world(["", True, False], env)

    await GitHubStep().run(world.context())

    shown = world.io.text()
    assert "the run on GitHub cannot e-mail you the morning summary" in shown
    assert "Outlook alone has no app password to send with" in shown
    assert "'uv run tracker setup cloud'" in shown
    assert "the dashboard is updated every morning" in shown


@pytest.mark.asyncio
async def test_with_the_gmail_connector_chosen_the_step_says_github_cannot_send() -> None:
    world = make_world(["", True, False], github_env() | {"SUMMARY_DELIVERY": "gmail_connector"})

    await GitHubStep().run(world.context())

    shown = world.io.text()
    assert "the run on GitHub cannot e-mail you the morning summary" in shown
    assert "SUMMARY_DELIVERY is set to gmail_connector" in shown
    assert "Outlook alone" not in shown


@pytest.mark.asyncio
async def test_with_a_gmail_mailbox_nothing_is_said_about_sending() -> None:
    world = make_world(["", True, False], github_env())

    await GitHubStep().run(world.context())

    assert "cannot e-mail you" not in world.io.text()


@pytest.mark.asyncio
async def test_without_a_copy_gh_creates_it_after_a_yes_and_then_saves_the_settings() -> None:
    world = make_world([True, "my copy", "tracker", CLAUDE_KEY, True, False], github_env())
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
    world = make_world([True, "", CLAUDE_KEY, True, False], github_env())
    world.github.name = None

    await GitHubStep().run(world.context())

    assert world.git.remotes == {"template": "https://github.com/you/threadline.git"}
    assert world.github.created == ["threadline"]


@pytest.mark.asyncio
async def test_a_link_to_the_public_template_is_never_taken_for_your_copy() -> None:
    world = make_world([True, "", CLAUDE_KEY, True, False], github_env())
    world.git.origin = "https://github.com/maker/threadline.git"
    world.github.name = "maker/threadline"
    world.github.private = False

    await GitHubStep().run(world.context())

    assert "maker/threadline, which is not a private copy you administer" in world.io.text()
    assert world.git.remotes == {"template": "https://github.com/maker/threadline.git"}
    assert world.github.created == ["threadline"]


@pytest.mark.asyncio
async def test_the_schedule_is_never_pushed_to_a_repository_you_do_not_administer() -> None:
    world = make_world(["08:07", True], github_env())
    world.github.admin = False

    await ScheduleStep().run(world.context())

    assert world.git.committed == [(WORKFLOW_PATH, SCHEDULE_COMMIT_MESSAGE)]
    assert world.git.pushed == []


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

    shown = world.io.text()
    assert "install the GitHub CLI from https://cli.github.com" in shown
    assert "brew" not in shown
    assert "move the hidden file .env" in shown
    assert "from the top folder of this project into the top folder of the new copy" in shown
    assert "backend/.env" not in shown
    assert world.github.secrets == {}


@pytest.mark.asyncio
async def test_without_a_copy_the_schedule_is_committed_but_never_pushed() -> None:
    world = make_world(["08:07", True], github_env())
    world.git.origin = None

    await ScheduleStep().run(world.context())

    assert world.git.committed == [(WORKFLOW_PATH, SCHEDULE_COMMIT_MESSAGE)]
    assert world.git.pushed == []
    assert "nothing to push to" in world.io.text()


# --- A new time zone moves the workflow's timezone line too ----------------------


def time_zone_context(world: World, workflow: Path) -> SetupContext:
    """The world's context, reading and writing a real workflow file."""
    ctx = world.context()
    return replace(ctx, gateways=replace(ctx.gateways, workflow=TextFile(workflow)))


@pytest.mark.asyncio
async def test_a_new_time_zone_is_written_into_the_workflow_keeping_its_time(
    tmp_path: Path,
) -> None:
    workflow = tmp_path / "threadline-run.yml"
    workflow.write_text(
        write_schedule(
            WORKFLOW_FILE.read_text(encoding="utf-8"), Schedule(time(6, 30), "Europe/Rome")
        ),
        encoding="utf-8",
    )
    world = make_world(["America/New_York", True, ""], github_env())

    await TimeZoneStep().run(time_zone_context(world, workflow))

    assert schedule_of(workflow.read_text(encoding="utf-8")) == {
        "cron": "30 6 * * *",
        "timezone": "America/New_York",
    }
    assert '  +      timezone: "America/New_York"' in world.io.said
    assert (
        f"Saved {WORKFLOW_PATH}: the daily run now starts at 06:30 (America/New_York)."
        in world.io.said
    )
    assert world.git.pushed == [(WORKFLOW_PATH, SCHEDULE_COMMIT_MESSAGE)]


@pytest.mark.asyncio
async def test_the_workflow_is_left_alone_when_its_zone_already_matches(tmp_path: Path) -> None:
    workflow = tmp_path / "threadline-run.yml"
    original = write_schedule(
        WORKFLOW_FILE.read_text(encoding="utf-8"), Schedule(time(7, 0), "Europe/Rome")
    )
    workflow.write_text(original, encoding="utf-8")
    world = make_world(["", ""], github_env())

    await TimeZoneStep().run(time_zone_context(world, workflow))

    assert workflow.read_text(encoding="utf-8") == original
    assert world.git.pushed == []
    assert world.git.committed == []


@pytest.mark.asyncio
async def test_a_workflow_with_two_daily_times_does_not_stop_the_time_zone_step(
    tmp_path: Path,
) -> None:
    workflow = tmp_path / "threadline-run.yml"
    original = write_schedule(
        WORKFLOW_FILE.read_text(encoding="utf-8"), Schedule(time(7, 0), "Europe/Rome")
    ).replace('- cron: "0 7 * * *"', '- cron: "0 7 * * *"\n    - cron: "0 19 * * *"')
    workflow.write_text(original, encoding="utf-8")
    world = make_world(["Asia/Tokyo", ""], github_env())

    await TimeZoneStep().run(time_zone_context(world, workflow))

    assert world.env.values["OWNER_TIME_ZONE"] == "Asia/Tokyo"
    assert workflow.read_text(encoding="utf-8") == original
    assert any("was changed by hand" in line for line in world.io.said)


@pytest.mark.asyncio
async def test_a_missing_workflow_file_does_not_stop_the_time_zone_step(tmp_path: Path) -> None:
    world = make_world(["Asia/Tokyo", ""], github_env())

    await TimeZoneStep().run(time_zone_context(world, tmp_path / "missing.yml"))

    assert world.env.values["OWNER_TIME_ZONE"] == "Asia/Tokyo"
    assert not (tmp_path / "missing.yml").exists()


def test_the_core_steps_end_with_the_dashboard_the_schedule_and_github() -> None:
    names = [step.name for step in core_steps()]

    assert names[-3:] == [StepName.DASHBOARD, StepName.SCHEDULE, StepName.GITHUB]


# --- The end of the core set-up ---------------------------------------------------


def _finishing_world(answers: list[str | bool]) -> World:
    """A world whose workflow already holds 07:30 in Rome, for the closing words."""
    world = make_world(answers, github_env())
    world.workflow.text = write_schedule(world.workflow.text, Schedule(time(7, 30), "Europe/Rome"))
    return world


@pytest.mark.asyncio
async def test_the_core_set_up_ends_saying_the_e_mail_is_on_its_way() -> None:
    world = _finishing_world([CLAUDE_KEY, True, ""])

    finished = await SetupWizard(world.context(), [GitHubStep()]).run_core()

    assert finished
    said = world.io.said
    ending = said[said.index("Set-up done.") :]
    assert ending[1:3] == [
        "The first run is going on GitHub, so the first summary e-mail reaches you in",
        "about 10 minutes.",
    ]
    assert "After that it comes every day at 07:30 (Europe/Rome)." in ending
    extras = " ".join(ending[-3:])
    assert "Refresh now button, which also makes the daily run start on time" in extras
    assert extras.endswith("Claude cloud route: uv run tracker setup extras")


@pytest.mark.asyncio
async def test_a_first_run_not_started_is_named_with_its_page_at_the_end() -> None:
    world = _finishing_world([CLAUDE_KEY, True, False])

    assert await SetupWizard(world.context(), [GitHubStep()]).run_core()

    said = world.io.said
    ending = said[said.index("Set-up done.") :]
    assert ending[1] == f"Start the first run at {WORKFLOW_PAGE}:"
    assert "After that it comes every day at 07:30 (Europe/Rome)." in ending


@pytest.mark.asyncio
async def test_a_core_set_up_that_stopped_has_no_closing_words() -> None:
    world = make_world([False], github_env())
    world.git.origin = None

    assert not await SetupWizard(world.context(), [GitHubStep()]).run_core()

    assert "Set-up done." not in world.io.said
    assert world.github.started == []


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


class Answering(Recorder):
    """A command runner with an answer per gh command, keyed by its first two words."""

    def __init__(self, answers: dict[str, tuple[int, str]]) -> None:
        super().__init__()
        self.answers = answers

    def __call__(self, arguments: Sequence[str], stdin: str | None) -> tuple[int, str]:
        super().__call__(arguments, stdin)
        return self.answers.get(" ".join(arguments[1:3]), (0, ""))


PERMISSIONS_PATH = "repos/you/threadline/actions/permissions"
ACTIONS_ON = f"api {PERMISSIONS_PATH}"
ACTIONS_SWITCH = "api --method"
WORKFLOW_ENABLE = "workflow enable"
WORKFLOW_RUN = "workflow run"


def _gh(answers: dict[str, tuple[int, str]] | None = None) -> tuple[GitHubCli, Answering]:
    run = Answering(answers or {})
    return GitHubCli(run, which=lambda _: "/usr/bin/gh"), run


def test_gh_enables_the_workflow_and_leaves_actions_alone_when_they_are_on() -> None:
    cli, run = _gh({ACTIONS_ON: (0, "true\n")})

    cli.enable_workflow("you/threadline")

    assert [call[0] for call in run.calls] == [
        ["gh", "api", PERMISSIONS_PATH, "--jq", ".enabled"],
        ["gh", "workflow", "enable", "threadline-run.yml", "--repo", "you/threadline"],
    ]


def test_gh_switches_actions_on_first_when_they_are_off() -> None:
    cli, run = _gh({ACTIONS_ON: (0, "false\n")})

    cli.enable_workflow("you/threadline")

    assert run.calls[1][0] == [
        "gh", "api", "--method", "PUT", PERMISSIONS_PATH,
        "--field", "enabled=true", "--raw-field", "allowed_actions=all",
    ]  # fmt: skip
    assert run.calls[2][0][:3] == ["gh", "workflow", "enable"]


def test_actions_github_would_not_switch_on_are_a_plain_error_naming_the_settings() -> None:
    cli, run = _gh({ACTIONS_ON: (1, ""), ACTIONS_SWITCH: (1, "")})

    with pytest.raises(WorkflowNotEnabledError) as raised:
        cli.enable_workflow("you/threadline")

    assert raised.value.code == "workflow_not_enabled"
    assert "Settings > Actions > General" in raised.value.message
    assert WORKFLOW_PAGE in raised.value.message
    assert len(run.calls) == 2


def test_a_workflow_gh_would_not_enable_is_a_plain_error_naming_the_page() -> None:
    cli, _ = _gh({ACTIONS_ON: (0, "true"), WORKFLOW_ENABLE: (1, "")})

    with pytest.raises(WorkflowNotEnabledError, match="click 'Enable workflow' if it shows"):
        cli.enable_workflow("you/threadline")


def test_gh_starts_the_workflow_with_the_mode_as_its_input() -> None:
    cli, run = _gh()

    cli.start_workflow("you/threadline", WorkflowMode.DAILY)

    started = [
        "gh", "workflow", "run", "threadline-run.yml", "--repo", "you/threadline",
        "--raw-field", "mode=daily",
    ]  # fmt: skip
    assert run.calls == [(started, None)]


def test_a_run_gh_would_not_start_is_a_plain_error_naming_the_page() -> None:
    cli, _ = _gh({WORKFLOW_RUN: (1, "")})

    with pytest.raises(WorkflowNotStartedError) as raised:
        cli.start_workflow("you/threadline", WorkflowMode.DAILY)

    assert raised.value.code == "workflow_not_started"
    assert f"open {WORKFLOW_PAGE} and click 'Run workflow' yourself" in raised.value.message


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
    answer = '{"nameWithOwner":"you/threadline","visibility":"PRIVATE","viewerPermission":"ADMIN"}'
    run = Recorder(output=answer + "\n")
    cli = GitHubCli(run, which=lambda _: "/usr/bin/gh")

    assert cli.repository() == GitHubRepository("you/threadline", private=True, admin=True)
    assert run.calls[0][0][-1] == "nameWithOwner,visibility,viewerPermission"
    assert GitHubCli(Recorder(status=1), which=lambda _: "/usr/bin/gh").repository() is None
    garbled = GitHubCli(Recorder(output="not json"), which=lambda _: "/usr/bin/gh")
    assert garbled.repository() is None


@pytest.mark.parametrize(
    ("visibility", "permission"),
    [("PUBLIC", "ADMIN"), ("PRIVATE", "WRITE"), ("PUBLIC", "READ")],
)
def test_only_a_private_repository_you_administer_is_your_copy(
    visibility: str, permission: str
) -> None:
    answer = (
        f'{{"nameWithOwner":"maker/threadline","visibility":"{visibility}",'
        f'"viewerPermission":"{permission}"}}'
    )
    cli = GitHubCli(Recorder(output=answer), which=lambda _: "/usr/bin/gh")

    repository = cli.repository()

    assert repository is not None
    assert not repository.is_own_private_copy


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
