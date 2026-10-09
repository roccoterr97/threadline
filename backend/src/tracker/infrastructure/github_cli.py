"""The GitHub CLI, git and the workflow file, as the set-up uses them.

A value is only ever handed to ``gh`` on its standard input — never as a
command-line argument, which other programs on the machine can read, and never
in a log line. What ``gh`` and ``git`` print is not logged either: only the
exit status is. Both speak UTF-8 on every system, Windows included, so their
text is read and written as UTF-8 rather than in the system's own encoding.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final, NoReturn, cast

from pydantic import SecretStr

from tracker.shared.constants.github import (
    ACTIONS_PERMISSIONS_API_PATH,
    ALLOWED_ACTIONS_ALL,
    COPY_REMOTE,
    DEFAULT_BRANCH_NAMES,
    GIT_ERROR_PREFIXES,
    GIT_IDENTITY_MARKERS,
    GIT_SAID_MAX_CHARACTERS,
    GIT_SET_EMAIL_COMMAND,
    GIT_SET_NAME_COMMAND,
    GIT_WORKFLOW_SCOPE_MESSAGE,
    GIT_WORKFLOW_SCOPE_REFUSAL,
    GITHUB_CLI_MINIMUM_VERSION,
    GITHUB_CLI_PAGE,
    JOB_ANNOTATIONS_API_PATH,
    RECENT_RUNS_LIMIT,
    RUN_CONCLUSION_SUCCESS,
    RUN_EVENT_BY_HAND,
    RUN_STATUS_COMPLETED,
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
#: The name the file being verified is given in its temporary folder.
_ATTESTED_FILE_NAME: Final[str] = "attested-file"
_GIT: Final[str] = "git"

#: How ``gh`` and ``git`` text is read and written, on every system; a byte
#: that is not UTF-8 is shown as a placeholder rather than stopping the set-up.
_COMMAND_ENCODING: Final[str] = "utf-8"
_UNREADABLE_BYTES: Final[str] = "replace"

#: Line ending of a file the set-up writes, so git sees only the lines it changed.
_NEWLINE: Final[str] = "\n"

#: What ``gh repo view`` is asked for, and the answers that make a private copy.
_REPOSITORY_FIELDS: Final[str] = "nameWithOwner,visibility,viewerPermission"
#: What is read about a workflow run.
_RUN_FIELDS: Final[str] = "databaseId,status,conclusion,url,displayTitle,createdAt"
_PRIVATE: Final[str] = "PRIVATE"
_ADMIN: Final[str] = "ADMIN"

#: The field of GitHub's Actions permissions that says whether Actions may run.
_ACTIONS_ENABLED_FIELD: Final[str] = "enabled"
#: What ``gh api --jq .enabled`` prints when they may.
_TRUE: Final[str] = "true"

#: A web address's sign-in part (``https://user:token@host``), never shown.
_ADDRESS_SIGN_IN: Final[re.Pattern[str]] = re.compile(r"(?<=://)[^/@\s]+@")
#: Git's refusal of a push that changes a workflow without the ``workflow`` permission.
_WORKFLOW_SCOPE_REFUSED: Final[re.Pattern[str]] = re.compile(
    GIT_WORKFLOW_SCOPE_REFUSAL, re.IGNORECASE | re.DOTALL
)

#: git's range for what a branch has that the branch it tracks does not.
_UPSTREAM_RANGE: Final[str] = "@{upstream}..HEAD"
#: Where git keeps the name of the copy's default branch, once it knows it.
_REMOTE_HEAD_REF: Final[str] = f"refs/remotes/{COPY_REMOTE}/HEAD"

#: How ``gh --version`` states its version: ``gh version 2.68.0 (2025-03-05)``.
_GH_VERSION: Final[re.Pattern[str]] = re.compile(r"gh version (\d+)\.(\d+)")

_log = get_logger(__name__)

#: Runs a command: (arguments, text for its standard input) -> (exit status, output).
Runner = Callable[[Sequence[str], str | None], tuple[int, str]]


def run_command(
    cwd: Path,
    which: Callable[[str], str | None] = shutil.which,
    *,
    merge_errors: bool = False,
) -> Runner:
    """Build a runner that starts commands in one folder, with no shell.

    The program is looked up first, so ``gh`` also finds ``gh.exe`` on Windows.

    Args:
        cwd: The folder commands run in: the repository.
        which: Finds a program on the machine; replaced in tests.
        merge_errors: Whether what the program prints as errors is part of the
            output. git says why it failed there; ``gh``'s output is read as
            data, so its errors stay out of it.

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
        output = done.stdout + done.stderr if merge_errors else done.stdout
        return done.returncode, output

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


