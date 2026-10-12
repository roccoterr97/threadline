"""Fixed values for reading Slack direct messages.

Each owner makes their own small Slack app in their own workspace, from the
manifest below, and pastes its User OAuth Token. An app that lives only in the
workspace that made it is an "internal" app, which Slack leaves out of the
lower 2025 limits on reading message history for apps outside its Marketplace,
and no Threadline server is ever involved. None of this is a secret or differs
between machines, so it is code rather than configuration.
"""

from __future__ import annotations

import json
from typing import Final
from urllib.parse import quote

#: Slack's Web API root; the method name follows it.
SLACK_API_URL: Final[str] = "https://slack.com/api"

#: The host the cloud environment must be allowed to reach for Slack.
CLOUD_SLACK_HOST: Final[str] = "slack.com"

#: How every User OAuth Token starts.
SLACK_USER_TOKEN_PREFIX: Final[str] = "xoxp-"

#: Separates the tokens of several workspaces in ``SLACK_USER_TOKENS``. A token
#: is made of letters, digits and dashes only, so it never holds one.
SLACK_TOKEN_SEPARATOR: Final[str] = ","

#: Read-only user permissions: direct messages and group direct messages, and
#: who the people in them are, with their e-mail address so a Slack message
#: joins that person's e-mail record. Nothing that can post or change anything.
SLACK_USER_SCOPES: Final[tuple[str, ...]] = (
    "im:history",
    "im:read",
    "mpim:history",
    "mpim:read",
    "users:read",
    "users:read.email",
)

#: The app every owner creates in their own workspace. No bot, no events, no
#: token rotation: the token does not expire, so the daily run needs nothing
#: renewed.
SLACK_APP_MANIFEST: Final[dict[str, object]] = {
    "display_information": {
        "name": "Threadline",
        "description": "Reads your Slack direct messages for your own Threadline. Read-only.",
    },
    "oauth_config": {"scopes": {"user": list(SLACK_USER_SCOPES)}},
    "settings": {
        "org_deploy_enabled": False,
        "socket_mode_enabled": False,
        "token_rotation_enabled": False,
    },
}

#: Slack's "create an app from a manifest" page, with the manifest filled in.
SLACK_NEW_APP_LINK: Final[str] = "https://api.slack.com/apps?new_app=1&manifest_json=" + quote(
    json.dumps(SLACK_APP_MANIFEST, separators=(",", ":")), safe=""
)

#: Conversation kinds read: direct messages and group direct messages. Slack
#: Connect direct messages with people outside the workspace are ``im`` too.
SLACK_CONVERSATION_TYPES: Final[str] = "im,mpim"

#: Rows asked for per page; Slack recommends no more than 200.
SLACK_PAGE_SIZE: Final[int] = 200

#: Pages one listing may take before Threadline gives up, so a paging fault
#: cannot turn into an endless loop. 100 pages of 200 is 20,000 rows.
SLACK_MAX_PAGES: Final[int] = 100

#: Longest "Retry-After" wait Threadline sits out. Slack asks for longer only
#: when the workspace is far over its limit, and the next run reads the rest.
SLACK_LONGEST_WAIT_SECONDS: Final[float] = 60.0

#: Slackbot's user identifier: it is in every workspace and is never a person.
SLACKBOT_USER_ID: Final[str] = "USLACKBOT"

#: Message kinds that carry something a person wrote. Every other kind is
#: Slack's own notice ("joined", "pinned", "renamed"), never a conversation.
SLACK_PERSON_SUBTYPES: Final[frozenset[str]] = frozenset(
    {"thread_broadcast", "file_share", "me_message"}
)

#: Slack's error codes for a token it no longer accepts: revoked, removed with
#: the app, belonging to a deactivated account, or never valid.
SLACK_REFUSED_TOKEN_ERRORS: Final[frozenset[str]] = frozenset(
    {
        "not_authed",
        "invalid_auth",
        "token_revoked",
        "token_expired",
        "account_inactive",
        "missing_scope",
        "not_allowed_token_type",
    }
)

#: Slack's error codes for a workspace whose admin has not let the app in yet.
SLACK_APPROVAL_ERRORS: Final[frozenset[str]] = frozenset(
    {"team_access_not_granted", "access_denied", "no_permission", "org_login_required"}
)

#: Slack's error code, in the body of an answer, for "too many requests".
SLACK_RATE_LIMITED_ERROR: Final[str] = "ratelimited"

#: Shown for a message that holds only a file, so it is not stored empty.
SLACK_FILE_PLACEHOLDER: Final[str] = "[shared a file: {name}]"

#: Shown for a mention of somebody whose name could not be looked up.
SLACK_UNKNOWN_PERSON: Final[str] = "someone"
