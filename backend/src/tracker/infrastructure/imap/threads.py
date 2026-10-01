"""Grouping messages into threads when the server offers no thread identifier.

Gmail names every thread itself (``X-GM-THRID``). Other servers do not, so a
thread is recognised the way mail programs do it: by the chain of identifiers
in ``References`` and ``In-Reply-To``, whose first entry is the message that
started the conversation. That first entry is the same on every later run, so
a thread keeps its identity from one morning to the next.

A reply whose program dropped those headers falls back to its subject, but
only when the subject says it is a reply ("Re:", "Fwd:"…), so two unrelated
messages that merely share a subject are never joined.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

#: Reply and forward markers, in the languages mail programs commonly write them.
_REPLY_PREFIX: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:(?:re|fwd?|aw|sv|antw|wg|tr|rif|vs)\s*(?:\[\d+\])?\s*:\s*)+",
    re.IGNORECASE,
)

MESSAGE_KEY: Final[str] = "mid:"
SUBJECT_KEY: Final[str] = "subject:"
FALLBACK_KEY: Final[str] = "own:"


@dataclass(frozen=True, slots=True)
class ThreadFacts:
    """The headers that place one message in a thread.

    Attributes:
        message_id: Its Message-ID, empty when it has none.
        in_reply_to: The message it answers, empty when unknown.
        references: The chain of earlier messages, oldest first.
        subject: Its decoded subject.
        stand_in: A key unique to this message, used when nothing else applies.
    """

    message_id: str
    in_reply_to: str
    references: tuple[str, ...]
    subject: str
    stand_in: str


def normalised_subject(subject: str) -> tuple[str, bool]:
    """Strip reply and forward markers from a subject.

    Args:
        subject: The subject as written.

    Returns:
        The bare subject in lower case, and whether it carried a marker.
    """
    bare = _REPLY_PREFIX.sub("", subject)
    return " ".join(bare.split()).lower(), bare != subject


def thread_keys(messages: Sequence[ThreadFacts]) -> list[str]:
    """Give every message the key of the thread it belongs to.

    Args:
        messages: The messages, in any order.

    Returns:
        One key per message, in the same order. Keys start with
        :data:`MESSAGE_KEY` (the thread's first message), :data:`SUBJECT_KEY`
        or :data:`FALLBACK_KEY`.
    """
    by_id = {message.message_id: message for message in messages if message.message_id}
    keys = [_chain_key(message, by_id) for message in messages]
    anchored: dict[str, str] = {}
    for message, key in zip(messages, keys, strict=True):
        if key.startswith(MESSAGE_KEY):
            anchored.setdefault(normalised_subject(message.subject)[0], key)
    return [
        anchored.get(key.removeprefix(SUBJECT_KEY), key) if key.startswith(SUBJECT_KEY) else key
        for key in keys
    ]


def _chain_key(message: ThreadFacts, by_id: dict[str, ThreadFacts]) -> str:
    """The key the message's own headers give it, following replies in the set."""
    if message.references:
        return MESSAGE_KEY + message.references[0]
    if message.in_reply_to:
        return MESSAGE_KEY + _root_of(message.in_reply_to, by_id)
    bare, is_reply = normalised_subject(message.subject)
    if is_reply and bare:
        return SUBJECT_KEY + bare
    if message.message_id:
        return MESSAGE_KEY + message.message_id
    return FALLBACK_KEY + message.stand_in


def _root_of(message_id: str, by_id: dict[str, ThreadFacts]) -> str:
    """Walk up the In-Reply-To chain as far as the set of messages allows."""
    seen: set[str] = set()
    current = message_id
    while current in by_id and current not in seen:
        seen.add(current)
        parent = by_id[current]
        if parent.references:
            return parent.references[0]
        if not parent.in_reply_to:
            return current
        current = parent.in_reply_to
    return current
