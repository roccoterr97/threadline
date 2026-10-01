"""Structured logging setup.

One configuration for every entry point. Log events carry short, stable names
and typed fields; they never carry secrets, message bodies, or e-mail subjects.
Callers pass identifiers, counts and error codes instead.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Final, TextIO, cast

import structlog

from tracker.shared.config import AppEnv, LogLevel

_LEVELS: Final[dict[LogLevel, int]] = {
    LogLevel.DEBUG: logging.DEBUG,
    LogLevel.INFO: logging.INFO,
    LogLevel.WARNING: logging.WARNING,
    LogLevel.ERROR: logging.ERROR,
}

#: Field names that must never be written to a log, whatever the caller passes.
#: Matched as a substring of the field name and case-insensitively, so
#: ``authorization``, ``api_key`` and ``token_encryption_key`` are all covered
#: without having to list every spelling a caller might invent.
FORBIDDEN_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "anon_key",
        "authorization",
        "body",
        "credential",
        "encrypted",
        "key",
        "password",
        "secret",
        "subject",
        "token",
    }
)

#: Field names that contain a forbidden word but carry nothing sensitive.
ALLOWED_FIELDS: Final[frozenset[str]] = frozenset({"keys", "monkeypatch"})

#: How deep to walk a nested value before giving up and redacting it whole.
MAX_REDACTION_DEPTH: Final[int] = 6

_REDACTED: Final[str] = "[redacted]"


class _StandardErrorStream:
    """Writes to whatever ``sys.stderr`` is at the moment of the call.

    Resolving the stream late keeps logging correct when the entry point is
    configured more than once and when a test harness replaces the stream.
    """

    def write(self, message: str) -> int:
        """Write one rendered log line."""
        return sys.stderr.write(message)

    def flush(self) -> None:
        """Flush the current stream."""
        sys.stderr.flush()


def redact_sensitive_fields(
    _logger: Any,  # noqa: ANN401 - structlog processor signature
    _name: str,
    event: structlog.typing.EventDict,
) -> structlog.typing.EventDict:
    """Replace the value of any forbidden field with a marker.

    Args:
        _logger: Unused; required by the structlog processor signature.
        _name: Unused; required by the structlog processor signature.
        event: The event dictionary about to be rendered.

    Returns:
        The event dictionary with sensitive values removed.
    """
    return {key: _scrubbed(key, value, 0) for key, value in event.items()}


def _is_forbidden(name: str) -> bool:
    """Whether a field name looks like it carries something sensitive.

    Args:
        name: The field name to judge.

    Returns:
        True when the name should never have its value written out.
    """
    lowered = name.lower()
    if lowered in ALLOWED_FIELDS:
        return False
    return any(word in lowered for word in FORBIDDEN_FIELDS)


def _scrubbed(name: str, value: object, depth: int) -> object:
    """Remove anything sensitive from one field, however deeply it is nested.

    A caller can pass a dictionary of headers or a list of records, so checking
    only the top level would leave a token one level down in plain sight.

    Args:
        name: The field name this value was given under.
        value: The value to clean.
        depth: How far down we already are.

    Returns:
        The value, with sensitive parts replaced by a marker.
    """
    if _is_forbidden(name):
        return _REDACTED
    if depth >= MAX_REDACTION_DEPTH:
        return _REDACTED
    if isinstance(value, dict):
        return {
            str(key): _scrubbed(str(key), inner, depth + 1)
            for key, inner in cast("dict[object, object]", value).items()
        }
    if isinstance(value, (list, tuple)):
        cleaned = [_scrubbed(name, inner, depth + 1) for inner in cast("list[object]", value)]
        return type(value)(cleaned) if isinstance(value, tuple) else cleaned
    return value


def configure_logging(
    level: LogLevel = LogLevel.INFO,
    app_env: AppEnv = AppEnv.DEVELOPMENT,
) -> None:
    """Configure structlog for this process.

    Logs go to standard error so they never mix with command output on stdout.

    Args:
        level: Lowest level that is emitted.
        app_env: Development renders human-readable lines; anything else renders JSON.
    """
    renderer: structlog.typing.Processor = (
        structlog.dev.ConsoleRenderer(colors=False)
        if app_env is AppEnv.DEVELOPMENT
        else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact_sensitive_fields,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(_LEVELS[level]),
        # The proxy only needs write() and flush(); it stands in for a text stream
        # so the current sys.stderr is resolved at write time.
        logger_factory=structlog.WriteLoggerFactory(file=cast("TextIO", _StandardErrorStream())),
        # Not cached: an entry point may configure logging more than once, and a
        # cached logger would keep the level captured the first time.
        cache_logger_on_first_use=False,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound logger for a module.

    Args:
        name: Usually ``__name__`` of the calling module.

    Returns:
        A logger that emits structured events.
    """
    return structlog.get_logger(name)
