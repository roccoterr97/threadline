"""Ctrl-C during ``tracker setup``: one press stops it, here or on the page."""

from __future__ import annotations

import os
import signal
import socket
import sys
import threading
from typing import Any

import pytest

from tracker.cli.commands import setup as setup_command
from tracker.infrastructure.setup_form import conversation as conversation_module
from tracker.infrastructure.setup_form.server import SetupForm, open_setup_form
from tracker.services.setup.ports import SetupIO

#: Seconds before the test presses Ctrl-C, and before it answers anyway.
_PRESS_AFTER: float = 0.2
_ANSWER_AFTER: float = 1.0


def _press_ctrl_c() -> None:
    """Send SIGINT to this process the way a terminal does.

    On Windows ``os.kill`` with SIGINT ends the process outright, so the
    signal is raised inside the process instead; Python still runs the
    handler on the main thread, as it does for a real Ctrl-C.
    """
    if sys.platform == "win32":
        signal.raise_signal(signal.SIGINT)
        return
    os.kill(os.getpid(), signal.SIGINT)


def _press_ctrl_c_later() -> threading.Timer:
    """Press Ctrl-C from another thread after a moment."""
    timer = threading.Timer(_PRESS_AFTER, _press_ctrl_c)
    timer.start()
    return timer


def test_one_ctrl_c_stops_a_question_waiting_for_typing() -> None:
    saved: list[str] = []

    async def question() -> bool:
        signal.raise_signal(signal.SIGINT)
        # A prompt blocked in the terminal comes back here after the first Ctrl-C.
        saved.append("answer typed after Ctrl-C")
        return True

    with pytest.raises(KeyboardInterrupt):
        setup_command.run_interruptible(question())

    assert saved == []


def test_the_usual_ctrl_c_handler_is_put_back_afterwards() -> None:
    async def nothing() -> bool:
        return True

    assert setup_command.run_interruptible(nothing()) is True
    assert signal.getsignal(signal.SIGINT) is signal.default_int_handler


def test_one_ctrl_c_on_the_page_stops_and_closes_the_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(conversation_module, "FORM_WAIT_SLICE_SECONDS", 0.01)
    forms: list[SetupForm] = []
    saved: list[str] = []

    def open_quietly(echo: Any) -> SetupForm:
        form = open_setup_form(lambda _: None, open_browser=lambda _: True)
        forms.append(form)
        return form

    def answer_anyway() -> None:
        # Without the fix the first Ctrl-C is lost, and this answer would be saved.
        question: Any = forms[0].conversation.snapshot(0)["question"]
        if question is not None:
            forms[0].conversation.answer(question["id"], "Europe/Rome")

    async def wizard(step: object, io: SetupIO | None = None, **_options: object) -> bool:
        assert io is not None
        saved.append(io.ask("Your time zone", default="UTC"))
        return True

    monkeypatch.setattr(setup_command, "open_setup_form", open_quietly)
    monkeypatch.setattr(setup_command, "_run", wizard)
    pressed = _press_ctrl_c_later()
    answered = threading.Timer(_ANSWER_AFTER, answer_anyway)
    answered.start()
    try:
        with pytest.raises(KeyboardInterrupt):
            setup_command.setup(None, browser=True)
    finally:
        pressed.cancel()
        answered.cancel()

    assert saved == []
    port = int(forms[0].url.split(":")[2].split("/")[0])
    with pytest.raises(OSError), socket.create_connection(("127.0.0.1", port), timeout=1):
        pass
