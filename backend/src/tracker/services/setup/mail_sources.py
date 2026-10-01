"""Reading and changing which mailboxes ``.env`` says Threadline reads."""

from __future__ import annotations

from typing import Final

from tracker.services.setup.context import SetupContext
from tracker.shared.constants.mailbox import MailSource

#: The setting that lists the mailboxes read.
MAIL_SOURCES: Final[str] = "MAIL_SOURCES"

_SEPARATOR: Final[str] = ","


def saved_sources(ctx: SetupContext) -> tuple[MailSource, ...] | None:
    """The mailboxes ``.env`` lists, or ``None`` when it does not say.

    Args:
        ctx: The set-up's context.

    Returns:
        The known mailboxes listed, in order; unknown words are ignored here
        because the configuration check reports them.
    """
    raw = ctx.env.get(MAIL_SOURCES)
    if raw is None:
        return None
    known = {source.value: source for source in MailSource}
    words = (word.strip().lower() for word in raw.split(_SEPARATOR))
    return tuple(dict.fromkeys(known[word] for word in words if word in known))


def save_sources(ctx: SetupContext, sources: tuple[MailSource, ...]) -> None:
    """Write the mailboxes to read, Outlook first.

    Args:
        ctx: The set-up's context.
        sources: The mailboxes; at least one.
    """
    ordered = [source for source in MailSource if source in sources]
    ctx.env.set(MAIL_SOURCES, _SEPARATOR.join(source.value for source in ordered))
    ctx.io.say(f"Saved {MAIL_SOURCES} in .env.")
