"""Builds the dashboard on this computer with Node.js, for contributors.

Owners never need this: the set-up downloads the dashboard the release
workflow built. A contributor testing their own changes to ``frontend/`` can
publish those instead, when Node.js 22 or newer is installed. The commands run
without a shell and their output is not logged, only their exit status.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Final

from tracker.shared.constants.dashboard import (
    LOCAL_BUILD_ENVIRONMENT,
    LOCAL_BUILD_TIMEOUT_SECONDS,
    NODE_MIN_MAJOR,
    NODE_VERSION_TIMEOUT_SECONDS,
)
from tracker.shared.errors import DashboardBuildError, DashboardPackageError
from tracker.shared.logging import get_logger

_NODE: Final[str] = "node"
_NPM: Final[str] = "npm"
_NODE_VERSION: Final[re.Pattern[str]] = re.compile(r"^v?(\d+)\.")
_PACKAGE_FILES: Final[tuple[str, ...]] = ("package.json", "package-lock.json")
_DEPENDENCIES: Final[str] = "node_modules"
_BUILD_OUTPUT: Final[str] = "dist"

_log = get_logger(__name__)

#: Runs a program: (arguments, folder, extra settings, seconds) -> (exit status, output).
ProgramRunner = Callable[[Sequence[str], Path, Mapping[str, str], float], tuple[int, str]]


def run_program(
    arguments: Sequence[str],
    cwd: Path,
    extra_env: Mapping[str, str],
    timeout: float,
    which: Callable[[str], str | None] = shutil.which,
) -> tuple[int, str]:
    """Run one program with no shell and return its exit status and output.

    The program inherits this process's environment (it needs ``PATH`` and
    npm's own settings) with ``extra_env`` laid over it. It is looked up
    first, because without a shell Windows finds ``npm.cmd`` only by its full path.

    Args:
        arguments: The program and its arguments.
        cwd: The folder it runs in.
        extra_env: Settings added for it alone.
        timeout: Seconds it may take.
        which: Finds a program on the machine; replaced in tests.

    Returns:
        The exit status (1 when it could not be started or took too long) and
        what it printed.
    """
    program = which(arguments[0]) or arguments[0]
    try:
        done = subprocess.run(
            [program, *arguments[1:]],
            cwd=cwd,
            env={**os.environ, **extra_env},
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        _log.warning("program_not_run", program=arguments[0], error_type=type(error).__name__)
        return 1, ""
    return done.returncode, done.stdout


class LocalDashboardBuild:
    """Runs ``npm run build`` in ``frontend/`` and reads what it wrote."""

    def __init__(
        self,
        frontend: Path,
        run: ProgramRunner = run_program,
        which: Callable[[str], str | None] = shutil.which,
    ) -> None:
        """Bind the builder to the dashboard's folder.

        Args:
            frontend: The ``frontend`` folder of the repository.
            run: Runs one program.
            which: Finds a program on the ``PATH``.
        """
        self._frontend = frontend
        self._run = run
        self._which = which

    def available(self) -> bool:
        """Tell whether the source is here and Node.js 22 or newer is installed."""
        if not all((self._frontend / name).is_file() for name in _PACKAGE_FILES):
            return False
        if self._which(_NODE) is None or self._which(_NPM) is None:
            return False
        status, output = self._run(
            [_NODE, "--version"], self._frontend, {}, NODE_VERSION_TIMEOUT_SECONDS
        )
        found = _NODE_VERSION.match(output.strip())
        return status == 0 and found is not None and int(found.group(1)) >= NODE_MIN_MAJOR

    def build(self) -> dict[str, bytes]:
        """Install the dependencies when missing, build, and read every built file.

        Returns:
            Each file by its path inside the site, such as ``assets/index.js``.

        Raises:
            DashboardBuildError: If a command failed.
            DashboardPackageError: If the build wrote a link instead of a file.
        """
        if not (self._frontend / _DEPENDENCIES).is_dir():
            self._step([_NPM, "ci"], "npm ci")
        self._step([_NPM, "run", "build"], "npm run build")
        _log.info("dashboard_built_locally")
        return read_site(self._frontend / _BUILD_OUTPUT)

    def _step(self, arguments: Sequence[str], label: str) -> None:
        """Run one npm command in the dashboard's folder."""
        status, _output = self._run(
            arguments, self._frontend, LOCAL_BUILD_ENVIRONMENT, LOCAL_BUILD_TIMEOUT_SECONDS
        )
        if status != 0:
            _log.error("dashboard_build_failed", command=label, status=status)
            message = f"'{label}' did not finish - run it in the frontend folder to see why"
            raise DashboardBuildError(message)


def read_site(folder: Path) -> dict[str, bytes]:
    """Read every file below a built site's folder.

    Args:
        folder: The folder ``npm run build`` wrote.

    Returns:
        Each file by its path inside the site, with ``/`` between parts.

    Raises:
        DashboardBuildError: If the folder is missing.
        DashboardPackageError: If it holds a link, which could point anywhere.
    """
    if not folder.is_dir():
        message = f"the build wrote no {folder.name} folder"
        raise DashboardBuildError(message)
    files: dict[str, bytes] = {}
    for path in sorted(folder.rglob("*")):
        if path.is_symlink():
            message = f"the built dashboard holds a link, {path.relative_to(folder).as_posix()}"
            raise DashboardPackageError(message)
        if path.is_file():
            files[path.relative_to(folder).as_posix()] = path.read_bytes()
    return files
