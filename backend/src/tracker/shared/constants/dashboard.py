"""Fixed values for publishing the dashboard with ``tracker setup dashboard``.

Where the prebuilt dashboard is downloaded from, the limits it is checked
against, Netlify's addresses and how long a deploy may take. None of it is a
secret or differs between machines, so it is code rather than configuration.
"""

from __future__ import annotations

import string
from pathlib import Path
from typing import Final

from tracker.shared.config import REPOSITORY_ROOT

# --- The prebuilt dashboard ----------------------------------------------------

#: The public template whose GitHub Release holds the prebuilt dashboard. The
#: release workflow (``.github/workflows/dashboard-release.yml``) publishes it there.
TEMPLATE_REPOSITORY: Final[str] = "roccoterr97/threadline"

#: The rolling release the workflow refreshes on every push to ``main``.
RELEASE_TAG: Final[str] = "latest"

#: The built dashboard, zipped, and the file holding its SHA-256.
ARCHIVE_NAME: Final[str] = "dashboard.zip"
CHECKSUM_NAME: Final[str] = f"{ARCHIVE_NAME}.sha256"

#: Where a release's file is downloaded from; GitHub redirects to its storage.
RELEASE_ASSET_URL: Final[str] = (
    f"https://github.com/{TEMPLATE_REPOSITORY}/releases/download/{RELEASE_TAG}/{{name}}"
)

#: Largest download accepted for the archive (the dashboard is about 1 MB).
ARCHIVE_MAX_BYTES: Final[int] = 25 * 1024 * 1024

#: Largest download accepted for the checksum file (one line).
CHECKSUM_MAX_BYTES: Final[int] = 1024

#: Most files the archive may hold, and their largest total once unpacked: a
#: guard against an archive that unpacks into far more than it weighs.
ARCHIVE_MAX_FILES: Final[int] = 500
ARCHIVE_MAX_UNPACKED_BYTES: Final[int] = 100 * 1024 * 1024

#: The page every dashboard must have.
INDEX_FILE: Final[str] = "index.html"

#: The file holding the owner's two public Supabase values, which ``index.html``
#: loads before the dashboard, and the global it sets (``frontend/src/lib/runtimeConfig.ts``).
CONFIG_FILE: Final[str] = "config.js"
CONFIG_GLOBAL: Final[str] = "__THREADLINE_CONFIG__"

#: The fixed date written into every file of the archive the set-up makes, so
#: the same files always make the same archive.
ARCHIVE_TIMESTAMP: Final[tuple[int, int, int, int, int, int]] = (1980, 1, 1, 0, 0, 0)

# --- Building it on this computer instead ---------------------------------------

#: The dashboard's source, present in a full copy of the repository.
FRONTEND_DIRECTORY: Final[Path] = REPOSITORY_ROOT / "frontend"

#: Where ``npm run build`` writes the built dashboard.
FRONTEND_BUILD_DIRECTORY: Final[Path] = FRONTEND_DIRECTORY / "dist"

#: The oldest Node.js major version the dashboard builds with (CONTRIBUTING.md).
NODE_MIN_MAJOR: Final[int] = 22

#: Seconds ``npm ci`` or ``npm run build`` may take.
LOCAL_BUILD_TIMEOUT_SECONDS: Final[float] = 900.0

#: Seconds ``node --version`` may take.
NODE_VERSION_TIMEOUT_SECONDS: Final[float] = 10.0

# --- Netlify -------------------------------------------------------------------

#: Netlify's REST API.
NETLIFY_API_URL: Final[str] = "https://api.netlify.com/api/v1"

#: Where a free Netlify account is made.
NETLIFY_SIGNUP_PAGE: Final[str] = "https://app.netlify.com/signup"

#: Where a personal access token is made (User settings, Applications).
NETLIFY_TOKENS_PAGE: Final[str] = "https://app.netlify.com/user/applications#personal-access-tokens"

#: What the set-up suggests calling the token on that page.
NETLIFY_TOKEN_NAME: Final[str] = "Threadline set-up"

#: Every site gets ``https://<name>.netlify.app``; the set-up's names start like this.
SITE_NAME_PREFIX: Final[str] = "threadline-"
SITE_NAME_SUFFIX_LENGTH: Final[int] = 6
SITE_NAME_ALPHABET: Final[str] = string.ascii_lowercase + string.digits

#: New names tried when Netlify says a name is taken.
SITE_NAME_ATTEMPTS: Final[int] = 5

#: A deploy's state once it is live, and the states that mean it never will be.
DEPLOY_READY_STATE: Final[str] = "ready"
DEPLOY_FAILED_STATES: Final[frozenset[str]] = frozenset({"error", "rejected"})

#: How often the set-up asks whether the deploy is live, and the wait between:
#: about three minutes in all. A zip deploy is usually live in seconds.
DEPLOY_POLL_ATTEMPTS: Final[int] = 60
DEPLOY_POLL_WAIT_SECONDS: Final[float] = 3.0

#: How often the published address is opened before giving up, and the wait between.
SITE_PROBE_ATTEMPTS: Final[int] = 5
SITE_PROBE_WAIT_SECONDS: Final[float] = 3.0

#: The status and media type a working dashboard page answers with.
PAGE_OK_STATUS: Final[int] = 200
HTML_MEDIA_TYPE: Final[str] = "text/html"

#: How the set-up introduces itself to Netlify's API, which asks every caller to.
NETLIFY_USER_AGENT: Final[str] = (
    "Threadline set-up (+https://github.com/" + TEMPLATE_REPOSITORY + ")"
)

#: Settings the local build runs with, so it carries nobody's Supabase project
#: even when ``frontend/.env.local`` names one: the page reads ``config.js``.
LOCAL_BUILD_ENVIRONMENT: Final[dict[str, str]] = {
    "VITE_SUPABASE_URL": "",
    "VITE_SUPABASE_ANON_KEY": "",
    "VITE_DEMO": "false",
}

#: How Supabase's secret keys begin; one must never reach ``config.js``.
SUPABASE_SECRET_KEY_PREFIX: Final[str] = "sb_secret_"
