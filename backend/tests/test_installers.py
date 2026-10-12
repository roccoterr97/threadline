"""The one-line installers, checked without running them.

``install.sh`` and ``install.ps1`` install software and sign in to accounts, so
neither is run here. The syntax of ``install.sh`` is checked with ``sh -n``, and
single functions of it are run on their own, with the commands they call
faked. ``install.ps1`` is checked by reading it.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tracker.shared.constants.github import GITHUB_CLI_MINIMUM_VERSION

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
INSTALLER = REPOSITORY_ROOT / "install.sh"
WINDOWS_INSTALLER = REPOSITORY_ROOT / "install.ps1"

needs_posix_shell = pytest.mark.skipif(
    os.name == "nt" or shutil.which("sh") is None, reason="the installer is for macOS and Linux"
)


def run_shell(script: str) -> subprocess.CompletedProcess[str]:
    """Run a few lines of ``sh`` and return what happened."""
    return subprocess.run(  # noqa: S603 - a fixed shell and a test's own script
        [shutil.which("sh") or "sh", "-c", script],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )


def installer_function(name: str) -> str:
    """Return one function of ``install.sh``, as written there."""
    match = re.search(rf"^{name}\(\) \{{\n.*?^\}}\n", INSTALLER.read_text(), re.S | re.M)
    assert match is not None, f"{name} is not in install.sh"
    return match.group(0)


@needs_posix_shell
def test_the_installer_has_no_syntax_errors() -> None:
    assert run_shell(f"sh -n '{INSTALLER}'").returncode == 0


@needs_posix_shell
@pytest.mark.parametrize(
    ("have", "need", "enough"),
    [
        ("2.68.0", "2.68", True),
        ("2.68", "2.68", True),
        ("2.100.0", "2.68", True),
        ("3.0", "2.68", True),
        ("2.67.9", "2.68", False),
        ("2.9.0", "2.68", False),
        ("2.4", "2.68", False),
        ("", "2.68", False),
    ],
)
def test_a_github_tool_version_is_compared_number_by_number(
    have: str, need: str, enough: bool
) -> None:
    script = f"{installer_function('version_at_least')}\nversion_at_least '{have}' '{need}'"

    assert (run_shell(script).returncode == 0) is enough


def test_every_installer_asks_for_the_same_github_tool_version_as_the_set_up() -> None:
    expected = ".".join(str(part) for part in GITHUB_CLI_MINIMUM_VERSION)
    shell = re.search(r'^GITHUB_CLI_MINIMUM="([\d.]+)"$', INSTALLER.read_text(), re.M)
    windows = re.search(
        r"^\$GitHubCliMinimum = \[version\] '([\d.]+)'$", WINDOWS_INSTALLER.read_text(), re.M
    )

    assert shell is not None
    assert windows is not None
    assert shell.group(1) == expected
    assert windows.group(1) == expected


def check_existing_copy_with(facts: str) -> subprocess.CompletedProcess[str]:
    """Run the installer's existing-copy check against GitHub answering ``facts``."""
    script = "\n".join(
        [
            'TEMPLATE_REPOSITORY="roccoterr97/threadline"',
            'COPY_NAME="threadline"',
            installer_function("stop"),
            installer_function("lowercase"),
            installer_function("check_existing_copy"),
            f"copy_facts() {{ echo '{facts}'; }}",
            "copy_has_content() { return 0; }",
            "check_existing_copy",
        ]
    )
    return run_shell(script)


@needs_posix_shell
def test_the_template_owner_is_told_to_use_another_account_not_to_hide_the_template() -> None:
    result = check_existing_copy_with("RoccoTerr97/Threadline false ADMIN /")

    assert result.returncode == 1
    assert "the account that publishes Threadline" in result.stderr
    assert "gh auth logout" in result.stderr
    assert "Make it private" not in result.stderr


@needs_posix_shell
def test_a_public_repository_of_the_same_name_is_still_refused_as_public() -> None:
    result = check_existing_copy_with("someone/threadline false ADMIN roccoterr97/threadline")

    assert result.returncode == 1
    assert "someone/threadline on GitHub is public" in result.stderr


@needs_posix_shell
def test_a_private_copy_made_from_the_template_is_used() -> None:
    result = check_existing_copy_with("someone/threadline true ADMIN roccoterr97/threadline")

    assert result.returncode == 0
    assert result.stderr == ""


