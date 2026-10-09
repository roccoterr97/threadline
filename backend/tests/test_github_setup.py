"""The GitHub route of the set-up: the daily time, the secrets, and the gh and git helpers."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

import pytest
import yaml
from pydantic import SecretStr

from tests.setup_world import (
    GOOD_SECRET,
    OWNER_EMAIL,
    REFRESH_RUN_TITLE,
    FakeWorkflow,
    World,
    configured_env,
    make_world,
)
from tracker.infrastructure.github_cli import (
    GitHubCli,
    GitHubRepository,
    GitRepository,
    TextFile,
    WorkflowRun,
    run_command,
)
from tracker.services.setup.claude_key import ClaudeKeyProblem, claude_key_problem
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
    DAILY_RUN_TITLE,
    RECENT_RUNS_LIMIT,
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

#: A made-up subscription key as long as a real one (about 108 characters).
CLAUDE_KEY = "sk-ant-oat01-" + "made-up-subscription-key-" * 4 + "end"
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


# --- The Claude key ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("pasted", "problem"),
    [
        (CLAUDE_KEY, None),
        (CLAUDE_KEY[:70], ClaudeKeyProblem.CUT_SHORT),
        ("sk-ant-api03-" + "made-up-api-key-" * 7, ClaudeKeyProblem.API_KEY),
        ("export CLAUDE_CODE_OAUTH_TOKEN=" + CLAUDE_KEY, ClaudeKeyProblem.NOT_A_KEY),
        (CLAUDE_KEY + '"', ClaudeKeyProblem.STRAY_CHARACTERS),
    ],
)
def test_a_pasted_key_is_judged_by_its_shape(pasted: str, problem: ClaudeKeyProblem | None) -> None:
    assert claude_key_problem(pasted) is problem


@pytest.mark.asyncio
async def test_a_key_split_over_two_lines_is_joined_into_one() -> None:
    first, second = CLAUDE_KEY[:70], CLAUDE_KEY[70:]
    world = make_world([first, second, True, False], github_env())

    await GitHubStep().run(world.context())

    assert world.github.secrets[CLAUDE_TOKEN_SECRET] == CLAUDE_KEY
    assert "split over two lines" in world.io.secret_prompts[1]
    assert first not in world.io.text()


@pytest.mark.asyncio
async def test_a_key_cut_short_can_be_pasted_again_whole() -> None:
    world = make_world([CLAUDE_KEY[:70], CLAUDE_KEY, True, False], github_env())

    await GitHubStep().run(world.context())

    assert world.github.secrets[CLAUDE_TOKEN_SECRET] == CLAUDE_KEY


@pytest.mark.asyncio
async def test_an_api_key_is_refused_with_what_to_paste_instead() -> None:
    api_key = "sk-ant-api03-" + "made-up-api-key-" * 7
    world = make_world([api_key, CLAUDE_KEY, True, False], github_env())

    await GitHubStep().run(world.context())

    assert world.github.secrets[CLAUDE_TOKEN_SECRET] == CLAUDE_KEY
    shown = world.io.text()
    assert "That is an API key" in shown
    assert "starting sk-ant-oat" in shown
    assert api_key not in shown


@pytest.mark.asyncio
async def test_a_key_never_whole_stops_the_step_before_anything_is_saved() -> None:
    world = make_world(["not a key", "still not", "nope", "no"], github_env())

    with pytest.raises(ValidationFailedError, match="from the first letter to the last"):
        await GitHubStep().run(world.context())

    assert world.github.secrets == {}
    assert world.github.started == []


@pytest.mark.asyncio
async def test_the_key_instruction_says_it_is_split_over_two_lines() -> None:
    world = make_world(["", True, False], github_env())

    await GitHubStep().run(world.context())

    shown = world.io.text()
    assert "starting sk-ant-oat" in shown
    assert "from the first letter to the last, including the second line" in shown


# --- The first run ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_after_saving_the_first_run_is_started_after_one_yes() -> None:
    world = make_world([CLAUDE_KEY, True, ""], github_env())
    step = GitHubStep()

    await step.run(world.context())

    assert world.github.enabled == ["you/threadline"]
    assert world.github.started == [("you/threadline", "daily")]
    assert step.first_run == FirstRun(started=True, page=WORKFLOW_PAGE)
    said = world.io.said
    assert "The first run has started." in said
    assert "It is running; the summary e-mail comes in about 10 minutes." in said
    assert f"You can watch it here, or close this window: {WORKFLOW_PAGE}" in said


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
async def test_an_empty_answer_keeps_the_key_github_already_has() -> None:
    world = make_world(["", True, ""], github_env())
    world.github.secrets[CLAUDE_TOKEN_SECRET] = CLAUDE_KEY
    step = GitHubStep()

    await step.run(world.context())

    assert world.github.secrets[CLAUDE_TOKEN_SECRET] == CLAUDE_KEY
    assert (
        "or leave it empty to keep the key GitHub already has, if any"
        in (world.io.secret_prompts[0])
    )
    assert world.github.started == [("you/threadline", "daily")]
    assert step.first_run == FirstRun(started=True, page=WORKFLOW_PAGE)


@pytest.mark.asyncio
async def test_without_the_claude_key_on_github_the_first_run_is_not_started() -> None:
    world = make_world(["", True], github_env())
    step = GitHubStep()

    await step.run(world.context())

    assert CLAUDE_TOKEN_SECRET not in world.github.secrets
    assert world.github.started == []
    assert world.github.enabled == []
    assert step.first_run == FirstRun(started=False, page=WORKFLOW_PAGE, needs_claude_key=True)
    shown = world.io.text()
    assert "GitHub does not have CLAUDE_CODE_OAUTH_TOKEN yet" in shown
    assert "'claude setup-token'" in shown
    assert "'uv run tracker setup github'" in shown


@pytest.mark.asyncio
async def test_a_key_github_cannot_be_asked_about_also_holds_the_first_run_back() -> None:
    world = make_world(["", True], github_env())
    world.github.listable = False
    step = GitHubStep()

    await step.run(world.context())

    assert world.github.started == []
    assert step.first_run is not None
    assert step.first_run.needs_claude_key
    assert "could not be asked whether it has" in " ".join(world.io.said)


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


def outlook_only_env() -> dict[str, str]:
    """A finished set-up that reads Outlook alone, so GitHub has no way to send the e-mail."""
    return github_env() | {"MAIL_SOURCES": "outlook", "IMAP_PROVIDER": "", "IMAP_USERNAME": ""}


@pytest.mark.asyncio
async def test_with_outlook_alone_the_step_says_github_cannot_send_the_summary() -> None:
    world = make_world([False, CLAUDE_KEY, True, False], outlook_only_env())

    await GitHubStep().run(world.context())

    shown = world.io.text()
    assert "the run on GitHub cannot e-mail you the morning summary" in shown
    assert "needs a mailbox with an app password" in shown
    assert "Outlook alone has no app" in shown
    assert "'uv run tracker setup extras'" in shown
    assert "the dashboard is updated every morning" in shown


@pytest.mark.asyncio
async def test_with_outlook_alone_the_mailbox_step_is_offered_and_makes_the_e_mail_possible() -> (
    None
):
    answers = [True, "gmail", OWNER_EMAIL, "wxyz wxyz wxyz wxyz", True, CLAUDE_KEY, True, ""]
    world = make_world(answers, outlook_only_env())
    step = GitHubStep()

    await step.run(world.context())

    assert world.env.values["MAIL_SOURCES"] == "outlook,imap"
    assert world.github.variables["MAIL_SOURCES"] == "outlook,imap"
    assert world.github.started == [("you/threadline", "daily")]
    assert step.first_run == FirstRun(started=True, page=WORKFLOW_PAGE)
    assert "It is running; the summary e-mail comes in about 10 minutes." in world.io.said


@pytest.mark.asyncio
async def test_with_no_way_to_send_the_first_run_defaults_to_no_and_promises_no_e_mail() -> None:
    world = make_world([False, CLAUDE_KEY, True, ""], outlook_only_env())
    step = GitHubStep()

    await step.run(world.context())

    assert world.github.started == []
    assert step.first_run == FirstRun(started=False, page=WORKFLOW_PAGE, summary_by_email=False)
    shown = world.io.text()
    assert "Without one, no summary e-mail will arrive" in shown
    assert "'uv run tracker setup mailbox', then 'uv run tracker setup github'" in shown


@pytest.mark.asyncio
async def test_starting_the_first_run_anyway_says_no_e_mail_will_come() -> None:
    world = make_world([False, CLAUDE_KEY, True, True], outlook_only_env())
    step = GitHubStep()

    await step.run(world.context())

    assert world.github.started == [("you/threadline", "daily")]
    assert step.first_run == FirstRun(started=True, page=WORKFLOW_PAGE, summary_by_email=False)
    shown = world.io.text()
    assert "No summary e-mail" in shown
    assert "e-mail comes in about" not in shown


@pytest.mark.asyncio
async def test_with_the_gmail_connector_chosen_the_step_says_github_cannot_send() -> None:
    world = make_world(["", True, False], github_env() | {"SUMMARY_DELIVERY": "gmail_connector"})

    await GitHubStep().run(world.context())

    shown = world.io.text()
    assert "the run on GitHub cannot e-mail you the morning summary" in shown
    assert "SUMMARY_DELIVERY is set to gmail_connector" in shown
    assert "Outlook alone" not in shown
    assert "Connect a Gmail" not in " ".join(world.io.said)


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


# --- A time that is saved here but not on GitHub yet -------------------------------


def _unsent_env() -> dict[str, str]:
    """A set-up whose saved zone matches the workflow, so no line needs changing."""
    return github_env() | {"OWNER_TIME_ZONE": "UTC"}


@pytest.mark.asyncio
async def test_a_time_saved_here_but_not_committed_is_offered_again_on_a_rerun() -> None:
    world = make_world(["", True], _unsent_env())
    world.git.uncommitted = True

    await ScheduleStep().run(world.context())

    assert "Nothing to change" in world.io.text()
    assert "GitHub does not have this time yet" in world.io.text()
    assert world.git.pushed == [(WORKFLOW_PATH, SCHEDULE_COMMIT_MESSAGE)]


@pytest.mark.asyncio
async def test_a_time_committed_but_not_pushed_is_pushed_without_a_new_commit() -> None:
    world = make_world(["", True], _unsent_env())
    world.git.unpushed = True

    await ScheduleStep().run(world.context())

    assert world.git.plain_pushes == 1
    assert world.git.pushed == []
    assert world.git.committed == []


@pytest.mark.asyncio
async def test_a_time_already_on_github_asks_nothing_on_a_rerun() -> None:
    world = make_world([""], _unsent_env())

    await ScheduleStep().run(world.context())

    assert "Nothing to change" in world.io.text()
    assert world.git.pushed == []
    assert world.git.plain_pushes == 0


@pytest.mark.asyncio
async def test_a_declined_push_of_a_saved_time_prints_the_lines_to_run() -> None:
    world = make_world(["", False], _unsent_env())
    world.git.unpushed = True

    await ScheduleStep().run(world.context())

    assert world.git.plain_pushes == 0
    assert "  git push" in world.io.said


@pytest.mark.asyncio
async def test_without_a_copy_an_unpushed_commit_is_not_offered() -> None:
    world = make_world([""], _unsent_env())
    world.git.origin = None
    world.git.unpushed = True

    await ScheduleStep().run(world.context())

    assert world.git.plain_pushes == 0
    assert world.git.committed == []


@pytest.mark.asyncio
async def test_the_time_zone_step_offers_a_zone_saved_here_but_not_on_github(
    tmp_path: Path,
) -> None:
    workflow = tmp_path / "threadline-run.yml"
    workflow.write_text(
        write_schedule(
            WORKFLOW_FILE.read_text(encoding="utf-8"), Schedule(time(7, 0), "Europe/Rome")
        ),
        encoding="utf-8",
    )
    world = make_world(["", "", True], github_env())
    world.git.uncommitted = True

    await TimeZoneStep().run(time_zone_context(world, workflow))

    assert world.git.pushed == [(WORKFLOW_PATH, SCHEDULE_COMMIT_MESSAGE)]


@pytest.mark.asyncio
async def test_the_github_step_sends_a_time_that_never_reached_the_copy() -> None:
    world = make_world([True, CLAUDE_KEY, True, False], _unsent_env())
    world.git.unpushed = True

    await GitHubStep().run(world.context())

    assert world.git.plain_pushes == 1
    assert world.github.secrets[CLAUDE_TOKEN_SECRET] == CLAUDE_KEY


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


# --- Following the first run ----------------------------------------------------------

STOPPED_NOTE = (
    "Claude did not accept the key saved on GitHub (CLAUDE_CODE_OAUTH_TOKEN): it is "
    "incomplete, expired or was cancelled."
)


@pytest.mark.asyncio
async def test_a_first_run_that_stops_at_once_is_said_with_the_reason_from_github() -> None:
    world = make_world([CLAUDE_KEY, True, ""], github_env())
    world.github.run_states = [("in_progress", ""), ("completed", "failure")]
    world.github.notes = (STOPPED_NOTE,)
    step = GitHubStep()

    await step.run(world.context())

    run_page = "https://github.com/you/threadline/actions/runs/1000"
    assert step.first_run == FirstRun(started=True, page=run_page, stopped=True)
    said = world.io.said
    assert f"The first run stopped with a problem. {STOPPED_NOTE}" in said
    assert not any("e-mail comes in about" in line for line in said)
    assert world.waits == [10, 10, 10]


@pytest.mark.asyncio
async def test_a_stopped_run_without_a_reason_names_its_page() -> None:
    world = make_world([CLAUDE_KEY, True, ""], github_env())
    world.github.run_states = [("completed", "failure")]

    await GitHubStep().run(world.context())

    text = world.io.text()
    assert "The first run stopped with a problem. To see why, open this page" in text
    assert "step marked with a red cross: https://github.com/you/threadline/actions/runs/1000" in (
        text
    )


@pytest.mark.asyncio
async def test_a_first_run_still_going_after_two_minutes_is_left_to_finish() -> None:
    world = make_world([CLAUDE_KEY, True, ""], github_env())

    await GitHubStep().run(world.context())

    assert world.waits == [10] * 12
    assert "Watching it for up to 2 minutes, to catch a problem early..." in world.io.said
    assert "It is running; the summary e-mail comes in about 10 minutes." in world.io.said


@pytest.mark.asyncio
async def test_a_first_run_that_finishes_well_says_so() -> None:
    world = make_world([CLAUDE_KEY, True, ""], github_env())
    world.github.run_states = [("completed", "success")]

    await GitHubStep().run(world.context())

    assert "The first run has finished." in world.io.said
    assert "The summary e-mail is on its way." in world.io.said


@pytest.mark.asyncio
async def test_an_earlier_run_is_not_taken_for_the_new_one() -> None:
    world = make_world([CLAUDE_KEY, True, ""], github_env())
    old = "https://github.com/you/threadline/actions/runs/7"
    world.github.runs = [WorkflowRun(id=7, status="completed", conclusion="failure", url=old)]

    await GitHubStep().run(world.context())

    assert set(world.github.looked_at) == {1001}
    assert "It is running; the summary e-mail comes in about 10 minutes." in world.io.said


_SET_UP_STARTED = datetime(2026, 9, 29, 7, 0, tzinfo=UTC)


def _other_run(run_id: int, title: str, created_at: datetime) -> WorkflowRun:
    url = f"https://github.com/you/threadline/actions/runs/{run_id}"
    return WorkflowRun(run_id, "in_progress", "", url, title=title, created_at=created_at)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "other",
    [
        _other_run(1001, REFRESH_RUN_TITLE, _SET_UP_STARTED + timedelta(seconds=5)),
        _other_run(1001, DAILY_RUN_TITLE, _SET_UP_STARTED + timedelta(seconds=5)),
        _other_run(999, DAILY_RUN_TITLE, _SET_UP_STARTED - timedelta(minutes=10)),
    ],
    ids=["a refresh just after", "an on-time start just after", "a daily run from before"],
)
async def test_only_the_daily_run_the_set_up_started_is_followed(other: WorkflowRun) -> None:
    world = make_world([CLAUDE_KEY, True, ""], github_env())
    world.github.runs_started_next = [other]
    world.github.run_states = [("completed", "failure")]
    step = GitHubStep()

    await step.run(world.context())

    assert set(world.github.looked_at) == {1000}
    run_page = "https://github.com/you/threadline/actions/runs/1000"
    assert step.first_run == FirstRun(started=True, page=run_page, stopped=True)


@pytest.mark.asyncio
async def test_the_set_ups_run_is_still_found_when_githubs_clock_is_a_little_behind() -> None:
    world = make_world([CLAUDE_KEY, True, ""], github_env())
    world.github.run_created_at = _SET_UP_STARTED - timedelta(seconds=30)
    world.github.run_states = [("completed", "success")]

    await GitHubStep().run(world.context())

    assert set(world.github.looked_at) == {1000}
    assert "The first run has finished." in world.io.said


@pytest.mark.asyncio
async def test_when_github_cannot_say_how_runs_go_the_run_is_not_followed() -> None:
    world = make_world([CLAUDE_KEY, True, ""], github_env())
    world.github.runs_readable = False
    step = GitHubStep()

    await step.run(world.context())

    assert world.waits == []
    assert step.first_run == FirstRun(started=True, page=WORKFLOW_PAGE)
    assert "The first run has started." in world.io.said
    assert "It is running; the summary e-mail comes in about 10 minutes." in world.io.said


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
async def test_the_closing_words_promise_no_e_mail_when_none_can_come() -> None:
    world = make_world([False, CLAUDE_KEY, True, ""], outlook_only_env())
    world.workflow.text = write_schedule(world.workflow.text, Schedule(time(7, 30), "Europe/Rome"))

    assert await SetupWizard(world.context(), [GitHubStep()]).run_core()

    said = world.io.said
    ending = said[said.index("Set-up done.") :]
    text = "\n".join(ending)
    assert f"Start the first run at {WORKFLOW_PAGE}:" in ending
    assert "the dashboard fills about 10 minutes later." in ending
    assert "After that the dashboard is updated every day at 07:30 (Europe/Rome)." in ending
    assert "No summary e-mail will come yet" in text
    assert "summary e-mail follows" not in text
    assert "comes every day" not in text


@pytest.mark.asyncio
async def test_the_closing_words_name_the_missing_claude_key() -> None:
    world = _finishing_world(["", True])

    assert await SetupWizard(world.context(), [GitHubStep()]).run_core()

    said = world.io.said
    ending = said[said.index("Set-up done.") :]
    assert "The first run is not started yet: GitHub still needs your Claude key." in ending
    assert "'uv run tracker setup github' and paste the key." in ending
    assert "After that it comes every day at 07:30 (Europe/Rome)." in ending
    assert not any("e-mail reaches you" in line for line in ending)


@pytest.mark.asyncio
async def test_the_closing_words_point_back_to_a_first_run_that_stopped() -> None:
    world = _finishing_world([CLAUDE_KEY, True, ""])
    world.github.run_states = [("completed", "failure")]
    world.github.notes = (STOPPED_NOTE,)

    assert await SetupWizard(world.context(), [GitHubStep()]).run_core()

    said = world.io.said
    ending = said[said.index("Set-up done.") :]
    assert ending[1] == "The first run on GitHub stopped with a problem; what to do is said above."
    assert not any("e-mail reaches you" in line for line in ending)


@pytest.mark.asyncio
async def test_a_core_set_up_that_stopped_has_no_closing_words() -> None:
    world = make_world([False], github_env())
    world.git.origin = None

    assert not await SetupWizard(world.context(), [GitHubStep()]).run_core()

    assert "Set-up done." not in world.io.said
    assert world.github.started == []


# --- The gh and git helpers ----------------------------------------------------------


def test_gh_reads_the_newest_runs_started_by_hand_and_one_runs_state() -> None:
    listing = Recorder(
        output=(
            '[{"databaseId": 43, "status": "queued", "conclusion": "", "url": "v",'
            ' "displayTitle": "Threadline refresh", "createdAt": "2026-10-09T08:00:05Z"},'
            ' {"databaseId": 42, "status": "in_progress", "conclusion": "", "url": "u",'
            ' "displayTitle": "Threadline daily run", "createdAt": "2026-10-09T08:00:00Z"},'
            ' {"databaseId": 41, "status": "queued", "conclusion": "", "url": "w",'
            ' "createdAt": "not a time"}, "not a run"]'
        )
    )
    viewing = Recorder(
        output='{"databaseId": 42, "status": "completed", "conclusion": "failure", "url": "u"}'
    )

    runs = GitHubCli(listing, which=lambda _: "/usr/bin/gh").recent_runs("you/threadline")
    seen = GitHubCli(viewing, which=lambda _: "/usr/bin/gh").workflow_run("you/threadline", 42)

    assert [run.id for run in runs] == [43, 42, 41]
    assert runs[1] == WorkflowRun(
        id=42,
        status="in_progress",
        conclusion="",
        url="u",
        title=DAILY_RUN_TITLE,
        created_at=datetime(2026, 10, 9, 8, 0, tzinfo=UTC),
    )
    assert runs[2].created_at is None
    assert seen.finished
    assert not seen.succeeded
    command = listing.calls[0][0]
    assert command[:4] == ["gh", "run", "list", "--workflow"]
    assert "workflow_dispatch" in command
    assert command[command.index("--limit") + 1] == str(RECENT_RUNS_LIMIT)
    assert "displayTitle,createdAt" in command[command.index("--json") + 1]
    assert viewing.calls[0][0][:4] == ["gh", "run", "view", "42"]


def test_gh_reads_no_run_as_none_and_a_failure_as_unavailable() -> None:
    assert GitHubCli(Recorder(output="[]"), which=lambda _: "/usr/bin/gh").recent_runs("x/y") == ()
    for broken in (Recorder(status=1), Recorder(output="not json")):
        with pytest.raises(SourceUnavailableError, match="could not say how the run is going"):
            GitHubCli(broken, which=lambda _: "/usr/bin/gh").recent_runs("x/y")
    with pytest.raises(SourceUnavailableError):
        GitHubCli(Recorder(output="{}"), which=lambda _: "/usr/bin/gh").workflow_run("x/y", 1)


def test_gh_reads_a_runs_notes_by_their_title_from_each_job() -> None:
    runner = Answering(
        {
            "run view": (0, "11\n12\n"),
            "api repos/you/threadline/check-runs/11/annotations": (0, "First line\n"),
            "api repos/you/threadline/check-runs/12/annotations": (0, ""),
        }
    )

    notes = GitHubCli(runner, which=lambda _: "/usr/bin/gh").run_notes(
        "you/threadline", 42, "Why Claude stopped"
    )

    assert notes == ("First line",)
    api_call = runner.calls[1][0]
    assert api_call[:3] == ["gh", "api", "repos/you/threadline/check-runs/11/annotations"]
    assert api_call[-1] == '.[] | select(.title == "Why Claude stopped") | .message'


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


def test_gh_switches_the_workflow_off_by_its_file_name() -> None:
    cli, run = _gh()

    cli.disable_workflow("you/threadline")

    assert [call[0] for call in run.calls] == [
        ["gh", "workflow", "disable", "threadline-run.yml", "--repo", "you/threadline"]
    ]


def test_a_workflow_gh_would_not_disable_is_a_plain_error_naming_the_page() -> None:
    cli, _ = _gh({"workflow disable": (1, "")})

    with pytest.raises(SourceUnavailableError, match="choose 'Disable workflow'"):
        cli.disable_workflow("you/threadline")


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


def _version_of(text: str) -> Answering:
    return Answering({"--version": (0, text), "auth status": (0, "")})


def test_an_old_gh_stops_the_set_up_early_with_where_to_get_a_new_one() -> None:
    run = _version_of("gh version 2.40.1 (2023-12-13)\nhttps://github.com/cli/cli/releases\n")

    with pytest.raises(SourceUnavailableError) as raised:
        GitHubCli(run, which=lambda _: "/usr/bin/gh").ready()

    message = str(raised.value)
    assert "2.40" in message
    assert "2.68" in message
    assert "https://cli.github.com" in message


def test_a_new_enough_gh_is_ready_and_asked_its_version_only_once() -> None:
    run = _version_of("gh version 2.68.0 (2025-03-05)\n")
    cli = GitHubCli(run, which=lambda _: "/usr/bin/gh")

    assert cli.ready()
    assert cli.ready()

    versions = [call[0] for call in run.calls if call[0][1:] == ["--version"]]
    assert versions == [["gh", "--version"]]


@pytest.mark.parametrize("said", ["", "something unexpected", "gh version dev"])
def test_a_version_gh_does_not_state_clearly_is_not_held_against_it(said: str) -> None:
    assert GitHubCli(_version_of(said), which=lambda _: "/usr/bin/gh").ready()


def test_a_newer_major_version_passes_whatever_its_minor_number() -> None:
    assert GitHubCli(_version_of("gh version 3.0.0\n"), which=lambda _: "/usr/bin/gh").ready()


def test_gh_says_whether_it_is_installed_apart_from_being_signed_in() -> None:
    assert GitHubCli(Recorder(), which=lambda _: "/usr/bin/gh").installed()
    assert not GitHubCli(Recorder(), which=lambda _: None).installed()
    assert GitHubCli(Recorder(status=1), which=lambda _: "/usr/bin/gh").installed()


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


def test_a_failed_git_command_shows_the_first_error_line() -> None:
    run = Answering({"add --": (128, "hint: ignore me\nfatal: not a git repository\nmore\n")})

    with pytest.raises(SourceUnavailableError) as raised:
        GitRepository(run).commit_and_push(WORKFLOW_PATH, SCHEDULE_COMMIT_MESSAGE)

    assert "'git add' did not work (git said: fatal: not a git repository)" in str(raised.value)


def test_a_web_address_in_what_git_said_loses_its_sign_in() -> None:
    said = "fatal: unable to access 'https://you:ghp_sekret@github.com/you/x.git/': nope\n"
    run = Answering({"push": (128, said)})

    with pytest.raises(SourceUnavailableError) as raised:
        GitRepository(run).push()

    assert "ghp_sekret" not in str(raised.value)
    assert "github.com/you/x.git" in str(raised.value)


@pytest.mark.parametrize(
    "rejection",
    [
        " ! [remote rejected] main -> main (refusing to allow an OAuth App to create or update "
        "workflow `.github/workflows/threadline-run.yml` without `workflow` scope)",
        " ! [remote rejected] main -> main (refusing to allow a Personal Access Token to create "
        "or update workflow `.github/workflows/threadline-run.yml` without `workflow` scope)",
        " ! [remote rejected] main -> main (refusing to allow an OAuth App to create or update "
        "workflow `.github/workflows/threadline-run.yml` without workflow scope)",
    ],
)
def test_a_push_refused_for_the_workflow_permission_says_how_to_add_it(rejection: str) -> None:
    said = f"To https://github.com/you/x.git\n{rejection}\nerror: failed to push some refs\n"
    run = Answering({"push": (1, said)})

    with pytest.raises(SourceUnavailableError) as raised:
        GitRepository(run).push()

    assert str(raised.value) == (
        "GitHub refused the change because your sign-in may not change workflow files. "
        "Run: gh auth refresh -h github.com -s workflow, then run this step again."
    )


def test_another_refused_push_still_shows_what_git_said() -> None:
    said = " ! [remote rejected] main -> main (protected branch hook declined)\nerror: failed\n"
    run = Answering({"push": (1, said)})

    with pytest.raises(SourceUnavailableError, match="git said: error: failed"):
        GitRepository(run).push()


def test_git_without_a_name_gets_the_two_lines_that_give_it_one() -> None:
    said = (
        "Author identity unknown\n\n*** Please tell me who you are.\n\nRun\n\n"
        '  git config --global user.email "you@example.com"\n'
        "fatal: unable to auto-detect email address\n"
    )
    run = Answering({"commit -m": (128, said)})

    with pytest.raises(SourceUnavailableError) as raised:
        GitRepository(run).commit(WORKFLOW_PATH, SCHEDULE_COMMIT_MESSAGE)

    message = str(raised.value)
    assert 'git config --global user.name "Your Name"' in message
    assert 'git config --global user.email "you@example.com"' in message
    assert "did not work" not in message


def test_git_says_what_differs_in_one_file() -> None:
    changed = Answering({"status --porcelain": (0, " M .github/workflows/threadline-run.yml\n")})
    clean = Answering({})

    assert GitRepository(changed).has_uncommitted(WORKFLOW_PATH)
    assert not GitRepository(clean).has_uncommitted(WORKFLOW_PATH)


def test_a_commit_that_is_not_on_github_is_found_by_comparing_with_the_upstream() -> None:
    ahead = Answering({"log --oneline": (0, "abc123 Set the daily Threadline time\n")})

    assert GitRepository(ahead).has_unpushed(WORKFLOW_PATH)
    assert ahead.calls[0][0][:4] == ["git", "log", "--oneline", "@{upstream}..HEAD"]
    assert not GitRepository(Answering({})).has_unpushed(WORKFLOW_PATH)


NO_UPSTREAM = (128, "fatal: no upstream configured for branch 'main'\n")
AHEAD = "abc123 Set the daily Threadline time\n"
UPSTREAM_LOG = "log --oneline @{upstream}..HEAD"
DEFAULT_BRANCH_LOG = "log --oneline origin/main..HEAD"


class GitAnswers(Recorder):
    """A git runner answering by the start of the command, e.g. a log with one range."""

    def __init__(self, answers: dict[str, tuple[int, str]]) -> None:
        super().__init__()
        self.answers = answers

    def __call__(self, arguments: Sequence[str], stdin: str | None) -> tuple[int, str]:
        super().__call__(arguments, stdin)
        command = " ".join(arguments[1:])
        for start, answer in self.answers.items():
            if command.startswith(start):
                return answer
        return 128, "fatal: not answered in this test\n"

    def asked(self, start: str) -> bool:
        """Whether a command starting with ``start`` was run."""
        return any(" ".join(call[0][1:]).startswith(start) for call in self.calls)


def test_without_an_upstream_the_default_branch_on_github_is_compared() -> None:
    run = GitAnswers(
        {
            UPSTREAM_LOG: NO_UPSTREAM,
            "symbolic-ref --short": (0, "origin/main\n"),
            DEFAULT_BRANCH_LOG: (0, AHEAD),
        }
    )

    assert GitRepository(run).has_unpushed(WORKFLOW_PATH)
    assert run.asked(DEFAULT_BRANCH_LOG)


def test_a_default_branch_git_cannot_name_is_found_by_its_usual_names() -> None:
    run = GitAnswers(
        {
            UPSTREAM_LOG: NO_UPSTREAM,
            "symbolic-ref --short": (
                128,
                "fatal: ref refs/remotes/origin/HEAD is not a symbolic ref\n",
            ),
            "rev-parse --verify --quiet origin/main": (0, "abc123\n"),
            DEFAULT_BRANCH_LOG: (0, ""),
        }
    )

    assert not GitRepository(run).has_unpushed(WORKFLOW_PATH)
    assert run.asked(DEFAULT_BRANCH_LOG)


def test_with_nothing_on_github_to_compare_with_the_file_is_not_called_unsent() -> None:
    run = GitAnswers(
        {
            UPSTREAM_LOG: NO_UPSTREAM,
            "symbolic-ref --short": (128, "fatal: no such ref\n"),
            "rev-parse --verify --quiet": (1, ""),
        }
    )

    assert not GitRepository(run).has_unpushed(WORKFLOW_PATH)
    assert not run.asked(DEFAULT_BRANCH_LOG)


def test_a_warning_git_printed_does_not_make_a_clean_file_look_changed() -> None:
    quiet = Answering({"status --porcelain": (0, ""), "log --oneline": (0, "")})
    noisy = Answering({"status --porcelain": (0, "warning: LF will be replaced by CRLF\n")})
    repository = GitRepository(quiet, run_for_errors=noisy)

    assert not repository.has_uncommitted(WORKFLOW_PATH)
    assert not repository.has_unpushed(WORKFLOW_PATH)
    assert noisy.calls == []


def test_what_a_failed_git_command_printed_as_errors_is_still_shown() -> None:
    plain = Answering({"add --": (128, "")})
    merged = Answering({"add --": (128, "fatal: not a git repository\n")})

    with pytest.raises(SourceUnavailableError) as raised:
        GitRepository(plain, run_for_errors=merged).commit_and_push(
            WORKFLOW_PATH, SCHEDULE_COMMIT_MESSAGE
        )

    assert "git said: fatal: not a git repository" in str(raised.value)
    assert plain.calls == []


def test_git_pushes_what_is_already_committed() -> None:
    run = Recorder()

    GitRepository(run).push()

    assert [call[0] for call in run.calls] == [["git", "push"]]


def test_the_runner_can_hand_back_what_a_program_printed_as_errors_too() -> None:
    script = "import sys; print('out'); print('oops', file=sys.stderr); sys.exit(3)"
    command = ["python", "-c", script]

    merged = run_command(Path.cwd(), which=lambda _: sys.executable, merge_errors=True)
    plain = run_command(Path.cwd(), which=lambda _: sys.executable)

    assert merged(command, None) == (3, "out\noops\n")
    assert plain(command, None) == (3, "out\n")
