"""The GitHub CLI, git and the workflow file, as the set-up uses them.

A value is only ever handed to ``gh`` on its standard input — never as a
command-line argument, which other programs on the machine can read, and never
in a log line. What ``gh`` and ``git`` print is not logged either: only the
exit status is.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from pydantic import SecretStr

from tracker.shared.constants.github import COPY_REMOTE
from tracker.shared.errors import SourceUnavailableError
from tracker.shared.logging import get_logger

#: Seconds one ``gh`` or ``git`` command may take.
COMMAND_TIMEOUT_SECONDS: Final[float] = 60.0

_GH: Final[str] = "gh"
_GIT: Final[str] = "git"

#: What ``gh repo view`` is asked for, and the answers that make a private copy.
_REPOSITORY_FIELDS: Final[str] = "nameWithOwner,visibility,viewerPermission"
_PRIVATE: Final[str] = "PRIVATE"
_ADMIN: Final[str] = "ADMIN"

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


@dataclass(frozen=True, slots=True)
class GitHubRepository:
    """A repository as the signed-in account sees it.

    Attributes:
        name: ``owner/name``.
        private: Whether only invited people can see it.
        admin: Whether the signed-in account administers it.
    """

    name: str
    private: bool
    admin: bool

    @property
    def is_own_private_copy(self) -> bool:
        """Whether secrets may go here: private, and administered by the owner.

        The public template, or anybody else's repository, is neither.
        """
        return self.private and self.admin


def _parse_repository(output: str) -> GitHubRepository | None:
    """Read ``gh repo view --json``'s answer; anything unexpected is ``None``."""
    try:
        answer = json.loads(output)
    except json.JSONDecodeError:
        return None
    if not isinstance(answer, dict):
        return None
    facts = cast("dict[str, object]", answer)
    name = facts.get("nameWithOwner")
    if not isinstance(name, str) or name.count("/") != 1:
        return None
    return GitHubRepository(
        name=name,
        private=facts.get("visibility") == _PRIVATE,
        admin=facts.get("viewerPermission") == _ADMIN,
    )


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

    def repository(self) -> GitHubRepository | None:
        """Describe the GitHub repository this folder belongs to.

        Returns:
            Its name, whether it is private and whether the signed-in account
            administers it; ``None`` when ``gh`` could not say.
        """
        status, output = self._run([_GH, "repo", "view", "--json", _REPOSITORY_FIELDS], None)
        if status != 0:
            return None
        return _parse_repository(output)

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

    def secret_names(self, repository: str) -> frozenset[str]:
        """List the names of the repository's Actions secrets; values never leave GitHub.

        Raises:
            SourceUnavailableError: If ``gh`` could not list them.
        """
        return self._names(["secret", "list", "--repo", repository], "secrets")

    def variable_names(self, repository: str) -> frozenset[str]:
        """List the names of the repository's Actions variables.

        Raises:
            SourceUnavailableError: If ``gh`` could not list them.
        """
        return self._names(["variable", "list", "--repo", repository], "variables")

    def delete_secret(self, repository: str, name: str) -> None:
        """Delete one Actions secret.

        Raises:
            SourceUnavailableError: If ``gh`` did not delete it.
        """
        self._delete(["secret", "delete", name, "--repo", repository], name)

    def delete_variable(self, repository: str, name: str) -> None:
        """Delete one Actions variable.

        Raises:
            SourceUnavailableError: If ``gh`` did not delete it.
        """
        self._delete(["variable", "delete", name, "--repo", repository], name)

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

    def _names(self, arguments: list[str], kind: str) -> frozenset[str]:
        """Run one ``gh … list`` command and read the names it printed."""
        status, output = self._run([_GH, *arguments, "--json", "name", "--jq", ".[].name"], None)
        if status != 0:
            _log.warning("github_settings_not_listed", kind=kind, status=status)
            message = f"the GitHub CLI could not list the repository's {kind}"
            raise SourceUnavailableError(message)
        return frozenset(line.strip() for line in output.splitlines() if line.strip())

    def _delete(self, arguments: list[str], name: str) -> None:
        """Run one ``gh … delete`` command."""
        status, _ = self._run([_GH, *arguments], None)
        if status != 0:
            _log.warning("github_setting_not_deleted", setting=name, status=status)
            message = f"the GitHub CLI could not delete {name}"
            raise SourceUnavailableError(message)

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
