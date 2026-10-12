"""Telegram, through its own user API (MTProto) and the Telethon library.

The only code that knows Telethon exists. It reads, read-only, with the
owner's own application and login: it never sends a message, never marks a
message as read and never changes anything on the account. Everything it hands
back is a plain record from :mod:`tracker.domain.telegram`.
"""
