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

#: Supabase's API server.
SUPABASE_API_URL: Final[str] = "https://api.supabase.com"

#: Supabase's Management API, reached with a personal access token.
SUPABASE_MANAGEMENT_API_URL: Final[str] = f"{SUPABASE_API_URL}/v1"

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

#: Name the set-up suggests for the personal access token, so it is easy to
#: recognise and delete afterwards.
SUPABASE_TOKEN_NAME: Final[str] = "Threadline set-up"

#: The browser sign-in Supabase's own command-line tool uses for ``supabase login``.
#: The page takes ``session_id``, ``token_name`` and ``public_key``; once the
#: person clicks Authorize it shows a short code, and the session address below
#: hands over the new access token, sealed for this computer's key.
SUPABASE_BROWSER_SIGN_IN_PAGE: Final[str] = f"{SUPABASE_DASHBOARD_URL}/cli/login"
SUPABASE_SIGN_IN_SESSION_URL: Final[str] = f"{SUPABASE_API_URL}/platform/cli/login/{{session_id}}"

#: Seconds to wait for the sign-in session's answer, as Supabase's tool does.
SUPABASE_SIGN_IN_TIMEOUT_SECONDS: Final[float] = 10.0

#: Start of the name of the access token a browser sign-in makes; the Unix time
#: follows. Letters, digits and dashes only: the page address is not encoded.
SUPABASE_SIGN_IN_TOKEN_PREFIX: Final[str] = "threadline-setup-"

#: Name offered for a new Supabase project.
SUPABASE_DEFAULT_PROJECT_NAME: Final[str] = "threadline"

#: Bytes of randomness in the generated database password. Threadline never
#: needs the password again, so it is not kept or shown.
DATABASE_PASSWORD_BYTES: Final[int] = 24

#: How often a freshly created project is looked at, and how long between
#: looks. A new project takes one to three minutes to come up; the Management
#: API allows 120 requests a minute per endpoint, so a look every five seconds
#: for five minutes stays far below that.
PROJECT_READY_ATTEMPTS: Final[int] = 60
PROJECT_READY_WAIT_SECONDS: Final[float] = 5.0

#: Status Supabase reports once a project can be used.
PROJECT_HEALTHY_STATUS: Final[str] = "ACTIVE_HEALTHY"

#: Status of a project that was just created and is still being set up.
PROJECT_STARTING_STATUS: Final[str] = "COMING_UP"

#: Statuses of a project that is, or is about to be, usable. A project left
#: behind by a run that stopped after creating it is in one of these.
PROJECT_REUSABLE_STATUSES: Final[frozenset[str]] = frozenset(
    {PROJECT_STARTING_STATUS, PROJECT_HEALTHY_STATUS}
)

#: How a project's status is shown in the list of existing projects.
PROJECT_STATUS_LABELS: Final[dict[str, str]] = {
    PROJECT_HEALTHY_STATUS: "running",
    PROJECT_STARTING_STATUS: "still being set up",
}

#: How often a project that was just created is asked again when it does not
#: answer yet (its address can lag a little behind the "healthy" status), and
#: the seconds between two asks.
NEW_PROJECT_ANSWER_ATTEMPTS: Final[int] = 6
NEW_PROJECT_ANSWER_WAIT_SECONDS: Final[float] = 5.0

#: Status of a paused project. A free project is paused after a week without
#: use and can be restored from its page in the Supabase dashboard.
PROJECT_PAUSED_STATUS: Final[str] = "INACTIVE"

#: Statuses meaning a project will never come up on its own.
PROJECT_FAILED_STATUSES: Final[frozenset[str]] = frozenset(
    {"INIT_FAILED", "REMOVED", "RESTORE_FAILED", "PAUSE_FAILED", PROJECT_PAUSED_STATUS}
)

#: Names of the API keys the set-up creates when a project has none.
PUBLISHABLE_KEY_NAME: Final[str] = "threadline_dashboard"
SECRET_KEY_NAME: Final[str] = "threadline_backend"

#: How a Supabase API key of each kind begins.
PUBLISHABLE_KEY_PREFIX: Final[str] = "sb_publishable_"
SECRET_KEY_PREFIX: Final[str] = "sb_secret_"


class RegionGroup(StrEnum):
    """Supabase's smart region groups: it picks the best data centre in the group."""

    AMERICAS = "americas"
    EMEA = "emea"
    APAC = "apac"


#: What each region group is called when offered.
REGION_GROUP_LABELS: Final[dict[RegionGroup, str]] = {
    RegionGroup.AMERICAS: "The Americas",
    RegionGroup.EMEA: "Europe, the Middle East and Africa",
    RegionGroup.APAC: "Asia and the Pacific",
}

#: The region group offered first for each beginning of a time-zone name.
#: ``UTC`` and anything unrecognised fall back to the Americas, Supabase's
#: largest group.
REGION_GROUP_BY_ZONE_PREFIX: Final[dict[str, RegionGroup]] = {
    "Europe/": RegionGroup.EMEA,
    "Africa/": RegionGroup.EMEA,
    "Atlantic/": RegionGroup.EMEA,
    "Arctic/": RegionGroup.EMEA,
    "Asia/": RegionGroup.APAC,
    "Australia/": RegionGroup.APAC,
    "Pacific/": RegionGroup.APAC,
    "Indian/": RegionGroup.APAC,
    "Antarctica/": RegionGroup.APAC,
}
DEFAULT_REGION_GROUP: Final[RegionGroup] = RegionGroup.AMERICAS