def find_copy_when_github_answers(answer: str) -> subprocess.CompletedProcess[str]:
    """Run the installer's copy look-up with ``gh repo view`` answering ``answer``."""
    script = "\n".join(
        [
            'TEMPLATE_REPOSITORY="roccoterr97/threadline"',
            'COPY_NAME="threadline"',
            installer_function("stop"),
            installer_function("lowercase"),
            installer_function("copy_facts"),
            installer_function("existing_copy"),
            installer_function("check_existing_copy"),
            f"gh() {{ echo '{answer}'; }}",
            "copy_has_content() { return 0; }",
            'existing_copy; echo "found $?"',
            'check_existing_copy; echo "usable $?"',
        ]
    )
    return run_shell(script)


@needs_posix_shell
def test_a_repository_renamed_from_threadline_is_not_taken_for_the_copy() -> None:
    result = find_copy_when_github_answers(
        "someone/threadline-test-0-9 true ADMIN roccoterr97/threadline"
    )

    assert result.stdout.splitlines() == ["found 1", "usable 1"]
    assert result.stderr == ""


@needs_posix_shell
def test_the_copy_under_its_own_name_is_found_in_any_letter_case() -> None:
    result = find_copy_when_github_answers("someone/Threadline true ADMIN roccoterr97/threadline")

    assert result.stdout.splitlines() == ["someone/Threadline", "found 0", "usable 0"]


def test_the_windows_installer_also_checks_the_name_github_answers_with() -> None:
    windows = WINDOWS_INSTALLER.read_text()

    assert "--json name,owner," in windows
    assert "if ($Facts.name -ne $CopyName)" in windows


def installer_functions(*names: str) -> str:
    """Return several functions of ``install.sh``, as written there."""
    return "\n".join(installer_function(name) for name in names)


BACKGROUND_HELPERS = ("say", "note", "stop", "wait_for_job", "show_log", "keep_log")


def background_settings(tmp_path: Path) -> str:
    """Return the installer settings that its background jobs use, inside ``tmp_path``."""
    copy = tmp_path / "threadline"
    copy.mkdir(exist_ok=True)
    return "\n".join(
        [
            f'WORK_DIR="{tmp_path}"; COPY_FOLDER="{copy}"',
            'LOG_LINES_SHOWN=5; INSTALL_LOG="install.log"; PYTHON_VERSION="3.12"',
            'PYTHON_JOB=""; CLAUDE_JOB=""',
        ]
    )


