"""The GitHub CLI, git and the workflow file, as the set-up uses them.

A value is only ever handed to ``gh`` on its standard input — never as a
command-line argument, which other programs on the machine can read, and never
in a log line. What ``gh`` and ``git`` print is not logged either: only the
exit status is.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final

from pydantic import SecretStr

from tracker.shared.constants.github import COPY_REMOTE
from tracker.shared.errors import SourceUnavailableError
from tracker.shared.logging import get_logger

#: Seconds one ``gh`` or ``git`` command may take.
COMMAND_TIMEOUT_SECONDS: Final[float] = 60.0

_GH: Final[str] = "gh"
_GIT: Final[str] = "git"

_log = get_logger(__name__)

#: Runs a command: (arguments, text for its standard input) -> (exit status, output).
Runner = Callable[[Sequence[str], str | None], tuple[int, str]]


def run_command(cwd: Path) -> Runner:
    """Build a runner that starts commands in one folder, with no shell.

    Args:
        cwd: The folder commands run in: the repository.

    Returns:
        The runner.
    """

    def run(arguments: Sequence[str], stdin: str | None) -> tuple[int, str]:
        try:
            done = subprocess.run(
                list(arguments),
                cwd=cwd,
                input=stdin,
                capture_output=True,
                text=True,
                check=False,
                timeout=COMMAND_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            _log.warning("command_not_run", program=arguments[0], error_type=type(error).__name__)
            return 1, ""
        return done.returncode, done.stdout

    return run


class GitHubCli:
    """Saves Actions secrets and variables with the GitHub CLI, when it is signed in."""

    def __init__(self, run: Runner, which: Callable[[str], str | None] = shutil.which) -> None:
        """Bind the helper to a command runner.

        Args:
            run: Runs one command in the repository.
            which: Finds a program on the machine; replaced in tests.
        """
        self._run = run
        self._which = which

    def ready(self) -> bool:
        """Tell whether ``gh`` is installed and signed in."""
        if self._which(_GH) is None:
            return False
        status, _ = self._run([_GH, "auth", "status"], None)
        return status == 0

    def repository(self) -> str | None:
        """Name the GitHub repository this folder belongs to, as ``owner/name``."""
        status, output = self._run(
            [_GH, "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"], None
        )
        name = output.strip()
        return name if status == 0 and name.count("/") == 1 else None

    def set_secret(self, repository: str, name: str, value: SecretStr) -> None:
        """Save one Actions secret; the value goes through standard input only.

        Raises:
            SourceUnavailableError: If ``gh`` did not save it.
        """
        self._save(["secret", "set", name, "--repo", repository], value.get_secret_value(), name)

    def set_variable(self, repository: str, name: str, value: str) -> None:
        """Save one Actions variable; the value goes through standard input only.

        Raises:
            SourceUnavailableError: If ``gh`` did not save it.
        """
        self._save(["variable", "set", name, "--repo", repository], value, name)

    def create_private_copy(self, name: str) -> None:
        """Create a private repository from this folder, link it as ``origin`` and push.

        Args:
            name: The new repository's name, under the signed-in account.

        Raises:
            SourceUnavailableError: If ``gh`` did not create it.
        """
        status, _ = self._run(
            [
                _GH, "repo", "create", name, "--private",
                "--source", ".", "--remote", COPY_REMOTE, "--push",
            ],
            None,
        )  # fmt: skip
        if status != 0:
            _log.warning("github_copy_not_created", status=status)
            message = "the GitHub CLI could not create your copy - run 'gh auth status' to see why"
            raise SourceUnavailableError(message)
        _log.info("github_copy_created")

    def _save(self, arguments: list[str], value: str, name: str) -> None:
        """Run one ``gh … set`` command with the value on standard input."""
        status, _ = self._run([_GH, *arguments], value)
        if status != 0:
            _log.warning("github_setting_not_saved", setting=name, status=status)
            message = f"the GitHub CLI could not save {name}"
            raise SourceUnavailableError(message)


class GitRepository:
    """Commits and pushes one file, only when the owner said yes."""

    def __init__(self, run: Runner) -> None:
        """Bind the helper to a command runner.

        Args:
            run: Runs one command in the repository.
        """
        self._run = run

    def origin_url(self) -> str | None:
        """Return where ``origin`` points, or ``None`` when there is no such link."""
        status, output = self._run([_GIT, "remote", "get-url", COPY_REMOTE], None)
        url = output.strip()
        return url if status == 0 and url else None

    def rename_origin(self, new_name: str) -> None:
        """Keep the current ``origin`` link under another name.

        Raises:
            SourceUnavailableError: If git did not rename it.
        """
        self._git(["remote", "rename", COPY_REMOTE, new_name])

    def commit(self, path: str, message: str) -> None:
        """Run ``git add`` and ``git commit`` for one file.

        Args:
            path: The file, relative to the repository.
            message: The commit message.

        Raises:
            SourceUnavailableError: If either did not work.
        """
        self._git(["add", "--", path])
        self._git(["commit", "-m", message, "--", path])

    def commit_and_push(self, path: str, message: str) -> None:
        """Run ``git add``, ``git commit`` and ``git push`` for one file.

        Args:
            path: The file, relative to the repository.
            message: The commit message.

        Raises:
            SourceUnavailableError: If one of the three did not work.
        """
        self.commit(path, message)
        self._git(["push"])

    def _git(self, arguments: list[str]) -> None:
        """Run one git command, turning a failure into a plain error."""
        status, _ = self._run([_GIT, *arguments], None)
        if status != 0:
            _log.warning("git_command_failed", command=arguments[0], status=status)
            message = f"'git {arguments[0]}' did not work - run it yourself to see why"
            raise SourceUnavailableError(message)


class TextFile:
    """One text file of the repository, such as the workflow."""

    def __init__(self, path: Path) -> None:
        """Bind the helper to a file.

        Args:
            path: Where the file is.
        """
        self._path = path

    def read(self) -> str:
        """Return the file's content."""
        return self._path.read_text(encoding="utf-8")

    def write(self, text: str) -> None:
        """Replace the file's content."""
        self._path.write_text(text, encoding="utf-8")
