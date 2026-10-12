"""Slack's Web API, read-only, with the owner's own User OAuth Token.

Plain HTTPS calls through the project's one retry policy; no Slack library.
The token never leaves the ``Authorization`` header: not a log line, not an
error message.
"""
