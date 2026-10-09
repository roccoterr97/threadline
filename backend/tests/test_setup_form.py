"""The set-up page: the shared conversation, the page's IO, and the local server."""

from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any

import pytest

from tracker.infrastructure.setup_form import conversation as conversation_module
from tracker.infrastructure.setup_form.conversation import (
    HIDDEN_ANSWER,
    Conversation,
    Outcome,
    QuestionKind,
)
from tracker.infrastructure.setup_form.io import FormIO
from tracker.infrastructure.setup_form.server import SetupForm, open_setup_form
from tracker.shared.constants.setup import FORM_IDLE_LIMIT_SECONDS, FORM_KEY_HEADER
from tracker.shared.errors import SetupStoppedError


class TickingClock:
    """A clock that moves only when told."""

    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture(autouse=True)
def quick_waits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(conversation_module, "FORM_WAIT_SLICE_SECONDS", 0.01)


def answer_soon(talk: Conversation, value: str, *, question_id: int | None = None) -> None:
    """Answer the open question from another thread, as the page would."""

    def answer() -> None:
        while True:
            snapshot = talk.snapshot(0)
            question = snapshot["question"]
            if isinstance(question, dict):
                talk.answer(question_id if question_id is not None else question["id"], value)
                return

    threading.Thread(target=answer, daemon=True).start()


# --- The conversation ----------------------------------------------------------


def test_a_question_waits_for_the_page_and_records_the_answer() -> None:
    talk = Conversation()
    talk.say("Hello")
    answer_soon(talk, "abc")

    assert talk.ask(QuestionKind.TEXT, "Project address", "x") == "abc"

    snapshot = talk.snapshot(0)
    assert snapshot["entries"] == [
        {"kind": "said", "text": "Hello", "detail": ""},
        {"kind": "answer", "text": "Project address", "detail": "abc"},
    ]
    assert snapshot["question"] is None
    assert snapshot["next"] == 2


def test_a_secret_answer_is_recorded_as_hidden() -> None:
    talk = Conversation()
    answer_soon(talk, "sb_secret_x")

    assert talk.ask(QuestionKind.SECRET, "Secret key") == "sb_secret_x"

    entries: Any = talk.snapshot(0)["entries"]
    assert entries[0]["detail"] == HIDDEN_ANSWER
    assert "sb_secret_x" not in json.dumps(talk.snapshot(0))


def test_an_answer_to_an_old_question_is_ignored() -> None:
    talk = Conversation()

    assert talk.answer(99, "late") is False
    answer_soon(talk, "stale", question_id=42)
    answer_soon(talk, "fresh")

    assert talk.ask(QuestionKind.TEXT, "Name") == "fresh"


def test_the_page_only_gets_entries_after_the_ones_it_has() -> None:
    talk = Conversation()
    talk.say("one")
    talk.say("two")
    talk.link("https://example.com")

    snapshot = talk.snapshot(2)

    assert snapshot["entries"] == [{"kind": "link", "text": "https://example.com", "detail": ""}]
    assert snapshot["next"] == 3


def test_stopping_from_the_page_raises_in_the_open_question() -> None:
    talk = Conversation()
    threading.Thread(target=talk.stop, daemon=True).start()

    with pytest.raises(SetupStoppedError, match="you stopped the set-up from the page"):
        talk.ask(QuestionKind.CONTINUE, "Once you have saved")


def test_a_page_not_seen_for_too_long_stops_the_set_up() -> None:
    clock = TickingClock()
    talk = Conversation(clock=clock)
    clock.now += FORM_IDLE_LIMIT_SECONDS + 1

    with pytest.raises(SetupStoppedError, match="left alone for too long"):
        talk.ask(QuestionKind.TEXT, "Name")


def test_a_look_from_the_page_counts_as_a_sign_of_life() -> None:
    clock = TickingClock()
    talk = Conversation(clock=clock)
    clock.now += FORM_IDLE_LIMIT_SECONDS - 1
    talk.snapshot(0)
    clock.now += 2
    answer_soon(talk, "still here")

    assert talk.ask(QuestionKind.TEXT, "Name") == "still here"


