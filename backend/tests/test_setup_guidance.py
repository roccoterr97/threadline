"""How the guided set-up talks to a newcomer: answers, skips, log lines and the last words."""

from __future__ import annotations

from typing import Any

import pytest
from typer.testing import CliRunner

from tests.setup_world import OWNER_EMAIL, World, configured_env, make_world
from tests.test_setup_form import answer_soon
from tracker.cli.commands import doctor as doctor_command
from tracker.cli.commands import setup as setup_command
from tracker.cli.main import build_cli
from tracker.infrastructure import terminal_io
from tracker.infrastructure.setup_form.conversation import Conversation
from tracker.infrastructure.setup_form.io import FormIO
from tracker.infrastructure.terminal_io import TerminalIO
from tracker.services.doctor.models import ok
from tracker.services.doctor.service import DoctorReport
from tracker.services.setup.models import StepName
from tracker.services.setup.skipped_steps import SKIPPED_STEPS
from tracker.services.setup.step_categories import CategoriesStep
from tracker.services.setup.step_microsoft import MicrosoftStep
from tracker.services.setup.wizard import SetupWizard
from tracker.shared import config
from tracker.shared.errors import DatabaseUnavailableError
from tracker.shared.logging import get_logger, logs_kept_in

_SITE = "https://threadline-abc123.netlify.app"
_LOGIN = "you+threadline@example.com"


# --- "y" at a question with a suggestion ------------------------------------------


@pytest.mark.parametrize("typed", ["y", "Y", "yes", " YES ", "ok", "Ok"])
def test_the_terminal_reads_y_at_a_suggestion_as_keep_it(
    monkeypatch: pytest.MonkeyPatch, typed: str
) -> None:
    monkeypatch.setattr(terminal_io.typer, "prompt", lambda *_args, **_kwargs: typed)

    assert TerminalIO().ask("Your time zone", default="Europe/Paris") == "Europe/Paris"


def test_the_terminal_takes_y_as_typed_where_it_may_be_meant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(terminal_io.typer, "prompt", lambda *_args, **_kwargs: "y")

    assert TerminalIO().ask("Name for your copy", default="threadline", exact=True) == "y"
    assert TerminalIO().ask("Your LinkedIn profile address") == "y"


def test_the_terminal_keeps_any_other_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(terminal_io.typer, "prompt", lambda *_args, **_kwargs: "Asia/Tokyo")

    assert TerminalIO().ask("Your time zone", default="Europe/Paris") == "Asia/Tokyo"


def test_the_page_reads_y_at_a_suggestion_as_keep_it() -> None:
    talk = Conversation()
    io = FormIO(talk, lambda _: None)

    answer_soon(talk, "Y")
    assert io.ask("Your time zone", default="Europe/Paris") == "Europe/Paris"
    answer_soon(talk, "y")
    assert io.ask("Name for your copy", default="threadline", exact=True) == "y"


# --- Log lines stay off the screen -----------------------------------------------------


def test_log_lines_go_to_the_file_and_back_to_the_screen_afterwards(
    capsys: pytest.CaptureFixture[str],
) -> None:
    log_file = config.SETUP_LOG_FILE
    log = get_logger(__name__)

    with logs_kept_in(log_file):
        log.info("migration_applied", name="0001_schema")
    log.info("after_the_set_up")

    assert "migration_applied" in log_file.read_text(encoding="utf-8")
    assert "migration_applied" not in capsys.readouterr().err
    log.info("shown_again")
    assert "shown_again" in capsys.readouterr().err
    assert "after_the_set_up" not in log_file.read_text(encoding="utf-8")


def test_a_log_file_that_cannot_be_written_still_shows_the_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    unwritable = config.SETUP_LOG_FILE.parent / "missing-folder" / "setup.log"

    with logs_kept_in(unwritable):
        get_logger(__name__).warning("setup_step_stopped", step="mailbox")

    assert "setup_step_stopped" in capsys.readouterr().err


def test_the_doctor_shows_plain_lines_and_keeps_its_log_in_the_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def checked() -> DoctorReport:
        get_logger(__name__).info("doctor_finished", healthy=True, checks=1)
        return DoctorReport((ok("Database", "reachable"),))

    monkeypatch.setattr(doctor_command, "run_doctor", checked)

    result = CliRunner().invoke(build_cli(), ["doctor"])

    assert result.exit_code == 0
    assert "Database" in result.output
    assert "doctor_finished" not in result.output
    assert "doctor_finished" in config.SETUP_LOG_FILE.read_text(encoding="utf-8")


