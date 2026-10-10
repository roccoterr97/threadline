"""The one-line installer for macOS and Linux, checked without running it.

``install.sh`` installs software and signs in to accounts, so it is never run
here. Its syntax is checked with ``sh -n``, and the one piece of pure logic in
it, the comparison of GitHub tool versions, is run on its own.
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


def install_claude_code_with(
    tmp_path: Path, *, found: bool, downloads: bool = True, installs: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run the installer's Claude Code step with the network and the install faked."""
    folder = tmp_path / "local-bin"
    script = "\n".join(
        [
            f'CLAUDE_INSTALLER="https://claude.ai/install.sh"; CLAUDE_FOLDER="{folder}"',
            f'WORK_DIR="{tmp_path}"; PATH="/usr/bin:/bin"',
            installer_function("say"),
            installer_function("note"),
            installer_function("install_claude_code"),
            installer_function("use_claude_folder"),
            f'has() {{ [ "$1" = bash ] || {{ [ "$1" = claude ] && {str(found).lower()}; }}; }}',
            f'download() {{ echo "download $1"; {str(downloads).lower()}; }}',
            f"bash() {{ echo 'ran the installer'; {str(installs).lower()}; }}",
            'install_claude_code; echo "exit $?"; echo "path $PATH"',
        ]
    )
    return run_shell(script)


@needs_posix_shell
def test_claude_code_already_there_is_not_installed_again(tmp_path: Path) -> None:
    result = install_claude_code_with(tmp_path, found=True)

    assert "Claude Code is installed." in result.stdout
    assert "download" not in result.stdout


@needs_posix_shell
def test_claude_code_is_installed_with_anthropics_installer_and_found_this_session(
    tmp_path: Path,
) -> None:
    result = install_claude_code_with(tmp_path, found=False)

    assert "download https://claude.ai/install.sh" in result.stdout
    assert "ran the installer" in result.stdout
    assert f"path {tmp_path / 'local-bin'}:" in result.stdout


@pytest.mark.parametrize(
    ("downloads", "installs", "said"),
    [(False, True, "could not be downloaded"), (True, False, "did not install")],
)
@needs_posix_shell
def test_a_failed_claude_code_install_is_said_and_the_installer_carries_on(
    tmp_path: Path, downloads: bool, installs: bool, said: str
) -> None:
    result = install_claude_code_with(tmp_path, found=False, downloads=downloads, installs=installs)

    assert said in result.stdout
    assert "paste the key" in result.stdout
    assert "exit 0" in result.stdout


def test_both_installers_use_anthropics_official_claude_code_installers() -> None:
    assert 'CLAUDE_INSTALLER="https://claude.ai/install.sh"' in INSTALLER.read_text()
    assert "$ClaudeInstaller = 'https://claude.ai/install.ps1'" in WINDOWS_INSTALLER.read_text()


def test_claude_code_is_installed_after_git_and_before_the_github_sign_in() -> None:
    shell_order = re.findall(r"^  (\w+)$", INSTALLER.read_text(), re.M)
    windows_order = re.findall(r"^    ([A-Z]\w+-\w+)$", WINDOWS_INSTALLER.read_text(), re.M)

    assert shell_order.index("check_git") < shell_order.index("install_claude_code")
    assert shell_order.index("install_claude_code") < shell_order.index("sign_in_to_github")
    assert windows_order.index("Install-Git") < windows_order.index("Install-ClaudeCode")
    assert windows_order.index("Install-ClaudeCode") < windows_order.index("Connect-GitHub")
