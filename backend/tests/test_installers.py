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
