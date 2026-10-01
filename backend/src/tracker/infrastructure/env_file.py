"""The ``.env`` file, read and changed one line at a time.

Only the set-up writes to it. Lines it does not touch — comments, blank lines,
other settings — stay exactly as they were. A file it creates is readable by
you alone.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from tracker.shared.constants.setup import ENV_FILE_MODE
from tracker.shared.errors import ValidationFailedError

_SEPARATOR: Final[str] = "="
_COMMENT: Final[str] = "#"
_QUOTES: Final[str] = "\"'"


class EnvFile:
    """Reads and writes ``NAME=value`` lines."""

    def __init__(self, path: Path) -> None:
        """Bind the helper to a file, which may not exist yet.

        Args:
            path: Where the ``.env`` file is.
        """
        self._path = path

    def get(self, name: str) -> str | None:
        """Return a value, or ``None`` when it is absent or empty."""
        return self._values().get(name) or None

    def names(self) -> tuple[str, ...]:
        """Return the names that hold a value, in file order."""
        return tuple(name for name, value in self._values().items() if value)

    def set(self, name: str, value: str) -> None:
        """Write a value, replacing the line that holds it or adding one.

        Args:
            name: The setting's name.
            value: Its value, on one line.

        Raises:
            ValidationFailedError: If the value spans several lines.
        """
        if "\n" in value or "\r" in value:
            message = f"{name} must fit on one line"
            raise ValidationFailedError(message)
        lines = self._lines()
        entry = f"{name}{_SEPARATOR}{value}"
        for index, line in enumerate(lines):
            if _name_of(line) == name:
                lines[index] = entry
                break
        else:
            lines.append(entry)
        self._write(lines)

    def _values(self) -> dict[str, str]:
        """Parse every ``NAME=value`` line."""
        found: dict[str, str] = {}
        for line in self._lines():
            name = _name_of(line)
            if name:
                found[name] = line.split(_SEPARATOR, 1)[1].strip().strip(_QUOTES)
        return found

    def _lines(self) -> list[str]:
        """Read the file's lines; none when it does not exist."""
        if not self._path.exists():
            return []
        return self._path.read_text(encoding="utf-8").splitlines()

    def _write(self, lines: list[str]) -> None:
        """Write the lines back, creating the file readable by you alone."""
        if not self._path.exists():
            self._path.touch(mode=ENV_FILE_MODE)
            self._path.chmod(ENV_FILE_MODE)
        self._path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _name_of(line: str) -> str | None:
    """Return the setting a line holds, or ``None`` for comments and blanks."""
    stripped = line.strip()
    if not stripped or stripped.startswith(_COMMENT) or _SEPARATOR not in stripped:
        return None
    return stripped.split(_SEPARATOR, 1)[0].strip().removeprefix("export ").strip()
