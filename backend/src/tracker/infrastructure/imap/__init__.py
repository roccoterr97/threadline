"""Read-only access to any standard mailbox over IMAP: Gmail, iCloud, Yahoo, Fastmail.

Sign-in uses an app password the owner makes at their provider; it is kept
encrypted in the database, never in ``.env``. Folders are only ever opened with
EXAMINE and messages only fetched with ``BODY.PEEK``, so nothing here can mark,
move, flag or delete a message.
"""
