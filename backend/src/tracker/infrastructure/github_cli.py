"""The GitHub CLI, git and the workflow file, as the set-up uses them.

A value is only ever handed to ``gh`` on its standard input — never as a
command-line argument, which other programs on the machine can read, and never
in a log line. What ``gh`` and ``git`` print is not logged either: only the
exit status is. Both speak UTF-8 on every system, Windows included, so their
text is read and written as UTF-8 rather than in the system's own encoding.
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

from tracker.shared.constants.github import (
    ACTIONS_PERMISSIONS_API_PATH,
    ALLOWED_ACTIONS_ALL,
    COPY_REMOTE,
    WORKFLOW_FILE_NAME,
    WORKFLOW_MODE_INPUT,
    WORKFLOW_PAGE,
    WorkflowMode,
)
from tracker.shared.errors import (
    SourceUnavailableError,
    WorkflowNotEnabledError,
    WorkflowNotStartedError,
)
from tracker.shared.logging import get_logger

#: Seconds one ``gh`` or ``git`` command may take.
COMMAND_TIMEOUT_SECONDS: Final[float] = 60.0

_GH: Final[str] = "gh"
_GIT: Final[str] = "git"

#: How ``gh`` and ``git`` text is read and written, on every system; a byte
#: that is not UTF-8 is shown as a placeholder rather than stopping the set-up.
_COMMAND_ENCODING: Final[str] = "utf-8"
_UNREADABLE_BYTES: Final[str] = "replace"

#: Line ending of a file the set-up writes, so git sees only the lines it changed.
_NEWLINE: Final[str] = "\n"

#: What ``gh repo view`` is asked for, and the answers that make a private copy.
_REPOSITORY_FIELDS: Final[str] = "nameWithOwner,visibility,viewerPermission"
_PRIVATE: Final[str] = "PRIVATE"
_ADMIN: Final[str] = "ADMIN"

#: The field of GitHub's Actions permissions that says whether Actions may run.
_ACTIONS_ENABLED_FIELD: Final[str] = "enabled"
#: What ``gh api --jq .enabled`` prints when they may.
_TRUE: Final[str] = "true"

_log = get_logger(__name__)

#: Runs a command: (arguments, text for its standard input) -> (exit status, output).
Runner = Callable[[Sequence[str], str | None], tuple[int, str]]


def run_command(cwd: Path, which: Callable[[str], str | None] = shutil.which) -> Runner:
    """Build a runner that starts commands in one folder, with no shell.

    The program is looked up first, so ``gh`` also finds ``gh.exe`` on Windows.

    Args:
        cwd: The folder commands run in: the repository.
        which: Finds a program on the machine; replaced in tests.

    Returns:
        The runner.
    """

    def run(arguments: Sequence[str], stdin: str | None) -> tuple[int, str]:
        program = which(arguments[0]) or arguments[0]
        try:
            done = subprocess.run(
                [program, *arguments[1:]],
                cwd=cwd,
                input=stdin,
                capture_output=True,
                text=True,
                encoding=_COMMAND_ENCODING,
                errors=_UNREADABLE_BYTES,
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

    def enable_workflow(self, repository: str) -> None:
        """Switch Actions on in the repository if they are off, then enable the workflow.

        A copy made from the template, or by ``create_private_copy``, is not a
        fork, so GitHub leaves its workflows on; this puts right the rare copy
        where Actions were switched off, and is harmless otherwise.

        Args:
            repository: The copy, as ``owner/name``.

        Raises:
            WorkflowNotEnabledError: If GitHub refused either change.
        """
        if not self._actions_enabled(repository):
            self._enable_actions(repository)
        status, _ = self._run(
            [_GH, "workflow", "enable", WORKFLOW_FILE_NAME, "--repo", repository], None
        )
        if status != 0:
            _log.warning("github_workflow_not_enabled", status=status)
            message = (
                f"GitHub would not switch on the workflow in {repository} - open "
                f"{WORKFLOW_PAGE.format(repository=repository)}, click 'Enable workflow' "
                "if it shows, then 'Run workflow'"
            )
            raise WorkflowNotEnabledError(message)

    def start_workflow(self, repository: str, mode: WorkflowMode) -> None:
        """Start one run of the Threadline workflow on the repository's default branch.

        Args:
            repository: The copy, as ``owner/name``.
            mode: ``daily`` for the whole run with the e-mail, ``refresh`` for new mail only.

        Raises:
            WorkflowNotStartedError: If GitHub did not start it.
        """
        status, _ = self._run(
            [
                _GH, "workflow", "run", WORKFLOW_FILE_NAME, "--repo", repository,
                "--raw-field", f"{WORKFLOW_MODE_INPUT}={mode}",
            ],
            None,
        )  # fmt: skip
        if status != 0:
            _log.warning("github_workflow_not_started", mode=mode.value, status=status)
            message = (
                f"GitHub did not start the run - open "
                f"{WORKFLOW_PAGE.format(repository=repository)} and click 'Run workflow' "
                f"yourself, keeping mode {WorkflowMode.DAILY}"
            )
            raise WorkflowNotStartedError(message)
        _log.info("github_workflow_started", mode=mode.value)

    def _actions_enabled(self, repository: str) -> bool:
        """Read whether Actions may run in the repository; a failed read counts as no."""
        path = ACTIONS_PERMISSIONS_API_PATH.format(repository=repository)
        status, output = self._run([_GH, "api", path, "--jq", f".{_ACTIONS_ENABLED_FIELD}"], None)
        return status == 0 and output.strip() == _TRUE

    def _enable_actions(self, repository: str) -> None:
        """Switch Actions on for the repository, allowing every action, as the guide does."""
        path = ACTIONS_PERMISSIONS_API_PATH.format(repository=repository)
        status, _ = self._run(
            [
                _GH, "api", "--method", "PUT", path,
                "--field", f"{_ACTIONS_ENABLED_FIELD}={_TRUE}",
                "--raw-field", f"allowed_actions={ALLOWED_ACTIONS_ALL}",
            ],
            None,
        )  # fmt: skip
        if status != 0:
            _log.warning("github_actions_not_enabled", status=status)
            message = (
                f"GitHub would not switch on Actions for {repository} - on github.com open "
                "your copy's Settings > Actions > General, choose 'Allow all actions and "
                f"reusable workflows', then start the run at "
                f"{WORKFLOW_PAGE.format(repository=repository)}"
            )
            raise WorkflowNotEnabledError(message)

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
        """Replace the file's content, keeping its lines ending as git stores them."""
        self._path.write_text(text, encoding="utf-8", newline=_NEWLINE)
