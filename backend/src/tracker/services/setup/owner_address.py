"""Offering to record an address the owner just connected as one of their own."""

from __future__ import annotations

from typing import Final

from tracker.services.setup import values
from tracker.services.setup.context import SetupContext

#: The setting that lists the owner's own addresses.
OWNER_ADDRESSES: Final[str] = "OWNER_EMAIL_ADDRESSES"


def remember_address(ctx: SetupContext, address: str) -> None:
    """Offer to add a connected mailbox's address to the owner's own addresses.

    When the owner declines and no address is saved yet, one is asked for, so
    the owner's own messages always count as theirs.

    Args:
        ctx: The set-up's context.
        address: The address just connected; empty when the service did not say.
    """
    existing = ctx.env.get(OWNER_ADDRESSES)
    if address and address in (existing or "").lower().split(","):
        return
    if address and ctx.io.confirm(
        f"Add {address} to your own addresses ({OWNER_ADDRESSES})?", default=True
    ):
        ctx.env.set(OWNER_ADDRESSES, values.merged_addresses(existing, address))
        ctx.io.say(f"Saved {OWNER_ADDRESSES} in .env.")
        return
    if existing is None:
        typed = ctx.ask_until_valid(
            lambda: ctx.io.ask("Your own e-mail address, so your messages count as yours"),
            values.email_address,
        )
        ctx.write(OWNER_ADDRESSES, typed)
