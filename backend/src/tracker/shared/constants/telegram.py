"""Fixed facts about reading Telegram with the owner's own account.

Threadline reads Telegram through Telegram's own user API (MTProto), with an
application the owner registers at my.telegram.org, read-only. None of this is
a secret or differs between machines, so it is code rather than configuration.
"""

from __future__ import annotations

from typing import Final

#: Where the owner registers their own application and copies its keys.
TELEGRAM_APPS_PAGE: Final[str] = "https://my.telegram.org/apps"

#: What the owner types into that page's form.
TELEGRAM_APP_TITLE: Final[str] = "Threadline"
TELEGRAM_APP_SHORT_NAME: Final[str] = "threadline"

#: How the session is named in Telegram > Settings > Devices, so the owner can
#: recognise it there and end it.
TELEGRAM_DEVICE_MODEL: Final[str] = "Threadline"
TELEGRAM_SYSTEM_VERSION: Final[str] = "read-only"
TELEGRAM_APP_VERSION: Final[str] = "1.0"

#: The account Telegram sends its own notices and login codes from.
TELEGRAM_SERVICE_USER_ID: Final[int] = 777_000

#: A pause Telegram asks for that is this short is waited out; a longer one
#: stops the read, and the next run tries again.
TELEGRAM_FLOOD_WAIT_MAX_SECONDS: Final[int] = 60

#: Most chats read in one run, newest first, so a fault can never turn into an
#: endless walk through years of chats.
TELEGRAM_MAX_CHATS: Final[int] = 500

#: Most messages read from one chat, newest first. A chat with somebody new in
#: the window is read in full up to this many, so the assessment sees the
#: conversation rather than its last line, without reading years of history.
TELEGRAM_MAX_MESSAGES_PER_CHAT: Final[int] = 200

#: Seconds one request to Telegram may take, and how many times a dropped
#: connection or request is tried again.
TELEGRAM_TIMEOUT_SECONDS: Final[int] = 30
TELEGRAM_RETRIES: Final[int] = 3

#: Length of an application's api_hash: 32 hexadecimal characters.
TELEGRAM_API_HASH_LENGTH: Final[int] = 32

#: The part of the guide that walks through Telegram.
TELEGRAM_GUIDE_SECTION: Final[str] = "docs/setup-your-accounts.md, the Telegram part"