def test_the_ending_is_shown_once_the_page_has_fetched_it() -> None:
    talk = Conversation()
    talk.finish(Outcome(ok=True, message="All done."))

    assert talk.farewell_seen() is False
    assert talk.snapshot(0)["finished"] == {"ok": True, "message": "All done."}
    assert talk.farewell_seen() is True


# --- The page's IO -------------------------------------------------------------


def test_form_io_echoes_what_is_said_and_asked_but_never_an_answer() -> None:
    talk = Conversation()
    echoed: list[str] = []
    io = FormIO(talk, echoed.append)
    io.say("Welcome")
    answer_soon(talk, "sb_secret_x")

    assert io.ask_secret("Secret key") == "sb_secret_x"
    assert echoed == ["Welcome", "? Secret key"]


def test_form_io_falls_back_to_the_default_on_an_empty_answer() -> None:
    talk = Conversation()
    io = FormIO(talk, lambda _: None)
    answer_soon(talk, "")

    assert io.ask("Time zone", default="Europe/Rome") == "Europe/Rome"


def test_form_io_reads_yes_and_no_and_falls_back_to_the_default() -> None:
    talk = Conversation()
    io = FormIO(talk, lambda _: None)
    answer_soon(talk, "yes")
    assert io.confirm("Apply?", default=False) is True
    answer_soon(talk, "no")
    assert io.confirm("Apply?", default=True) is False
    answer_soon(talk, "maybe")
    assert io.confirm("Apply?", default=True) is True


def test_form_io_offers_a_page_as_a_link_without_opening_it() -> None:
    talk = Conversation()
    echoed: list[str] = []
    io = FormIO(talk, echoed.append)

    io.open_page("https://supabase.com/dashboard")

    entries: Any = talk.snapshot(0)["entries"]
    assert entries == [{"kind": "link", "text": "https://supabase.com/dashboard", "detail": ""}]
    assert echoed == ["  Open https://supabase.com/dashboard"]


def test_form_io_pause_waits_for_a_click() -> None:
    talk = Conversation()
    io = FormIO(talk, lambda _: None)
    answer_soon(talk, "")

    io.pause("Once you have saved")

    entries: Any = talk.snapshot(0)["entries"]
    assert entries[0]["text"] == "Once you have saved"


# --- The server ----------------------------------------------------------------


@pytest.fixture
def form(monkeypatch: pytest.MonkeyPatch) -> Iterator[SetupForm]:
    monkeypatch.setattr("tracker.infrastructure.setup_form.server.FORM_FAREWELL_SECONDS", 0.05)
    opened: list[str] = []
    running = open_setup_form(lambda _: None, open_browser=lambda url: opened.append(url) is None)
    assert opened == [running.url]
    yield running
    running.close()


def call(
    form: SetupForm,
    path: str,
    *,
    key: str | None = None,
    body: dict[str, object] | None = None,
    host: str | None = None,
) -> tuple[int, bytes, dict[str, str]]:
    base, fragment = form.url.split("#")
    request = urllib.request.Request(base.rstrip("/") + path)
    if key is not None:
        request.add_header(FORM_KEY_HEADER, fragment if key == "right" else key)
    if host is not None:
        request.add_header("Host", host)
    if body is not None:
        request.data = json.dumps(body).encode()
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310 - loopback only
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, error.read(), dict(error.headers)


def test_the_page_is_served_on_the_loopback_address_only(form: SetupForm) -> None:
    assert form.url.startswith("http://127.0.0.1:")
    status, body, headers = call(form, "/")

    assert status == 200
    assert b"Threadline set-up" in body
    assert headers["Content-Security-Policy"].startswith("default-src 'none'")
    assert headers["Cache-Control"] == "no-store"
    assert call(form, "/page.js")[0] == 200
    assert call(form, "/page.css")[0] == 200
    assert call(form, "/nothing")[0] == 404