@dataclass(frozen=True, slots=True)
class WorkflowRun:
    """One run of the Threadline workflow, as GitHub describes it.

    Attributes:
        id: GitHub's number for the run.
        status: Where it is: ``queued``, ``in_progress``, ``completed`` and so on.
        conclusion: How it ended, once it has; empty before.
        url: The run's page, with its log.
        title: The title GitHub shows for it, such as "Threadline daily run".
        created_at: When GitHub made it, or ``None`` when GitHub did not say.
    """

    id: int
    status: str
    conclusion: str
    url: str
    title: str = ""
    created_at: datetime | None = None

    @property
    def finished(self) -> bool:
        """Whether the run has ended, well or not."""
        return self.status == RUN_STATUS_COMPLETED

    @property
    def succeeded(self) -> bool:
        """Whether the run has ended well."""
        return self.finished and self.conclusion == RUN_CONCLUSION_SUCCESS


def _parse_run(answer: object) -> WorkflowRun | None:
    """Read one run from ``gh``'s JSON; anything unexpected is ``None``."""
    if not isinstance(answer, dict):
        return None
    facts = cast("dict[str, object]", answer)
    number = facts.get("databaseId")
    if not isinstance(number, int):
        return None
    return WorkflowRun(
        id=number,
        status=str(facts.get("status") or ""),
        conclusion=str(facts.get("conclusion") or ""),
        url=str(facts.get("url") or ""),
        title=str(facts.get("displayTitle") or ""),
        created_at=_parse_moment(facts.get("createdAt")),
    )


def _parse_moment(value: object) -> datetime | None:
    """Read a moment GitHub gives with its time zone; anything else is ``None``."""
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None


