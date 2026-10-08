"""The ``.env`` file, read and changed one line at a time.

Only the set-up writes to it. Lines it does not touch — comments, blank lines,
other settings — stay exactly as they were. Every write leaves the file
readable by you alone, even one that was readable by others before.

Values are read the way python-dotenv reads them for the settings: when a name
appears twice, the last line wins, and quotes are removed only when the same
quote character wraps both ends. A value python-dotenv would otherwise cut
short or change — one holding `` #``, edge spaces, or wrapped in quotes — is
written inside single quotes, which python-dotenv reads literally.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from tracker.shared.constants.setup import ENV_FILE_MODE
from tracker.shared.errors import ValidationFailedError

_SEPARATOR: Final[str] = "="
_COMMENT: Final[str] = "#"
_QUOTES: Final[str] = "\"'"
_LITERAL_QUOTE: Final[str] = "'"
#: What python-dotenv takes as the start of a comment after an unquoted value.
_INLINE_COMMENTS: Final[tuple[str, ...]] = (" #", "\t#")
#: The shortest quoted value: the two quotes and nothing between them.
_QUOTED_LENGTH: Final[int] = 2


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
        """Write a value, replacing every line that holds it or adding one.

        Every line with this name gets the value, so whichever one a reader
        takes, it finds the new value.

        Args:
            name: The setting's name.
            value: Its value, on one line.

        Raises:
            ValidationFailedError: If the value spans several lines, or would
                need quoting but holds a single quote.
        """
        if "\n" in value or "\r" in value:
            message = f"{name} must fit on one line"
            raise ValidationFailedError(message)
        entry = f"{name}{_SEPARATOR}{_written(name, value)}"
        lines = self._lines()
        holds_it = [_name_of(line) == name for line in lines]
        updated = [entry if holds else line for line, holds in zip(lines, holds_it, strict=True)]
        if not any(holds_it):
            updated.append(entry)
        self._write(updated)

    def _values(self) -> dict[str, str]:
        """Parse every ``NAME=value`` line."""
        found: dict[str, str] = {}
        for line in self._lines():
            name = _name_of(line)
            if name:
                found[name] = _unquoted(line.split(_SEPARATOR, 1)[1].strip())
        return found

    def _lines(self) -> list[str]:
        """Read the file's lines; none when it does not exist."""
        if not self._path.exists():
            return []
        return self._path.read_text(encoding="utf-8").splitlines()

    def _write(self, lines: list[str]) -> None:
        """Write the lines back, making the file readable by you alone first."""
        self._path.touch(mode=ENV_FILE_MODE)
        self._path.chmod(ENV_FILE_MODE)
        self._path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _name_of(line: str) -> str | None:
    """Return the setting a line holds, or ``None`` for comments and blanks."""
    stripped = line.strip()
    if not stripped or stripped.startswith(_COMMENT) or _SEPARATOR not in stripped:
        return None
    return stripped.split(_SEPARATOR, 1)[0].strip().removeprefix("export ").strip()


def _written(name: str, value: str) -> str:
    """Return a value as it must be written for python-dotenv to read it back unchanged."""
    if not _needs_quotes(value):
        return value
    if _LITERAL_QUOTE in value:
        message = f"{name} cannot hold both a single quote and a space before #"
        raise ValidationFailedError(message)
    return f"{_LITERAL_QUOTE}{value}{_LITERAL_QUOTE}"


def _needs_quotes(value: str) -> bool:
    """Whether python-dotenv would cut, trim or unquote the value as written."""
    return (
        any(marker in value for marker in _INLINE_COMMENTS)
        or value != value.strip()
        or _unquoted(value) != value
    )


def _unquoted(value: str) -> str:
    """Remove the quotes around a value only when one quote character wraps both ends."""
    if len(value) >= _QUOTED_LENGTH and value[0] == value[-1] and value[0] in _QUOTES:
        return value[1:-1]
    return value