#: How often the auth server's public settings are read after sign-ups were
#: switched off, and how long between reads: the change takes a moment to show.
SIGNUP_CHECK_ATTEMPTS: Final[int] = 5
SIGNUP_CHECK_WAIT_SECONDS: Final[float] = 3.0

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

#: Your applications on LinkedIn's developer portal, where an earlier one is found.
LINKEDIN_DEVELOPER_APPS_PAGE: Final[str] = "https://www.linkedin.com/developers/apps"

#: The form that creates a new application, opened straight away.
LINKEDIN_NEW_APP_PAGE: Final[str] = "https://www.linkedin.com/developers/apps/new"

#: The company page LinkedIn provides for this product, so nobody has to create one,
#: as LinkedIn's list names it. Look-alike pages share most of the name; this
#: one alone carries LinkedIn's own blue logo.
LINKEDIN_DEFAULT_COMPANY: Final[str] = "Member Data Portability (Member-Only Default Company Page)"

#: Threadline's own logo in the owner's copy, for the application's required "App logo".
LINKEDIN_APP_LOGO: Final[Path] = REPOSITORY_ROOT / "website" / "public" / "icons" / "icon-512.png"

#: The product to request on the application's Products tab.
LINKEDIN_PRODUCT: Final[str] = "Member Data Portability API (Member)"

#: How the name of the permission to tick begins. LinkedIn's own pages end it
#: in two different ways, so only the beginning is ever shown.
LINKEDIN_PERMISSION_PREFIX: Final[str] = "r_dma_portability"

#: Every LinkedIn profile address starts with this.
LINKEDIN_PROFILE_PREFIX: Final[str] = "https://www.linkedin.com/in/"

#: The part of the guide that walks through LinkedIn by hand.
LINKEDIN_GUIDE_SECTION: Final[str] = "docs/setup-your-accounts.md, part 8a (LinkedIn)"

# --- Claude cloud ------------------------------------------------------------

#: Where cloud environments and routines are managed.
CLAUDE_CODE_PAGE: Final[str] = "https://claude.ai/code"

#: Host the cloud needs when Outlook is read, besides the default list of
#: package managers (which already covers the Microsoft sign-in host). An IMAP
#: mailbox's server is added from the settings.
CLOUD_OUTLOOK_HOST: Final[str] = "graph.microsoft.com"

#: Host the cloud needs only when LinkedIn is connected.
CLOUD_LINKEDIN_HOST: Final[str] = "api.linkedin.com"

#: Settings that exist on your own computer only and are never copied to the cloud.
LOCAL_ONLY_SETTINGS: Final[frozenset[str]] = frozenset({"APP_ENV", "LOG_LEVEL"})

# --- Refresh now -------------------------------------------------------------

#: The Edge Function behind the dashboard's "Refresh now" button.
REFRESH_FUNCTION_SLUG: Final[str] = "refresh-now"

#: Where its source files are in the repository.
REFRESH_FUNCTION_DIRECTORY: Final[Path] = (
    REPOSITORY_ROOT / "supabase" / "functions" / REFRESH_FUNCTION_SLUG
)

#: The files deployed, the first being the one Supabase starts. ``daily.ts`` is
#: the on-time morning start, which lives in the same function.
REFRESH_FUNCTION_FILES: Final[tuple[str, ...]] = ("index.ts", "refresh.ts", "daily.ts")

#: Where a project serves an Edge Function, below the project address.
FUNCTION_PATH: Final[str] = "/functions/v1/{slug}"

#: What a deployed "Refresh now" answers a caller who is not signed in.
REFRESH_GUARD_STATUSES: Final[frozenset[int]] = frozenset({401, 403})

#: What Supabase answers when no function of that name is deployed.
FUNCTION_MISSING_STATUS: Final[int] = 404

#: The branch the dashboard's refresh runs the workflow on.
REFRESH_BRANCH: Final[str] = "main"


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
    #: The key the database's timer proves itself with (the on-time morning start).
    DAILY_START_KEY = "DAILY_START_KEY"


#: The runner the set-up switches on: the GitHub workflow.
REFRESH_TARGET_GITHUB: Final[str] = "github"

# --- The on-time morning start ------------------------------------------------

#: The function's scheduled path, below its address, which the database's
#: timer calls. ``daily.ts`` and migration 0016 use the same path.
DAILY_START_PATH: Final[str] = "/daily-start"

#: Bytes of randomness in the key the timer sends; it becomes 43 characters,
#: above the 32 the function and the database require.
DAILY_START_KEY_BYTES: Final[int] = 32

#: The database function that saves the address and key in Vault and makes
#: sure the timer exists (migration 0016).
DAILY_START_SAVE_FUNCTION: Final[str] = "save_daily_start_settings"

#: The database function the doctor and the set-up read the state from.
DAILY_START_STATUS_FUNCTION: Final[str] = "daily_start_status"

#: How often the timer looks, in minutes, as said to the owner (migration 0016's job).
DAILY_START_INTERVAL_MINUTES: Final[int] = 15

#: Where the set-up and the doctor point the owner for the on-time morning start.
DAILY_START_GUIDE_SECTION: Final[str] = "docs/refresh-now.md, 'The on-time morning start'"
