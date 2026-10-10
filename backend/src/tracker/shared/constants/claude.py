"""Fixed facts about the Claude subscription key and how Claude reports a failed run.

The key is the one ``claude setup-token`` prints; GitHub's daily run uses it
through ``anthropics/claude-code-action``. When that run fails, the action
hides everything Claude wrote (it can quote the owner's mail), so the reason
is read from the run's own record and said in one plain line, under the title
below; the set-up looks for that title when it watches the first run.
"""

from __future__ import annotations

from typing import Final

#: How every Claude key starts.
CLAUDE_KEY_FAMILY_PREFIX: Final[str] = "sk-ant-"

#: How the subscription key from ``claude setup-token`` starts ("oat": OAuth token).
CLAUDE_SUBSCRIPTION_KEY_PREFIX: Final[str] = "sk-ant-oat"

#: How a pay-as-you-go API key starts: it bills an API account, not the subscription.
CLAUDE_API_KEY_PREFIX: Final[str] = "sk-ant-api"

#: The characters a key is made of; anything else was copied along with it.
CLAUDE_KEY_CHARACTERS: Final[str] = r"[A-Za-z0-9_-]+"

#: Fewer characters than this is a key cut short. A whole key is about 108
#: characters, and ``claude setup-token`` wraps it at the window's width, so a
#: copy of its first line alone, in an ordinary 80-column window, is far shorter.
#: The floor stays well below the whole length, so a whole key is never refused.
CLAUDE_KEY_MIN_LENGTH: Final[int] = 90

#: The command Claude Code is run with, and its words that make a subscription key.
CLAUDE_COMMAND: Final[str] = "claude"
CLAUDE_SETUP_TOKEN_ARGUMENTS: Final[tuple[str, ...]] = ("setup-token",)

#: Where Anthropic's own installer puts ``claude`` on macOS and Linux, under the
#: home folder. A terminal opened before the install may not look there yet.
CLAUDE_NATIVE_INSTALL_PATH: Final[tuple[str, ...]] = (".local", "bin", "claude")

#: Where Claude Code's installation is explained, for anyone who does not have it.
CLAUDE_CODE_SETUP_PAGE: Final[str] = "https://code.claude.com/docs/en/setup"

#: The width, in characters, of the screen ``claude setup-token`` draws on when
#: the set-up runs it. Far wider than any window, so the key comes on one line.
CLAUDE_KEY_SCREEN_COLUMNS: Final[int] = 1000

#: The height of that screen, in lines.
CLAUDE_KEY_SCREEN_ROWS: Final[int] = 50

#: Seconds the set-up waits for the key: time to sign in and click Authorize.
#: After that ``claude setup-token`` is stopped and the key is pasted instead.
CLAUDE_KEY_WAIT_SECONDS: Final[float] = 300.0

#: Seconds without a key before the owner is told they can paste a sign-in
#: code, which the Claude page shows when it cannot hand the sign-in back itself.
CLAUDE_KEY_CODE_HINT_SECONDS: Final[float] = 30.0

#: Most characters of Claude's screen kept while looking for its sign-in
#: address: far more than the address, so it is never cut, and the screen,
#: redrawn many times a second, is never kept whole.
CLAUDE_SIGN_IN_ADDRESS_WINDOW: Final[int] = 8192

#: Seconds between two looks at the screen and the keyboard while waiting.
CLAUDE_KEY_POLL_SECONDS: Final[float] = 0.1

#: Seconds ``claude setup-token`` is given to end after its screen closed.
CLAUDE_KEY_EXIT_SECONDS: Final[float] = 5.0

#: The title of the one line the workflow writes when Claude stopped with an
#: error. ``.github/workflows/threadline-run.yml`` repeats it; a test keeps both equal.
CLAUDE_STOPPED_TITLE: Final[str] = "Why Claude stopped"

#: Longest stretch of an unrecognised error that is shown, so a long answer
#: from the service never fills the run's page.
CLAUDE_ERROR_DETAIL_MAX_CHARACTERS: Final[int] = 160

#: How such an error starts when it is the service's own answer, which names a
#: status and a type, never what Claude was reading. Anything else is not shown.
CLAUDE_SERVICE_ERROR_PREFIXES: Final[tuple[str, ...]] = ("api error",)

#: The codes Claude Code puts on its last message when a call to Claude failed.
CLAUDE_KEY_ERROR_CODES: Final[frozenset[str]] = frozenset({"authentication_failed"})
CLAUDE_BILLING_ERROR_CODES: Final[frozenset[str]] = frozenset({"billing_error"})
CLAUDE_LIMIT_ERROR_CODES: Final[frozenset[str]] = frozenset({"rate_limit"})
CLAUDE_BUSY_ERROR_CODES: Final[frozenset[str]] = frozenset({"overloaded", "server_error"})
CLAUDE_MODEL_ERROR_CODES: Final[frozenset[str]] = frozenset({"model_not_found"})

#: The answer statuses that say the same, for a record without those codes.
CLAUDE_KEY_ERROR_STATUSES: Final[frozenset[int]] = frozenset({401, 403})
CLAUDE_BILLING_ERROR_STATUSES: Final[frozenset[int]] = frozenset({402})
CLAUDE_LIMIT_ERROR_STATUSES: Final[frozenset[int]] = frozenset({429})
#: 500 and up: the service itself had a problem (529 is "overloaded").
CLAUDE_BUSY_ERROR_MIN_STATUS: Final[int] = 500

#: Words in Claude Code's error line that say the same, for an older record
#: with neither codes nor statuses. Compared in lower case.
CLAUDE_KEY_ERROR_MARKERS: Final[tuple[str, ...]] = (
    "invalid api key",
    "failed to authenticate",
    "authentication_error",
    "oauth token",
    "invalid bearer token",
    "/login",
)
CLAUDE_BILLING_ERROR_MARKERS: Final[tuple[str, ...]] = ("credit balance",)
CLAUDE_LIMIT_ERROR_MARKERS: Final[tuple[str, ...]] = (
    "usage limit",
    "hit your limit",
    "rate_limit_error",
)
CLAUDE_BUSY_ERROR_MARKERS: Final[tuple[str, ...]] = (
    "overloaded",
    "api error: 5",
    "internal server error",
)

#: The result subtype Claude Code reports when it used every step it was allowed.
CLAUDE_MAX_TURNS_SUBTYPE: Final[str] = "error_max_turns"
