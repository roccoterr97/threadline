"""Exchanged files are removed once used, and a clean-up leaves nothing behind."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from tracker.cli.commands import ai
from tracker.cli.main import build_cli
from tracker.services.assessment import work_files
from tracker.services.assessment.work_files import clean_work_directory, remove_work_file
from tracker.shared.errors import WorkFileError


def _fill(work: Path) -> None:
    """Lay out a work directory the way a day's run leaves it."""
    (work / "batches").mkdir(parents=True)
    (work / "results").mkdir()
    (work / "batches" / "batch-0001.json").write_text("{}", encoding="utf-8")
    (work / "results" / "batch-0001.json").write_text("{}", encoding="utf-8")
    (work / "summary.json").write_text("{}", encoding="utf-8")


def test_clean_removes_every_file_and_keeps_the_directory(tmp_path: Path) -> None:
    work = tmp_path / "work"
    _fill(work)

    result = clean_work_directory(work)

    assert result.removed_files == 3
    assert work.is_dir()
    assert list(work.iterdir()) == []


def test_clean_of_a_missing_directory_removes_nothing(tmp_path: Path) -> None:
    assert clean_work_directory(tmp_path / "absent").removed_files == 0


def test_clean_removes_a_link_without_touching_its_target(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    kept = outside / "keep.json"
    kept.write_text("{}", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    (work / "link").symlink_to(outside, target_is_directory=True)

    clean_work_directory(work)

    assert kept.is_file()
    assert list(work.iterdir()) == []


def test_clean_reports_what_it_could_not_remove_and_removes_the_rest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work = tmp_path / "work"
    _fill(work)
    stuck = work / "summary.json"
    real_unlink = Path.unlink

    def refuse_one(path: Path, missing_ok: bool = False) -> None:
        if path == stuck:
            raise PermissionError(path)
        real_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(work_files.Path, "unlink", refuse_one)

    with pytest.raises(WorkFileError):
        clean_work_directory(work)

    assert [path.name for path in work.iterdir()] == ["summary.json"]


def test_removing_a_file_that_is_already_gone_is_fine(tmp_path: Path) -> None:
    remove_work_file(tmp_path / "gone.json")


def test_a_file_that_cannot_be_removed_raises_a_typed_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "batch-0001.json"
    target.write_text("{}", encoding="utf-8")

    def refuse(path: Path, **_options: bool) -> None:
        raise PermissionError(path.name)

    monkeypatch.setattr(work_files.Path, "unlink", refuse)

    with pytest.raises(WorkFileError):
        remove_work_file(target)


def test_the_clean_command_empties_the_work_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work = tmp_path / "work"
    _fill(work)
    monkeypatch.setattr(ai, "clean_work_directory", lambda: clean_work_directory(work))

    result = CliRunner().invoke(build_cli(), ["ai", "clean"])

    assert result.exit_code == 0
    assert "3 files removed" in result.output
    assert list(work.iterdir()) == []
