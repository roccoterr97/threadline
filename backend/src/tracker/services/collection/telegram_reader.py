"""What the Telegram collector and the doctor need from Telegram.

The reader behind it (``infrastructure/telegram``) speaks Telegram's own
protocol; nothing on this side of the port knows which library does that, so
the collector is tested with a fake reader and no network.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Protocol

from tracker.domain.telegram import TelegramAccount, TelegramChat, TelegramMessage


class TelegramReader(Protocol):
    """Reads the owner's Telegram, read-only: it never sends and never marks anything as read."""

    async def account_name(self) -> str:
        """The logged-in account's own name; proves the saved login still works."""
        ...

    async def chats_since(self, since: datetime) -> Sequence[TelegramChat]:
        """Every chat whose newest message was sent at or after a moment, newest first."""
        ...

    async def recent_messages(self, chat: TelegramChat, limit: int) -> Sequence[TelegramMessage]:
        """The newest messages of one chat, at most ``limit``, newest first."""
        ...


#: Opens a reader on the owner's account for one collection, and closes it after.
TelegramOpener = Callable[[TelegramAccount], AbstractAsyncContextManager[TelegramReader]]