def _loaded(output: str) -> object:
    """``gh``'s JSON answer, or ``None`` when it is not JSON."""
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return None


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
        self._version_checked = False

    def installed(self) -> bool:
        """Tell whether ``gh`` is on this computer, whether or not it is signed in."""
        return self._which(_GH) is not None

    def ready(self) -> bool:
        """Tell whether ``gh`` is installed, new enough and signed in.

        Raises:
            SourceUnavailableError: If ``gh`` is older than Threadline needs; said
                once, at the first use, rather than by a command failing late.
        """
        if not self.installed():
            return False
        self._require_recent_version()
        status, _ = self._run([_GH, "auth", "status"], None)
        return status == 0

    def _require_recent_version(self) -> None:
        """Stop with where to get a newer ``gh`` when this one is too old.

        A version ``gh`` does not state clearly is not held against it.
        """
        if self._version_checked:
            return
        self._version_checked = True
        status, output = self._run([_GH, "--version"], None)
        found = _GH_VERSION.search(output) if status == 0 else None
        if found is None:
            return
        version = (int(found.group(1)), int(found.group(2)))
        if version >= GITHUB_CLI_MINIMUM_VERSION:
            return
        minimum = ".".join(str(part) for part in GITHUB_CLI_MINIMUM_VERSION)
        _log.warning("github_cli_too_old", version=found.group(0))
        message = (
            f"your GitHub CLI is too old ({found.group(0)}); Threadline needs {minimum} "
            f"or newer - get the newest from {GITHUB_CLI_PAGE}"
        )
        raise SourceUnavailableError(message)

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

    def verify_attestation(
        self, archive: bytes, repository: str, signer_workflow: str, source_ref: str
    ) -> bool:
        """Check a file's signed build provenance with ``gh attestation verify``.

        The file must have been built by one workflow of one repository, run on
        one ref, on a GitHub-hosted runner; the attestation is fetched from
        GitHub and its signature checked against the public Sigstore roots.

        Args:
            archive: The file's content, written to a temporary file for ``gh``.
            repository: The repository that must have built it, as ``owner/name``.
            signer_workflow: The workflow that must have signed it, as
                ``owner/name/.github/workflows/file.yml``.
            source_ref: The git ref the build must have run on, such as ``refs/heads/main``.

        Returns:
            ``True`` only when ``gh`` confirmed it; ``False`` when it could not
            (no attestation, a different builder, a failed check, no network).
        """
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / _ATTESTED_FILE_NAME
            path.write_bytes(archive)
            status, _ = self._run(
                [
                    _GH, "attestation", "verify", str(path),
                    "--repo", repository,
                    "--signer-workflow", signer_workflow,
                    "--source-ref", source_ref,
                    "--deny-self-hosted-runners",
                ],
                None,
            )  # fmt: skip
        if status != 0:
            _log.warning("github_attestation_not_confirmed", repository=repository, status=status)
        return status == 0

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

    def recent_runs(self, repository: str) -> tuple[WorkflowRun, ...]:
        """The newest runs of the workflow started with 'Run workflow', newest first.

        Args:
            repository: The copy, as ``owner/name``.

        Returns:
            Up to ``RECENT_RUNS_LIMIT`` runs; none when there is none yet.

        Raises:
            SourceUnavailableError: If GitHub could not say.
        """
        output = self._read_runs(
            [
                _GH, "run", "list", "--workflow", WORKFLOW_FILE_NAME, "--repo", repository,
                "--event", RUN_EVENT_BY_HAND, "--limit", str(RECENT_RUNS_LIMIT),
                "--json", _RUN_FIELDS,
            ]
        )  # fmt: skip
        answer = _loaded(output)
        if not isinstance(answer, list):
            return self._unreadable()
        runs = (_parse_run(item) for item in cast("list[object]", answer))
        return tuple(run for run in runs if run is not None)

    def workflow_run(self, repository: str, run_id: int) -> WorkflowRun:
        """Read where one run is.

        Args:
            repository: The copy, as ``owner/name``.
            run_id: GitHub's number for the run.

        Returns:
            The run.

        Raises:
            SourceUnavailableError: If GitHub could not say.
        """
        output = self._read_runs(
            [_GH, "run", "view", str(run_id), "--repo", repository, "--json", _RUN_FIELDS]
        )
        run = _parse_run(_loaded(output))
        return run if run is not None else self._unreadable()

    def run_notes(self, repository: str, run_id: int, title: str) -> tuple[str, ...]:
        """Read the notes with one title that a run's jobs left, such as an error line.

        Args:
            repository: The copy, as ``owner/name``.
            run_id: GitHub's number for the run.
            title: The notes' title.

        Returns:
            Each such note's text, in the order GitHub lists them.

        Raises:
            SourceUnavailableError: If GitHub could not say.
        """
        jobs = self._read_runs(
            [
                _GH, "run", "view", str(run_id), "--repo", repository,
                "--json", "jobs", "--jq", ".jobs[].databaseId",
            ]
        ).split()  # fmt: skip
        notes: list[str] = []
        for job in jobs:
            path = JOB_ANNOTATIONS_API_PATH.format(repository=repository, job=job)
            selected = f".[] | select(.title == {json.dumps(title)}) | .message"
            output = self._read_runs([_GH, "api", path, "--jq", selected])
            notes.extend(line.strip() for line in output.splitlines() if line.strip())
        return tuple(notes)

    def disable_workflow(self, repository: str) -> None:
        """Switch the Threadline workflow off, so it stops starting on its schedule.

        Args:
            repository: The copy, as ``owner/name``.

        Raises:
            SourceUnavailableError: If GitHub refused.
        """
        status, _ = self._run(
            [_GH, "workflow", "disable", WORKFLOW_FILE_NAME, "--repo", repository], None
        )
        if status != 0:
            _log.warning("github_workflow_not_disabled", status=status)
            message = (
                f"GitHub would not switch the daily run off - open "
                f"{WORKFLOW_PAGE.format(repository=repository)}, click the '...' menu at the "
                "top right and choose 'Disable workflow'"
            )
            raise SourceUnavailableError(message)
        _log.info("github_workflow_disabled")

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

    def _read_runs(self, arguments: list[str]) -> str:
        """Run one ``gh`` command that reads runs, and return what it printed.

        Raises:
            SourceUnavailableError: If ``gh`` failed.
        """
        status, output = self._run(arguments, None)
        if status != 0:
            _log.warning("github_runs_not_read", command=arguments[1], status=status)
            return self._unreadable()
        return output

    @staticmethod
    def _unreadable() -> NoReturn:
        """Stop with the one message for every run GitHub could not describe.

        Raises:
            SourceUnavailableError: Always.
        """
        message = "GitHub could not say how the run is going"
        raise SourceUnavailableError(message)

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

    def __init__(self, run: Runner, run_for_errors: Runner | None = None) -> None:
        """Bind the helper to command runners.

        Args:
            run: Runs one command in the repository; its output is what git
                printed as its answer only, so a harmless warning on the error
                channel never changes what a check reads.
            run_for_errors: Runs a command whose failure is explained to the
                owner, with what git printed as errors included in the output;
                ``run`` when omitted.
        """
        self._run = run
        self._run_for_errors = run_for_errors or run

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
        self.push()

    def push(self) -> None:
        """Run ``git push`` for what is already committed.

        Raises:
            SourceUnavailableError: If it did not work.
        """
        self._git(["push"])

    def has_uncommitted(self, path: str) -> bool:
        """Tell whether one file differs from the last commit, or is new.

        Args:
            path: The file, relative to the repository.

        Returns:
            ``False`` also when git could not say.
        """
        status, output = self._run([_GIT, "status", "--porcelain", "--", path], None)
        return status == 0 and bool(output.strip())

    def has_unpushed(self, path: str) -> bool:
        """Tell whether a commit that changed one file is not on GitHub yet.

        Compared with the branch's upstream, else with the copy's default
        branch on GitHub; when neither can be read there is nothing to
        compare with, and the file is not called unsent, so a copy that was
        never linked is not nagged about a push that could not happen.

        Args:
            path: The file, relative to the repository.
        """
        status, output = self._log(_UPSTREAM_RANGE, path)
        if status == 0:
            return bool(output.strip())
        default_branch = self._default_branch()
        if default_branch is None:
            return False
        status, output = self._log(f"{default_branch}..HEAD", path)
        return status == 0 and bool(output.strip())

    def _log(self, commits: str, path: str) -> tuple[int, str]:
        """List the commits in a range that changed one file."""
        return self._run([_GIT, "log", "--oneline", commits, "--", path], None)

    def _default_branch(self) -> str | None:
        """Name the copy's default branch as git knows it, such as ``origin/main``.

        Returns:
            The name git keeps, else the first usual name that exists; ``None``
            when git knows none of them.
        """
        status, output = self._run([_GIT, "symbolic-ref", "--short", _REMOTE_HEAD_REF], None)
        named = output.strip()
        if status == 0 and named:
            return named
        for branch in DEFAULT_BRANCH_NAMES:
            candidate = f"{COPY_REMOTE}/{branch}"
            status, _ = self._run([_GIT, "rev-parse", "--verify", "--quiet", candidate], None)
            if status == 0:
                return candidate
        return None

    def _git(self, arguments: list[str]) -> None:
        """Run one git command, turning a failure into a plain error saying what git said."""
        status, output = self._run_for_errors([_GIT, *arguments], None)
        if status == 0:
            return
        _log.warning("git_command_failed", command=arguments[0], status=status)
        if any(marker in output for marker in GIT_IDENTITY_MARKERS):
            message = (
                "git does not know who you are, so it cannot save the change - run these two "
                f"lines once in a terminal, with your own name and address: {GIT_SET_NAME_COMMAND}"
                f" and {GIT_SET_EMAIL_COMMAND} - then run the set-up again"
            )
            raise SourceUnavailableError(message)
        if _WORKFLOW_SCOPE_REFUSED.search(output):
            raise SourceUnavailableError(GIT_WORKFLOW_SCOPE_MESSAGE)
        said = _first_error_line(output)
        detail = f" (git said: {said})" if said else ""
        message = f"'git {arguments[0]}' did not work{detail} - run it yourself to see more"
        raise SourceUnavailableError(message)


def _first_error_line(output: str) -> str:
    """The line git gives as the reason, with any web address's sign-in removed.

    Args:
        output: Everything the failed git command printed.

    Returns:
        The first ``fatal:`` or ``error:`` line, else the first line; empty when
        git printed nothing. Cut short, since it is shown to the owner.
    """
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return ""
    chosen = next((line for line in lines if line.startswith(GIT_ERROR_PREFIXES)), lines[0])
    return _ADDRESS_SIGN_IN.sub("", chosen)[:GIT_SAID_MAX_CHARACTERS]


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
