"""Plain text out of an HTML e-mail, with the standard library only.

Graph converts HTML bodies to text on its side; an IMAP server does not, so a
message that has only an HTML part is converted here. Scripts, styles and the
page head are dropped, block elements become line breaks, and entities are
decoded. Nothing is fetched: images and links are ignored.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Final

#: Elements whose content is never text the owner reads.
_SKIPPED_ELEMENTS: Final[frozenset[str]] = frozenset({"script", "style", "head", "title"})

#: Elements that start a new line when they open or close.
_BLOCK_ELEMENTS: Final[frozenset[str]] = frozenset(
    {
        "br",
        "p",
        "div",
        "tr",
        "li",
        "ul",
        "ol",
        "table",
        "blockquote",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "section",
        "article",
        "header",
        "footer",
    }
)

_SPACES: Final[re.Pattern[str]] = re.compile(r"[ \t\r\f\v ]+")
_BLANK_LINES: Final[re.Pattern[str]] = re.compile(r"\n\s*\n+")


class _TextCollector(HTMLParser):
    """Collects the visible text of a document."""

    def __init__(self) -> None:
        """Start with no text and outside any skipped element."""
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skipping = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Note a skipped element or a line break; attributes are never used."""
        if tag in _SKIPPED_ELEMENTS:
            self._skipping += 1
        elif tag in _BLOCK_ELEMENTS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        """Leave a skipped element, or end a block with a line break."""
        if tag in _SKIPPED_ELEMENTS:
            self._skipping = max(0, self._skipping - 1)
        elif tag in _BLOCK_ELEMENTS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        """Keep text that is not inside a skipped element."""
        if not self._skipping:
            self._parts.append(data)

    def text(self) -> str:
        """Return the collected text, with spacing tidied."""
        lines = (_SPACES.sub(" ", line).strip() for line in "".join(self._parts).split("\n"))
        joined = "\n".join(lines)
        return _BLANK_LINES.sub("\n\n", joined).strip()


def html_to_text(html: str) -> str:
    """Turn an HTML body into readable plain text.

    Args:
        html: The HTML, already decoded to a string.

    Returns:
        The visible text, one paragraph per line; empty for an empty document.
    """
    collector = _TextCollector()
    collector.feed(html)
    collector.close()
    return collector.text()
