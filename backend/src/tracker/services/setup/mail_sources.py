"""Reading and changing which mailboxes ``.env`` says Threadline reads."""

from __future__ import annotations

from typing import Final

from tracker.services.setup.context import SetupContext
from tracker.shared.constants.mailbox import DeliveryRoute, MailSource

#: The setting that lists the mailboxes read.
MAIL_SOURCES: Final[str] = "MAIL_SOURCES"

#: The setting that chooses how the summary is sent; unset means the usual way.
SUMMARY_DELIVERY: Final[str] = "SUMMARY_DELIVERY"

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


def summary_route(ctx: SetupContext) -> DeliveryRoute:
    """How the summary will be sent, read the way the configuration reads it.

    Args:
        ctx: The set-up's context.

    Returns:
        The saved choice; without one, SMTP once an IMAP mailbox is read,
        otherwise the Gmail connector of the alternative route.
    """
    chosen = (ctx.env.get(SUMMARY_DELIVERY) or "").strip().lower()
    routes = {route.value: route for route in DeliveryRoute}
    if chosen in routes:
        return routes[chosen]
    if MailSource.IMAP in (saved_sources(ctx) or ()):
        return DeliveryRoute.SMTP
    return DeliveryRoute.GMAIL_CONNECTOR


def save_sources(ctx: SetupContext, sources: tuple[MailSource, ...]) -> None:
    """Write the mailboxes to read, Outlook first.

    Args:
        ctx: The set-up's context.
        sources: The mailboxes; at least one.
    """
    ordered = [source for source in MailSource if source in sources]
    ctx.env.set(MAIL_SOURCES, _SEPARATOR.join(source.value for source in ordered))
    ctx.io.say(f"Saved {MAIL_SOURCES} in .env.")
