"""Telling a mailbox's provider from its address, so the set-up need not ask."""

from __future__ import annotations

from tracker.shared.constants.mailbox import (
    MAILBOX_ENDING_PART_MAX_LENGTH,
    MAILBOX_PROVIDER_BY_DOMAIN,
    MAILBOX_PROVIDER_BY_NAME,
    ImapProvider,
    MailSource,
)


def provider_for(address: str) -> MailSource | ImapProvider | None:
    """Name the provider an address belongs to, when its ending says so.

    Args:
        address: An e-mail address, such as ``sam@hotmail.co.uk``.

    Returns:
        Gmail, Outlook (``MailSource.OUTLOOK``), iCloud, Yahoo or Fastmail, or
        ``None`` for any other ending, such as a company's own domain, whose
        provider cannot be told from the address.
    """
    domain = address.rpartition("@")[2].strip().lower().rstrip(".")
    known = MAILBOX_PROVIDER_BY_DOMAIN.get(domain)
    if known is not None:
        return known
    name, _, ending = domain.partition(".")
    parts = ending.split(".")
    if not ending or any(not part or len(part) > MAILBOX_ENDING_PART_MAX_LENGTH for part in parts):
        return None
    return MAILBOX_PROVIDER_BY_NAME.get(name)
