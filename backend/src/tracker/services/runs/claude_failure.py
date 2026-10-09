"""Why Claude stopped a run on GitHub, in one plain line.

``anthropics/claude-code-action`` keeps a record of the run (its "execution
file": every message, as JSON) and hides it from the log, because Claude's
words can quote the owner's mail. When Claude stops with an error, the reason
sits in that record: a code on Claude's last message, the status the service
answered, or Claude Code's own error line. This module reads only those and
says what happened and what to do. It never repeats anything Claude wrote: the
only text taken from the record is the service's own error line, and only
when it is recognisably one, cut short, with anything key-like removed.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Final, cast

from tracker.shared.constants.claude import (
    CLAUDE_BILLING_ERROR_CODES,
    CLAUDE_BILLING_ERROR_MARKERS,
    CLAUDE_BILLING_ERROR_STATUSES,
    CLAUDE_BUSY_ERROR_CODES,
    CLAUDE_BUSY_ERROR_MARKERS,
    CLAUDE_BUSY_ERROR_MIN_STATUS,
    CLAUDE_ERROR_DETAIL_MAX_CHARACTERS,
    CLAUDE_KEY_ERROR_CODES,
    CLAUDE_KEY_ERROR_MARKERS,
    CLAUDE_KEY_ERROR_STATUSES,
    CLAUDE_KEY_FAMILY_PREFIX,
    CLAUDE_LIMIT_ERROR_CODES,
    CLAUDE_LIMIT_ERROR_MARKERS,
    CLAUDE_LIMIT_ERROR_STATUSES,
    CLAUDE_MAX_TURNS_SUBTYPE,
    CLAUDE_MODEL_ERROR_CODES,
    CLAUDE_SERVICE_ERROR_PREFIXES,
)
from tracker.shared.constants.github import CLAUDE_TOKEN_SECRET
from tracker.shared.logging import get_logger

_log = get_logger(__name__)

#: Anything that looks like a Claude key, removed from a detail before it is shown.
_KEY_LIKE: Final[re.Pattern[str]] = re.compile(rf"{CLAUDE_KEY_FAMILY_PREFIX}[A-Za-z0-9_-]*")
_REMOVED: Final[str] = "[removed]"

#: What to do when the key has to be made again.
_NEW_KEY: Final[str] = (
    "Make a new key with 'claude setup-token', then run 'uv run tracker setup github' and paste it."
)


class ClaudeStopReason(StrEnum):
    """The kinds of reason Claude stops a run for, as far as the record tells."""

    KEY_REFUSED = "key_refused"
    NOT_SUBSCRIBED = "not_subscribed"
    USAGE_LIMIT = "usage_limit"
    SERVICE_BUSY = "service_busy"
    MODEL_UNAVAILABLE = "model_unavailable"
    TOO_MANY_STEPS = "too_many_steps"
    NO_RECORD = "no_record"
    OTHER = "other"


#: The line said for each reason; ``OTHER`` may add the service's own words.
_LINES: Final[Mapping[ClaudeStopReason, str]] = {
    ClaudeStopReason.KEY_REFUSED: (
        f"Claude did not accept the key saved on GitHub ({CLAUDE_TOKEN_SECRET}): it is "
        f"incomplete, expired or was cancelled. {_NEW_KEY}"
    ),
    ClaudeStopReason.NOT_SUBSCRIBED: (
        "Claude would not run on this key's account: the key does not come from an "
        f"active Claude subscription. Check your plan on claude.ai. {_NEW_KEY}"
    ),
    ClaudeStopReason.USAGE_LIMIT: (
        "Your Claude plan's usage limit was reached, so Claude stopped. Nothing needs "
        "fixing: the next run goes ahead once the limit resets."
    ),
    ClaudeStopReason.SERVICE_BUSY: (
        "Claude's service was busy or down for a moment. Nothing needs fixing: the next "
        "run tries again."
    ),
    ClaudeStopReason.MODEL_UNAVAILABLE: (
        "Claude would not use its model with this key's plan. Make a new key with "
        "'claude setup-token' while signed in to the account with your paid plan, then "
        "run 'uv run tracker setup github' and paste it."
    ),
    ClaudeStopReason.TOO_MANY_STEPS: (
        "Claude used every step it is allowed before it finished. The next run tries again."
    ),
    ClaudeStopReason.NO_RECORD: (
        "Claude stopped before it could say why, for example because the run ran out of "
        "time. The next run tries again."
    ),
    ClaudeStopReason.OTHER: "Claude stopped with an error",
}

#: What to do after an error that is not recognised.
_OTHER_ADVICE: Final[str] = (
    "If the next run stops the same way, make a new key with 'claude setup-token' and "
    "run 'uv run tracker setup github'."
)


def explain_execution_file(path: Path | None) -> str:
    """Say in one line why Claude stopped, from the action's execution file.

    Args:
        path: The file, or ``None`` when the action wrote none.

    Returns:
        One plain line: what happened and what to do.
    """
    if path is None or not path.is_file():
        return explain_messages(())
    try:
        loaded: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        _log.warning("claude_record_unreadable", error_type=type(error).__name__)
        return explain_messages(())
    messages = cast("list[object]", loaded) if isinstance(loaded, list) else []
    return explain_messages(messages)


def explain_messages(messages: Sequence[object]) -> str:
    """Say in one line why Claude stopped, from the run's messages.

    Args:
        messages: The run's messages, as the execution file holds them.

    Returns:
        One plain line: what happened and what to do.
    """
    result = _last_of_type(messages, "result")
    if result is None:
        return _LINES[ClaudeStopReason.NO_RECORD]
    reason = stop_reason(result, _last_of_type(messages, "assistant"))
    _log.info("claude_stop_explained", reason=reason.value)
    if reason is not ClaudeStopReason.OTHER:
        return _LINES[reason]
    detail = _service_detail(_error_text(result))
    said = f"{_LINES[reason]}: {detail}." if detail else f"{_LINES[reason]}."
    return f"{said} {_OTHER_ADVICE}"


def stop_reason(
    result: Mapping[str, object], assistant: Mapping[str, object] | None
) -> ClaudeStopReason:
    """Read why Claude stopped: its error code first, then the status, then its words.

    Args:
        result: The run's result message.
        assistant: Claude's last message, or ``None`` when there was none.

    Returns:
        The reason.
    """
    if result.get("subtype") == CLAUDE_MAX_TURNS_SUBTYPE:
        return ClaudeStopReason.TOO_MANY_STEPS
    code = assistant.get("error") if assistant is not None else None
    by_code = _reason_by_code(code) if isinstance(code, str) else None
    if by_code is not None:
        return by_code
    status = result.get("api_error_status")
    by_status = _reason_by_status(status) if isinstance(status, int) else None
    if by_status is not None:
        return by_status
    return _reason_by_words(_error_text(result).lower())


def _reason_by_code(code: str) -> ClaudeStopReason | None:
    """The reason a Claude Code error code names, if it is one of the known ones."""
    groups = (
        (CLAUDE_KEY_ERROR_CODES, ClaudeStopReason.KEY_REFUSED),
        (CLAUDE_BILLING_ERROR_CODES, ClaudeStopReason.NOT_SUBSCRIBED),
        (CLAUDE_LIMIT_ERROR_CODES, ClaudeStopReason.USAGE_LIMIT),
        (CLAUDE_BUSY_ERROR_CODES, ClaudeStopReason.SERVICE_BUSY),
        (CLAUDE_MODEL_ERROR_CODES, ClaudeStopReason.MODEL_UNAVAILABLE),
    )
    return next((reason for codes, reason in groups if code in codes), None)


def _reason_by_status(status: int) -> ClaudeStopReason | None:
    """The reason the service's answer status names, if it is one of the known ones."""
    if status in CLAUDE_KEY_ERROR_STATUSES:
        return ClaudeStopReason.KEY_REFUSED
    if status in CLAUDE_BILLING_ERROR_STATUSES:
        return ClaudeStopReason.NOT_SUBSCRIBED
    if status in CLAUDE_LIMIT_ERROR_STATUSES:
        return ClaudeStopReason.USAGE_LIMIT
    if status >= CLAUDE_BUSY_ERROR_MIN_STATUS:
        return ClaudeStopReason.SERVICE_BUSY
    return None


