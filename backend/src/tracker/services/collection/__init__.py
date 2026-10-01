"""Collecting messages from LinkedIn and the mailbox into the database.

Each collector follows the same four steps: read the source, group the messages
into threads, apply the obvious-noise rules, and write the result as idempotent
upserts. Running a collector twice changes nothing.
"""
