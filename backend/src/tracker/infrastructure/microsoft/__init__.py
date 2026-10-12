"""Read-only access to the owner's Microsoft mailbox, calendar and Teams chats.

Sign-in uses the one-time-code flow, which needs no Microsoft developer
account. Outlook (mail and calendar) and Teams chats are two separate sign-ins,
each with read-only permissions and a key of its own. Nothing here can send,
move or delete anything.
"""