def install_claude_code_with(
    tmp_path: Path, *, found: bool, downloads: bool = True, installs: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run the installer's Claude Code steps with the network and the install faked.

    The faked installer only finishes once the script has gone on past
    ``start_claude_code``, so an installer that is not run in the background
    makes the script time out.
    """
    folder = tmp_path / "local-bin"
    if found:
        folder.mkdir()
        (folder / "claude").write_text("#!/bin/sh\n")
        (folder / "claude").chmod(0o755)
    script = "\n".join(
        [
            f'CLAUDE_INSTALLER="https://claude.ai/install.sh"; CLAUDE_FOLDER="{folder}"',
            background_settings(tmp_path),
            'PATH="/usr/bin:/bin"',
            installer_functions(
                *BACKGROUND_HELPERS, "start_claude_code", "finish_claude_code", "use_claude_folder"
            ),
            'has() { case "$1" in bash) true ;; claude) [ -x "$CLAUDE_FOLDER/claude" ] ;; '
            "*) false ;; esac; }",
            f'download() {{ echo "download $1"; {str(downloads).lower()}; }}',
            "bash() {",
            '  until [ -f "$WORK_DIR/go" ]; do sleep 0.1; done',
            "  echo 'ran the installer'",
            f"  {str(installs).lower()} || {{ echo 'no space left'; return 1; }}",
            '  mkdir -p "$CLAUDE_FOLDER"; printf "#!/bin/sh\\n" >"$CLAUDE_FOLDER/claude"',
            '  chmod +x "$CLAUDE_FOLDER/claude"',
            "}",
            'start_claude_code; echo "job ${CLAUDE_JOB:-none}" | sed "s/[0-9][0-9]*/started/"',
            'touch "$WORK_DIR/go"',
            'finish_claude_code; echo "exit $?"; echo "path $PATH"',
        ]
    )
    return run_shell(script)


@needs_posix_shell
def test_claude_code_already_there_is_not_installed_again(tmp_path: Path) -> None:
    result = install_claude_code_with(tmp_path, found=True)

    assert "download" not in result.stdout
    assert "job none" in result.stdout
    assert f"path {tmp_path / 'local-bin'}:" in result.stdout


@needs_posix_shell
def test_claude_code_is_installed_in_the_background_and_found_this_session(
    tmp_path: Path,
) -> None:
    result = install_claude_code_with(tmp_path, found=False)

    assert "download https://claude.ai/install.sh" in result.stdout
    assert "Installing Claude Code in the background." in result.stdout
    assert "job started" in result.stdout
    assert "ran the installer" not in result.stdout
    assert "paste the key" not in result.stdout
    assert "exit 0" in result.stdout
    assert f"path {tmp_path / 'local-bin'}:" in result.stdout


@needs_posix_shell
def test_a_claude_code_download_that_fails_is_said_and_the_installer_carries_on(
    tmp_path: Path,
) -> None:
    result = install_claude_code_with(tmp_path, found=False, downloads=False)

    assert "could not be downloaded; the set-up will ask you to paste the key" in result.stdout
    assert "job none" in result.stdout
    assert "exit 0" in result.stdout


@needs_posix_shell
def test_a_failed_claude_code_install_is_said_with_its_last_lines_and_kept(
    tmp_path: Path,
) -> None:
    result = install_claude_code_with(tmp_path, found=False, installs=False)
    install_log = tmp_path / "threadline" / "install.log"

    assert "Claude Code did not install; the set-up will ask you to paste the key." in result.stdout
    assert "    ran the installer\n    no space left\n" in result.stdout
    assert f"The full report is in {install_log}." in result.stdout
    assert "no space left" in install_log.read_text()
    assert "exit 0" in result.stdout


def run_python_download(tmp_path: Path, *, downloads: bool) -> subprocess.CompletedProcess[str]:
    """Run the installer's background Python download and its wait, with uv faked."""
    script = "\n".join(
        [
            background_settings(tmp_path),
            installer_functions(*BACKGROUND_HELPERS, "start_python_download", "wait_for_python"),
            f'uv() {{ echo "uv $*"; echo "no network"; {str(downloads).lower()}; }}',
            'start_python_download; echo "job ${PYTHON_JOB:+started}"',
            'wait_for_python; echo "exit $?"',
        ]
    )
    return run_shell(script)


@needs_posix_shell
def test_python_is_downloaded_in_the_background_and_said_nothing_about(tmp_path: Path) -> None:
    result = run_python_download(tmp_path, downloads=True)

    assert result.stdout.splitlines() == ["job started", "exit 0"]
    assert "uv python install 3.12" in (tmp_path / "python.log").read_text()


@needs_posix_shell
def test_a_failed_python_download_is_one_line_and_not_fatal(tmp_path: Path) -> None:
    result = run_python_download(tmp_path, downloads=False)
    install_log = tmp_path / "threadline" / "install.log"

    assert result.stdout.splitlines() == [
        "job started",
        f"    Python did not download in advance (see {install_log}); trying again now.",
        "exit 0",
    ]
    assert "no network" in install_log.read_text()


@needs_posix_shell
def test_failing_threadline_parts_show_their_last_lines_and_stop(tmp_path: Path) -> None:
    backend = tmp_path / "threadline" / "backend"
    backend.mkdir(parents=True)
    (backend / "pyproject.toml").write_text("")
    script = "\n".join(
        [
            background_settings(tmp_path),
            installer_functions(*BACKGROUND_HELPERS, "wait_for_python", "install_threadline_parts"),
            'uv() { echo "Resolved 40 packages"; echo "No solution found"; return 1; }',
            'install_threadline_parts; echo "carried on"',
        ]
    )

    result = run_shell(script)

    assert result.returncode == 1
    assert "carried on" not in result.stdout
    assert "    Resolved 40 packages\n    No solution found\n" in result.stdout
    assert "Threadline's parts could not be installed." in result.stderr
    assert "No solution found" in (tmp_path / "threadline" / "install.log").read_text()


@needs_posix_shell
def test_stopping_the_installer_ends_its_background_jobs(tmp_path: Path) -> None:
    script = "\n".join(
        [
            background_settings(tmp_path),
            installer_functions("has", "cleanup", "stop_job"),
            "sleep 30 & CLAUDE_JOB=$!; job=$CLAUDE_JOB",
            'cleanup; wait "$job"; echo "ended $?"',
        ]
    )

    result = run_shell(script)

    assert "ended 143" in result.stdout


def test_both_installers_use_anthropics_official_claude_code_installers() -> None:
    assert 'CLAUDE_INSTALLER="https://claude.ai/install.sh"' in INSTALLER.read_text()
    assert "$ClaudeInstaller = 'https://claude.ai/install.ps1'" in WINDOWS_INSTALLER.read_text()


def test_the_windows_installer_runs_claude_code_and_python_in_the_background() -> None:
    windows = WINDOWS_INSTALLER.read_text()

    assert "Start-Background 'claude-code' $PowerShell $Arguments $WorkFolder" in windows
    assert "Start-Background 'python' $Uv @('python', 'install', $PythonVersion)" in windows
    assert "Start-Background 'threadline-parts' $Uv @('sync') $Backend" in windows
    assert "RedirectStandardInput = (Join-Path $WorkFolder 'no-input.txt')" in windows
    assert "$null = $Job.Process.Handle" in windows
    assert "Say 'Installing Claude Code in the background.'" in windows


def test_both_installers_download_the_python_that_threadline_runs_on() -> None:
    expected = (REPOSITORY_ROOT / "backend" / ".python-version").read_text().strip()
    shell = re.search(r'^PYTHON_VERSION="([\d.]+)"$', INSTALLER.read_text(), re.M)
    windows = re.search(r"^\$PythonVersion = '([\d.]+)'$", WINDOWS_INSTALLER.read_text(), re.M)

    assert shell is not None
    assert windows is not None
    assert shell.group(1) == expected
    assert windows.group(1) == expected


def sign_in_with(scopes: str, *, signed_in: bool) -> subprocess.CompletedProcess[str]:
    """Run the installer's GitHub sign-in with ``gh`` faked, printing how it is called."""
    script = "\n".join(
        [
            'GITHUB_WORKFLOW_SCOPE="workflow"',
            installer_functions(
                "say", "note", "stop", "ensure_workflow_permission", "sign_in_to_github"
            ),
            f'gh() {{ if [ "$1 $2" = "auth status" ]; then {str(signed_in).lower()}; '
            'return; fi; echo "gh $*"; }',
            f"github_scopes() {{ echo '{scopes}'; }}",
            "ensure_git_identity() { :; }",
            "sign_in_to_github",
        ]
    )
    return run_shell(script)


@needs_posix_shell
def test_the_github_sign_in_puts_its_code_on_the_clipboard() -> None:
    result = sign_in_with("", signed_in=False)

    assert (
        "gh auth login --hostname github.com --web --clipboard --git-protocol https "
        "--scopes workflow"
    ) in result.stdout
    assert "The code is on your clipboard" in result.stdout
    assert "Use a different account" in result.stdout


@needs_posix_shell
def test_the_extra_workflow_permission_also_puts_its_code_on_the_clipboard() -> None:
    result = sign_in_with("scopes: repo, read:org", signed_in=True)

    assert "gh auth refresh --hostname github.com --clipboard --scopes workflow" in result.stdout
    assert "gh auth login" not in result.stdout


def test_the_windows_sign_in_also_puts_its_code_on_the_clipboard() -> None:
    windows = WINDOWS_INSTALLER.read_text()

    assert "& gh auth login --hostname github.com --web --clipboard --git-protocol https" in windows
    assert "& gh auth refresh --hostname github.com --clipboard --scopes" in windows
    assert "Use a different account" in windows


def test_claude_code_starts_before_the_github_sign_in_and_is_waited_for_after() -> None:
    shell_order = re.findall(r"^  (\w+)$", INSTALLER.read_text(), re.M)
    windows_order = re.findall(r"^    ([A-Z]\w+-\w+)$", WINDOWS_INSTALLER.read_text(), re.M)

    shell_steps = [
        "check_git",
        "install_uv",
        "start_python_download",
        "start_claude_code",
        "sign_in_to_github",
        "get_copy",
        "install_threadline_parts",
        "finish_claude_code",
        "start_setup",
    ]
    windows_steps = [
        "Install-Git",
        "Install-Uv",
        "Start-PythonDownload",
        "Start-ClaudeCode",
        "Connect-GitHub",
        "Get-Copy",
        "Install-Parts",
        "Complete-ClaudeCode",
        "Start-Setup",
    ]
    assert [shell_order.index(step) for step in shell_steps] == sorted(
        shell_order.index(step) for step in shell_steps
    )
    assert [windows_order.index(step) for step in windows_steps] == sorted(
        windows_order.index(step) for step in windows_steps
    )
