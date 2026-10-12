"""Turning Slack's message markup into plain text.

Slack writes a mention as ``<@U123>``, a link as ``<https://…|label>`` and
escapes ``&``, ``<`` and ``>``. The assessment reads plain text, so every such
token is spelled out the way a person reading the message sees it.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final

#: One ``<…>`` token, with its optional ``|label``.
_TOKEN: Final[re.Pattern[str]] = re.compile(r"<([^<>|]+)(?:\|([^<>]*))?>")

#: Slack's three escaped characters, ``&amp;`` last so ``&amp;lt;`` stays ``&lt;``.
_ESCAPES: Final[tuple[tuple[str, str], ...]] = (("&lt;", "<"), ("&gt;", ">"), ("&amp;", "&"))

#: Special mentions, such as ``<!here>``.
_SPECIAL: Final[dict[str, str]] = {"here": "@here", "channel": "@channel", "everyone": "@everyone"}


def plain_text(text: str, names: Mapping[str, str], unknown_person: str) -> str:
    """Spell out every Slack markup token as plain text.

    Args:
        text: The message in Slack's markup.
        names: Known people's names, by Slack user identifier.
        unknown_person: What a mention of somebody not in ``names`` becomes.

    Returns:
        The text as a person reads it: ``@Name``, ``#channel``, ``label (link)``.
    """

    def replace(match: re.Match[str]) -> str:
        return _spelled(match.group(1), match.group(2), names, unknown_person)

    return _unescape(_TOKEN.sub(replace, text)).strip()


def mentioned_users(text: str) -> tuple[str, ...]:
    """List the user identifiers a message mentions, each once, in order.

    Args:
        text: The message in Slack's markup.

    Returns:
        The identifiers inside ``<@…>`` tokens.
    """
    found = [
        target.removeprefix("@") for target, _ in _TOKEN.findall(text) if target.startswith("@")
    ]
    return tuple(dict.fromkeys(found))


def _spelled(target: str, label: str | None, names: Mapping[str, str], unknown: str) -> str:
    """Spell out one token from what it points at and its label."""
    if target.startswith("@"):
        name = names.get(target[1:]) or label or unknown
        return f"@{name.removeprefix('@')}"
    if target.startswith("#"):
        return f"#{label}" if label else "#channel"
    if target.startswith("!"):
        return _special(target[1:], label)
    return _link(target, label)


def _special(target: str, label: str | None) -> str:
    """Spell out ``<!here>``, a user group or a date, preferring Slack's own label."""
    if label:
        return _unescape(label)
    return _SPECIAL.get(target, f"@{target.split('^', 1)[0]}")


def _link(url: str, label: str | None) -> str:
    """Spell out a link: the address alone, or the label followed by the address."""
    address = url.removeprefix("mailto:")
    if not label or _unescape(label) in {url, address}:
        return address
    return f"{_unescape(label)} ({address})"


def _unescape(text: str) -> str:
    """Undo Slack's escaping of ``&``, ``<`` and ``>``."""
    for escaped, character in _ESCAPES:
        text = text.replace(escaped, character)
    return text