# --- Building the dashboard here only on request ----------------------------------------


def test_build_here_is_refused_with_a_step_that_does_not_publish_the_dashboard() -> None:
    result = CliRunner().invoke(build_cli(), ["setup", "linkedin", "--build-here"])

    assert result.exit_code == 2
    assert "dashboard" in result.output


def test_build_here_reaches_the_run_of_the_dashboard_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[dict[str, Any]] = []

    async def wizard(step: object, io: object = None, **options: Any) -> bool:
        asked.append({"step": step, **options})
        return True

    monkeypatch.setattr(setup_command, "_run", wizard)

    setup_command.setup("dashboard", build_here=True)

    assert asked == [{"step": StepName.DASHBOARD, "build_here": True}]


# --- An optional step said no to is not asked again ---------------------------------------


def _gmail_world(answers: list[str | bool], env: dict[str, str] | None = None) -> World:
    known = {"MAIL_SOURCES": "imap", "OWNER_EMAIL_ADDRESSES": OWNER_EMAIL}
    return make_world(answers, configured_env() | known | (env or {}))


@pytest.mark.asyncio
async def test_saying_no_to_outlook_is_remembered() -> None:
    world = _gmail_world([False])

    await MicrosoftStep().run(world.context())

    assert world.env.values[SKIPPED_STEPS] == "microsoft"


@pytest.mark.asyncio
async def test_a_later_full_run_does_not_ask_about_outlook_again() -> None:
    world = _gmail_world([], {SKIPPED_STEPS: "microsoft"})

    assert await SetupWizard(world.context(), [MicrosoftStep()]).run_core() is True

    assert "Skipped earlier. To add it: uv run tracker setup microsoft" in world.io.said
    assert world.microsoft.accesses == []


@pytest.mark.asyncio
async def test_running_outlook_by_name_asks_again_and_forgets_the_skip() -> None:
    world = _gmail_world([True], {SKIPPED_STEPS: "microsoft"})

    assert await SetupWizard(world.context(), [MicrosoftStep()]).run_one(StepName.MICROSOFT)

    assert world.microsoft.signed_in
    assert world.env.get(SKIPPED_STEPS) is None


@pytest.mark.asyncio
async def test_a_skip_does_not_hold_once_outlook_is_the_mailbox() -> None:
    env = configured_env() | {
        "MAIL_SOURCES": "outlook",
        "OWNER_EMAIL_ADDRESSES": OWNER_EMAIL,
        SKIPPED_STEPS: "microsoft",
    }
    world = make_world([], env)

    await MicrosoftStep().run(world.context())

    assert world.microsoft.signed_in
    assert not any("Skipped earlier" in line for line in world.io.said)


@pytest.mark.asyncio
async def test_saying_no_to_categories_is_remembered_and_not_asked_again() -> None:
    world = make_world([False], configured_env())

    await CategoriesStep().run(world.context())
    world.io.said.clear()
    await CategoriesStep().run(world.context())

    assert world.env.values[SKIPPED_STEPS] == "categories"
    assert world.io.said == ["Skipped earlier. To choose them: uv run tracker setup categories"]


# --- The last words say where and how to sign in -------------------------------------------


def _finished_world() -> World:
    world = make_world([], configured_env() | {"DASHBOARD_BASE_URL": _SITE})
    world.admin.users = {OWNER_EMAIL: "user-1", _LOGIN: "user-2"}
    world.admin.owners = ["user-2"]
    return world


@pytest.mark.asyncio
async def test_the_last_words_name_the_dashboard_and_the_login_address() -> None:
    world = _finished_world()

    assert await SetupWizard(world.context(), []).run_core()

    said = world.io.said
    ending = said[said.index("Set-up done.") :]
    assert ending[1:3] == [
        f"Your dashboard: {_SITE}",
        f"Sign in there with {_LOGIN}: a sign-in link is e-mailed to that address.",
    ]


@pytest.mark.asyncio
async def test_the_last_words_still_say_how_to_sign_in_when_supabase_cannot_say(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _finished_world()

    def down() -> tuple[str, ...]:
        message = "the database did not answer"
        raise DatabaseUnavailableError(message)

    monkeypatch.setattr(world.admin, "owner_ids", down)

    assert await SetupWizard(world.context(), []).run_core()

    text = world.io.text()
    assert f"Your dashboard: {_SITE}" in text
    assert "Sign in there with the address you gave for the dashboard login" in text
