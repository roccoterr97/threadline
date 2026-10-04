"""Fixed values for ``tracker setup`` and ``tracker doctor``.

Addresses of the pages the set-up opens, the hosts the cloud environment must
be allowed to reach, and a few limits. None of it is a secret or differs
between machines, so it is code rather than configuration.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Final

from tracker.shared.config import REPOSITORY_ROOT

#: Where the database structure files live, applied in name order.
MIGRATIONS_DIRECTORY: Final[Path] = REPOSITORY_ROOT / "supabase" / "migrations"

#: File permissions of a ``.env`` the set-up creates: readable by you alone.
ENV_FILE_MODE: Final[int] = 0o600

#: Name of the throw-away secret the checks write, read back and remove.
SECRET_PROBE_NAME: Final[str] = "healthcheck_probe"

#: What they write; the value itself is meaningless.
SECRET_PROBE_VALUE: Final[str] = "healthcheck"

#: What to do when the configuration is missing or wrong, as the doctor and a
#: failed command both say it.
CONFIGURATION_FIX: Final[str] = (
    "run 'uv run tracker setup'; on GitHub, add the missing secrets with "
    "'uv run tracker setup github'"
)

# --- The set-up page in the browser -----------------------------------------

#: The page is served to this computer only; never to the network.
FORM_HOST: Final[str] = "127.0.0.1"

#: The header the page sends with its key, so no other page can read or answer.
FORM_KEY_HEADER: Final[str] = "X-Setup-Key"

#: Bytes of randomness in that key.
FORM_KEY_BYTES: Final[int] = 32

#: Longest answer the page may send, in bytes; keys and addresses are far shorter.
FORM_MAX_BODY_BYTES: Final[int] = 64 * 1024

#: Seconds a question waits between two looks at whether the page is still there.
FORM_WAIT_SLICE_SECONDS: Final[float] = 1.0

#: Seconds without a sign of life from the page before the set-up stops, so a
#: closed tab never leaves the command waiting forever. Browsers slow a tab
#: that is not in front down to one check a minute, so this is generous.
FORM_IDLE_LIMIT_SECONDS: Final[float] = 15 * 60

#: Seconds the page is kept up after the end, so it can show the last word.
FORM_FAREWELL_SECONDS: Final[float] = 5.0

# --- Supabase ---------------------------------------------------------------

#: Every Supabase project address ends with this.
SUPABASE_HOST_SUFFIX: Final[str] = ".supabase.co"

#: Supabase's Management API, reached with a personal access token.
SUPABASE_MANAGEMENT_API_URL: Final[str] = "https://api.supabase.com/v1"

#: Supabase's web dashboard.
SUPABASE_DASHBOARD_URL: Final[str] = "https://supabase.com/dashboard"

#: Page listing your projects, where a new one is created.
SUPABASE_PROJECTS_PAGE: Final[str] = f"{SUPABASE_DASHBOARD_URL}/projects"

#: Page where a personal access token is created.
SUPABASE_TOKENS_PAGE: Final[str] = f"{SUPABASE_DASHBOARD_URL}/account/tokens"

#: Project pages, with ``{ref}`` standing for the project's identifier.
SUPABASE_API_KEYS_PAGE: Final[str] = f"{SUPABASE_DASHBOARD_URL}/project/{{ref}}/settings/api-keys"
SUPABASE_SQL_EDITOR_PAGE: Final[str] = f"{SUPABASE_DASHBOARD_URL}/project/{{ref}}/sql"
SUPABASE_SIGN_IN_PAGE: Final[str] = f"{SUPABASE_DASHBOARD_URL}/project/{{ref}}/auth/providers"
SUPABASE_URL_CONFIGURATION_PAGE: Final[str] = (
    f"{SUPABASE_DASHBOARD_URL}/project/{{ref}}/auth/url-configuration"
)

#: Seconds between two structure files sent to the Management API. Supabase
#: names each applied file after the current second, so two files sent within
#: the same second collide and the second one is refused.
MIGRATION_PAUSE_SECONDS: Final[float] = 1.5

#: Seconds to wait before sending a refused structure file once more.
MIGRATION_RETRY_WAIT_SECONDS: Final[float] = 3.0

#: Longest part of a service's own error message that is logged and shown.
SERVICE_ERROR_DETAIL_LENGTH: Final[int] = 300

#: Logins read per page while looking one up by address.
AUTH_USERS_PAGE_SIZE: Final[int] = 50

#: Pages read before giving up; a personal project has one or two logins.
AUTH_USERS_MAX_PAGES: Final[int] = 20

# --- LinkedIn ----------------------------------------------------------------

#: LinkedIn's page for making an access key by hand.
LINKEDIN_TOKEN_GENERATOR_PAGE: Final[str] = (
    "https://www.linkedin.com/developers/tools/oauth/token-generator"
)

#: Your applications on LinkedIn's developer portal, where a new one is created.
LINKEDIN_DEVELOPER_APPS_PAGE: Final[str] = "https://www.linkedin.com/developers/apps"

#: The company page LinkedIn provides for this product, so nobody has to create one.
LINKEDIN_DEFAULT_COMPANY: Final[str] = "Member Data Portability (Member) Default Company"

#: The product to request on the application's Products tab.
LINKEDIN_PRODUCT: Final[str] = "Member Data Portability API (Member)"

#: How the name of the permission to tick begins. LinkedIn's own pages end it
#: in two different ways, so only the beginning is ever shown.
LINKEDIN_PERMISSION_PREFIX: Final[str] = "r_dma_portability"

#: Every LinkedIn profile address starts with this.
LINKEDIN_PROFILE_PREFIX: Final[str] = "https://www.linkedin.com/in/"

#: The part of the guide that walks through LinkedIn by hand.
LINKEDIN_GUIDE_SECTION: Final[str] = "docs/setup-your-accounts.md, part 6 (LinkedIn)"

# --- Claude cloud ------------------------------------------------------------

#: Where cloud environments and routines are managed.
CLAUDE_CODE_PAGE: Final[str] = "https://claude.ai/code"

#: Host the cloud needs when Outlook is read, besides the default list of
#: package managers (which already covers the Microsoft sign-in host). An IMAP
#: mailbox's server is added from the settings.
CLOUD_OUTLOOK_HOST: Final[str] = "graph.microsoft.com"

#: Host the cloud needs only when LinkedIn is connected.
CLOUD_LINKEDIN_HOST: Final[str] = "api.linkedin.com"

#: Settings that exist on your Mac only and are never copied to the cloud.
LOCAL_ONLY_SETTINGS: Final[frozenset[str]] = frozenset({"APP_ENV", "LOG_LEVEL"})

# --- Refresh now -------------------------------------------------------------

#: The Edge Function behind the dashboard's "Refresh now" button.
REFRESH_FUNCTION_SLUG: Final[str] = "refresh-now"

#: Where its source files are in the repository.
REFRESH_FUNCTION_DIRECTORY: Final[Path] = (
    REPOSITORY_ROOT / "supabase" / "functions" / REFRESH_FUNCTION_SLUG
)

#: The files deployed, the first being the one Supabase starts.
REFRESH_FUNCTION_FILES: Final[tuple[str, ...]] = ("index.ts", "refresh.ts")

#: Where a project serves an Edge Function, below the project address.
FUNCTION_PATH: Final[str] = "/functions/v1/{slug}"

#: What a deployed "Refresh now" answers a caller who is not signed in.
REFRESH_GUARD_STATUSES: Final[frozenset[int]] = frozenset({401, 403})

#: What Supabase answers when no function of that name is deployed.
FUNCTION_MISSING_STATUS: Final[int] = 404

#: The branch the dashboard's refresh runs the workflow on.
REFRESH_BRANCH: Final[str] = "main"

#: Where the set-up and the doctor point the owner for "Refresh now".
REFRESH_GUIDE_SECTION: Final[str] = "docs/setup-your-accounts.md, part 8f"

#: Supabase's own JWT check stays off: the function refuses a caller without a
#: sign-in itself (401) and asks the database whether the signed-in caller is
#: the owner, which also rejects a forged sign-in. With Supabase's check on,
#: the browser's CORS preflight, which carries no sign-in, would be refused,
#: and the new non-JWT API keys would be too.
REFRESH_FUNCTION_VERIFY_JWT: Final[bool] = False

#: How often the set-up looks for the freshly deployed function, and how long
#: it waits in between: a deploy takes a few seconds to go live.
REFRESH_PROBE_ATTEMPTS: Final[int] = 5
REFRESH_PROBE_WAIT_SECONDS: Final[float] = 3.0


class RefreshSetting(StrEnum):
    """The "Refresh now" function's settings (Supabase calls them secrets)."""

    TARGET = "REFRESH_TARGET"
    REPOSITORY = "GITHUB_REPOSITORY"
    BRANCH = "GITHUB_REF"
    DASHBOARD_ORIGIN = "DASHBOARD_ORIGIN"
    GITHUB_TOKEN = "GITHUB_TOKEN_REFRESH"


#: The runner the set-up switches on: the GitHub workflow.
REFRESH_TARGET_GITHUB: Final[str] = "github"
