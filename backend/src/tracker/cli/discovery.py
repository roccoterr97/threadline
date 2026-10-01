"""Automatic discovery of command modules.

Each module under :mod:`tracker.cli.commands` exposes a ``register`` function
that attaches its own commands to the root application. Discovery imports every
such module and calls it, in alphabetical order so the help stays stable.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable

import typer

from tracker.cli import commands
from tracker.shared.errors import ConfigurationError

#: Import path of the package that holds the command modules.
COMMAND_PACKAGE = commands.__name__

#: Name of the function every command module must expose.
REGISTER_FUNCTION = "register"


def command_module_names() -> tuple[str, ...]:
    """List the command modules available to the tool.

    Returns:
        The module names, alphabetically, without the package prefix. Modules
        whose name starts with an underscore are helpers and are skipped.
    """
    found = (
        module.name
        for module in pkgutil.iter_modules(commands.__path__)
        if not module.name.startswith("_")
    )
    return tuple(sorted(found))


def register_commands(cli: typer.Typer) -> tuple[str, ...]:
    """Attach every discovered command module to the application.

    Args:
        cli: The root Typer application.

    Returns:
        The names of the modules that were registered.

    Raises:
        ConfigurationError: If a module in the package does not expose
            ``register``. Skipping it silently would hide a whole command group.
    """
    names = command_module_names()
    for name in names:
        module = importlib.import_module(f"{COMMAND_PACKAGE}.{name}")
        register: Callable[[typer.Typer], None] | None = getattr(module, REGISTER_FUNCTION, None)
        if register is None or not callable(register):
            message = f"command module '{name}' does not expose {REGISTER_FUNCTION}()"
            raise ConfigurationError(message)
        register(cli)
    return names