def _reason_by_words(text: str) -> ClaudeStopReason:
    """The reason Claude Code's error line names, read from its words."""
    groups = (
        (CLAUDE_KEY_ERROR_MARKERS, ClaudeStopReason.KEY_REFUSED),
        (CLAUDE_BILLING_ERROR_MARKERS, ClaudeStopReason.NOT_SUBSCRIBED),
        (CLAUDE_LIMIT_ERROR_MARKERS, ClaudeStopReason.USAGE_LIMIT),
        (CLAUDE_BUSY_ERROR_MARKERS, ClaudeStopReason.SERVICE_BUSY),
    )
    found = (reason for markers, reason in groups if any(word in text for word in markers))
    return next(found, ClaudeStopReason.OTHER)


def _last_of_type(messages: Sequence[object], kind: str) -> Mapping[str, object] | None:
    """The last message of one type, or ``None`` when there is none."""
    for message in reversed(messages):
        if isinstance(message, dict):
            fields = cast("dict[str, object]", message)
            if fields.get("type") == kind:
                return fields
    return None


def _error_text(result: Mapping[str, object]) -> str:
    """Claude Code's error line: the result's text, else its list of errors."""
    text = result.get("result")
    if isinstance(text, str) and text.strip():
        return text
    errors = result.get("errors")
    if isinstance(errors, list):
        return " ".join(str(error) for error in cast("list[object]", errors))
    return ""


def _service_detail(text: str) -> str | None:
    """The service's own error line, safe to show, or ``None`` when it is not one."""
    lines = text.strip().splitlines()
    first = lines[0].strip() if lines else ""
    if not first.lower().startswith(CLAUDE_SERVICE_ERROR_PREFIXES):
        return None
    cleaned = _KEY_LIKE.sub(_REMOVED, first)
    return cleaned[:CLAUDE_ERROR_DETAIL_MAX_CHARACTERS].rstrip(" .")