def test_the_state_needs_the_key(form: SetupForm) -> None:
    form.conversation.say("Hello")

    assert call(form, "/api/state")[0] == 403
    assert call(form, "/api/state", key="wrong")[0] == 403
    status, body, _ = call(form, "/api/state?after=0", key="right")

    assert status == 200
    assert json.loads(body)["entries"][0]["text"] == "Hello"


def test_a_request_from_another_host_name_is_refused(form: SetupForm) -> None:
    assert call(form, "/", host="evil.example:80")[0] == 403
    assert call(form, "/api/state", key="right", host="evil.example:80")[0] == 403


def test_an_answer_reaches_the_waiting_question(form: SetupForm) -> None:
    answers: list[str] = []

    def ask() -> None:
        answers.append(form.io.ask("Name"))

    worker = threading.Thread(target=ask, daemon=True)
    worker.start()
    question: dict[str, Any] | None = None
    while question is None:
        question = json.loads(call(form, "/api/state", key="right")[1])["question"]

    status, body, _ = call(
        form, "/api/answer", key="right", body={"id": question["id"], "value": "Sam"}
    )
    worker.join(timeout=5)

    assert status == 200
    assert json.loads(body) == {"ok": True}
    assert answers == ["Sam"]


def test_an_answer_without_a_key_or_with_a_bad_body_is_refused(form: SetupForm) -> None:
    assert call(form, "/api/answer", body={"id": 1, "value": "x"})[0] == 403
    assert call(form, "/api/answer", key="right", body={})[1] == b'{"ok": false}'
    status, _, _ = call(form, "/api/stop", key="wrong", body={})
    assert status == 403


def test_stop_from_the_page_ends_the_open_question(form: SetupForm) -> None:
    outcome: list[str] = []

    def ask() -> None:
        try:
            form.io.pause("Once you have saved")
        except SetupStoppedError as error:
            outcome.append(error.message)

    worker = threading.Thread(target=ask, daemon=True)
    worker.start()
    while json.loads(call(form, "/api/state", key="right")[1])["question"] is None:
        pass

    assert call(form, "/api/stop", key="right", body={})[0] == 200
    worker.join(timeout=5)

    assert outcome == ["you stopped the set-up from the page"]


def test_finish_shows_the_ending_and_waits_for_the_page(form: SetupForm) -> None:
    form.finish(ok=False, message="Stopped before the end.")

    finished = json.loads(call(form, "/api/state", key="right")[1])["finished"]

    assert finished == {"ok": False, "message": "Stopped before the end."}


# --- The command and the wizard ------------------------------------------------


def test_setup_help_offers_the_browser() -> None:
    from typer.testing import CliRunner

    from tracker.cli.main import build_cli

    result = CliRunner().invoke(build_cli(), ["setup", "--help"], env={"COLUMNS": "200"})

    assert result.exit_code == 0
    # On GitHub the help is coloured; the codes would split the word.
    plain = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    assert "--browser" in plain


def test_the_terminal_pause_asks_for_enter(monkeypatch: pytest.MonkeyPatch) -> None:
    from tracker.infrastructure import terminal_io

    prompts: list[str] = []
    monkeypatch.setattr(
        terminal_io.typer, "prompt", lambda text, **kwargs: prompts.append(text) or ""
    )

    terminal_io.TerminalIO().pause("Once you have saved")

    assert prompts == ["Once you have saved, press Enter"]


@pytest.mark.asyncio
async def test_the_wizard_stops_cleanly_when_the_page_stops_it() -> None:
    from tests.setup_world import make_world
    from tracker.services.setup.models import StepName
    from tracker.services.setup.wizard import SetupWizard

    class StoppingStep:
        name = StepName.LOGIN
        title = "Your dashboard login"

        async def is_done(self, ctx: Any) -> bool:
            return False

        async def run(self, ctx: Any) -> None:
            message = "you stopped the set-up from the page"
            raise SetupStoppedError(message)

    world = make_world()
    wizard = SetupWizard(world.context(), [StoppingStep()])

    assert await wizard.run_core() is False
    assert "Stopped here: you stopped the set-up from the page." in world.io.said
    assert "Fix that" not in world.io.text()
