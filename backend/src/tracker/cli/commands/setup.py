"""``tracker setup``: the guided set-up, all of it or one step, here or on a page."""

from __future__ import annotations

import asyncio
import signal
import threading
from collections.abc import Coroutine, Iterator
from contextlib import contextmanager
from types import FrameType
from typing import Annotated, Final

import typer

from tracker.cli.commands.doctor import print_doctor_report
from tracker.cli.setup_wiring import build_context
from tracker.infrastructure.setup_form import open_setup_form
from tracker.infrastructure.supabase_platform import SupabasePlatform
from tracker.services.setup.models import StepName
from tracker.services.setup.ports import SetupIO
from tracker.services.setup.wizard import SetupWizard, default_steps
from tracker.shared import config

#: Panel the root help groups this command under.
HELP_PANEL: Final[str] = "system"

#: What the page says at the end.
_FINISHED_ALL: Final[str] = "All done. Threadline is set up."
_FINISHED_STEP: Final[str] = "Done. This step is finished."
_NOT_FINISHED: Final[str] = (
    "Stopped before the end. Run 'uv run tracker setup' again to carry on; "
    "what is finished stays saved."
)

StepArgument = Annotated[
    StepName | None,
    typer.Argument(
        help="Run only this step. Without it, every unfinished step runs in order.",
        show_default=False,
    ),
]

BrowserOption = Annotated[
    bool,
    typer.Option(
        "--browser",
        help="Ask the questions on a page in your web browser instead of here. "
        "Keys go into hidden fields; the page is served to this computer only.",
    ),
]


def register(cli: typer.Typer) -> None:
    """Attach the set-up to the root application.

    Args:
        cli: The root Typer application.
    """
    cli.command("setup", rich_help_panel=HELP_PANEL)(setup)


def setup(step: StepArgument = None, browser: BrowserOption = False) -> None:
    """Set up every connection, checking each one live before saving it.

    Steps: supabase, encryption, database, login, categories, timezone, mailbox,
    microsoft, linkedin, dashboard, schedule, github, refresh (the dashboard's
    Refresh now button), and cloud (the alternative to GitHub). Running it
    again carries on where it stopped.
    """
    if not browser:
        if not _run_in_terminal(step):
            raise typer.Exit(1)
        return
    form = open_setup_form(typer.echo)
    try:
        finished = _run_with(form.io, step)
        form.finish(ok=finished, message=_ending(step, finished=finished))
    finally:
        form.close()
    if not finished:
        raise typer.Exit(1)


def _run_in_terminal(step: StepName | None) -> bool:
    """Run here, with the final check printed after a full run."""
    if not run_interruptible(_run(step)):
        return False
    if step is not None:
        return True
    typer.echo("")
    typer.echo("Final check of every connection:")
    config.reset_settings_cache()
    return print_doctor_report()


def _run_with(io: SetupIO, step: StepName | None) -> bool:
    """Run through the page, with the final check shown there after a full run."""
    if not run_interruptible(_run(step, io)):
        return False
    if step is not None:
        return True
    io.say("")
    io.say("Final check of every connection:")
    config.reset_settings_cache()
    return print_doctor_report(io.say)


def run_interruptible[T](main: Coroutine[object, object, T]) -> T:
    """Run the wizard so that a single Ctrl-C stops it at once.

    ``asyncio.run`` swaps Python's own Ctrl-C handler for one that only asks
    the running task to stop at its next pause. A question waiting for typing,
    here or on the page, never pauses, so that first Ctrl-C was lost and the
    answer typed after it was still saved. ``asyncio.run`` leaves a handler of
    our own in place, and this one stops the set-up where it is.

    Args:
        main: The wizard's run.

    Returns:
        What the run returned.

    Raises:
        KeyboardInterrupt: When Ctrl-C is pressed.
    """
    with _interrupt_at_once():
        return asyncio.run(main)


@contextmanager
def _interrupt_at_once() -> Iterator[None]:
    """Raise ``KeyboardInterrupt`` on Ctrl-C, then put the previous handler back."""
    previous = signal.getsignal(signal.SIGINT)
    owns_signals = threading.current_thread() is threading.main_thread()
    if not owns_signals or previous is not signal.default_int_handler:
        yield
        return
    signal.signal(signal.SIGINT, _raise_interrupt)
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, previous)


def _raise_interrupt(_signum: int, _frame: FrameType | None) -> None:
    """Stop where the program is, as Python's own Ctrl-C handler does."""
    raise KeyboardInterrupt


def _ending(step: StepName | None, *, finished: bool) -> str:
    """The last line the page shows."""
    if not finished:
        return _NOT_FINISHED
    return _FINISHED_STEP if step is not None else _FINISHED_ALL


async def _run(step: StepName | None, io: SetupIO | None = None) -> bool:
    """Run the wizard on real clients."""
    async with SupabasePlatform() as platform:
        wizard = SetupWizard(build_context(config.ENV_FILE, platform, io), default_steps())
        if step is None:
            return await wizard.run_all()
        return await wizard.run_one(step)
