"""``tracker setup``: the core steps, the extras or one step, here or on a page."""

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
from tracker.services.setup.models import StepGroup, StepName
from tracker.services.setup.ports import SetupIO
from tracker.services.setup.wizard import SetupWizard, default_steps
from tracker.shared import config

#: Panel the root help groups this command under.
HELP_PANEL: Final[str] = "system"

#: What the page says at the end.
_FINISHED_CORE: Final[str] = "All done. Threadline is set up."
_FINISHED_EXTRAS: Final[str] = "All done. The extras are set up."
_FINISHED_STEP: Final[str] = "Done. This step is finished."
_NOT_FINISHED: Final[str] = (
    "Stopped before the end. Run '{command}' again to carry on; what is finished stays saved."
)
#: How the owner types the set-up.
_COMMAND: Final[str] = "uv run tracker setup"

TargetArgument = Annotated[
    str | None,
    typer.Argument(
        metavar="[STEP]",
        help=(
            f"Run only this step, or '{StepGroup.EXTRAS}' for the optional steps. "
            "Without it, every unfinished core step runs in order."
        ),
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


def setup(target: TargetArgument = None, browser: BrowserOption = False) -> None:
    """Set up every connection, checking each one live before saving it.

    The core steps, run in order without an argument: supabase, encryption,
    database, login, categories, timezone, mailbox, microsoft, dashboard,
    schedule and github, which starts the first daily run. Running it again
    carries on where it stopped. 'extras' runs the optional steps: linkedin,
    refresh (the dashboard's Refresh now button and the on-time daily start)
    and cloud (the alternative to GitHub). A step's name runs that step alone.
    """
    request = parse_target(target)
    if not browser:
        if not _run_in_terminal(request):
            raise typer.Exit(1)
        return
    form = open_setup_form(typer.echo)
    try:
        finished = _run_with(form.io, request)
        form.finish(ok=finished, message=_ending(request, finished=finished))
    finally:
        form.close()
    if not finished:
        raise typer.Exit(1)


def parse_target(target: str | None) -> StepName | StepGroup:
    """Read what to run: nothing (the core steps), a half by name, or one step by name.

    Args:
        target: What was typed after ``tracker setup``, if anything.

    Returns:
        The step, or the half of the set-up, to run.

    Raises:
        typer.BadParameter: If it is neither a step nor a half.
    """
    if target is None:
        return StepGroup.CORE
    if target in StepGroup:
        return StepGroup(target)
    if target in StepName:
        return StepName(target)
    message = f"choose a step ({', '.join(StepName)}) or '{StepGroup.EXTRAS}'"
    raise typer.BadParameter(message)


def _run_in_terminal(request: StepName | StepGroup) -> bool:
    """Run here, with the final check printed after the core steps."""
    if not run_interruptible(_run(request)):
        return False
    if request is not StepGroup.CORE:
        return True
    typer.echo("")
    typer.echo("Final check of every connection:")
    config.reset_settings_cache()
    return print_doctor_report()


def _run_with(io: SetupIO, request: StepName | StepGroup) -> bool:
    """Run through the page, with the final check shown there after the core steps."""
    if not run_interruptible(_run(request, io)):
        return False
    if request is not StepGroup.CORE:
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


def _ending(request: StepName | StepGroup, *, finished: bool) -> str:
    """The last line the page shows."""
    if not finished:
        command = f"{_COMMAND} {request}" if request is not StepGroup.CORE else _COMMAND
        return _NOT_FINISHED.format(command=command)
    if request is StepGroup.CORE:
        return _FINISHED_CORE
    return _FINISHED_EXTRAS if request is StepGroup.EXTRAS else _FINISHED_STEP


async def _run(request: StepName | StepGroup, io: SetupIO | None = None) -> bool:
    """Run the wizard on real clients."""
    async with SupabasePlatform() as platform:
        wizard = SetupWizard(build_context(config.ENV_FILE, platform, io), default_steps())
        if request is StepGroup.CORE:
            return await wizard.run_core()
        if request is StepGroup.EXTRAS:
            return await wizard.run_extras()
        return await wizard.run_one(request)
