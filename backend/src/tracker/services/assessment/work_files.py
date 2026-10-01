"""Remove the files Python and the assistant exchange once they are done with.

Batch files carry message text, and verdict files carry what was concluded from
it. Neither has any use after the verdicts are in the database, so nothing under
the work directory is kept longer than it is needed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from tracker.shared.constants.assessment import WORK_DIRECTORY
from tracker.shared.errors import WorkFileError
from tracker.shared.logging import get_logger

_log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CleanResult:
    """What one clean-up removed."""

    removed_files: int


def remove_work_file(path: Path) -> None:
    """Remove one exchanged file, if it is there.

    Args:
        path: The file to remove.

    Raises:
        WorkFileError: If the file exists and could not be removed.
    """
    try:
        path.unlink(missing_ok=True)
    except OSError as error:
        _log.error("work_file_not_removed", file=path.name, error_type=type(error).__name__)
        message = f"file could not be removed: {path.name}"
        raise WorkFileError(message) from error


def clean_work_directory(directory: Path = WORK_DIRECTORY) -> CleanResult:
    """Remove everything under the work directory, keeping the directory itself.

    One file that cannot be removed never stops the others from going.

    Args:
        directory: The work directory.

    Returns:
        How many files were removed.

    Raises:
        WorkFileError: If anything was left behind.
    """
    if not directory.is_dir():
        return CleanResult(removed_files=0)
    removed = 0
    left_behind = 0
    for entry in sorted(directory.iterdir()):
        entry_removed, entry_left = _remove_entry(entry)
        removed += entry_removed
        left_behind += entry_left
    _log.info("work_directory_cleaned", removed=removed, left_behind=left_behind)
    if left_behind:
        message = f"{left_behind} item(s) under the work directory could not be removed"
        raise WorkFileError(message)
    return CleanResult(removed_files=removed)


def _remove_entry(entry: Path) -> tuple[int, int]:
    """Remove one file, link or directory tree.

    A symbolic link is removed itself and never followed, so nothing outside
    the work directory can be reached through one.

    Args:
        entry: The path to remove.

    Returns:
        The number of files removed and the number of items left behind.
    """
    if entry.is_symlink() or not entry.is_dir():
        return _attempt(entry.unlink, entry, files=1)
    removed = 0
    left_behind = 0
    for child in sorted(entry.iterdir()):
        child_removed, child_left = _remove_entry(child)
        removed += child_removed
        left_behind += child_left
    if left_behind:
        return removed, left_behind
    directory_removed, directory_left = _attempt(entry.rmdir, entry, files=0)
    return removed + directory_removed, directory_left


def _attempt(remove: Callable[[], None], entry: Path, *, files: int) -> tuple[int, int]:
    """Run one removal, turning a refusal into a counted leftover.

    Args:
        remove: The removal to run.
        entry: The path being removed, for the log.
        files: How many files the removal accounts for when it works.

    Returns:
        The number of files removed and the number of items left behind.
    """
    try:
        remove()
    except OSError as error:
        _log.error("work_file_not_removed", file=entry.name, error_type=type(error).__name__)
        return 0, 1
    return files, 0
