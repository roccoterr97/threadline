"""Fixed facts about running Threadline on GitHub Actions.

The workflow file reads every setting from the repository's Actions secrets
and variables. Which setting is which is decided here, once: the set-up puts
each value where this module says, and a test checks the workflow file reads
each one from the same place. None of it is a secret or differs between
machines, so it is code rather than configuration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from tracker.shared.config import REPOSITORY_ROOT

#: The workflow's file name. The dashboard's "Refresh now" starts it by this
#: name through GitHub's API, so it must never change.
WORKFLOW_FILE_NAME: Final[str] = "threadline-run.yml"

#: Where the workflow lives in the repository.
WORKFLOW_FILE: Final[Path] = REPOSITORY_ROOT / ".github" / "workflows" / WORKFLOW_FILE_NAME

#: The secret holding the owner's Claude subscription key from ``claude setup-token``.
#: It goes straight into GitHub; Threadline never stores it, not even in ``.env``.
CLAUDE_TOKEN_SECRET: Final[str] = "CLAUDE_CODE_OAUTH_TOKEN"

#: Settings that are neither secret nor personal, kept as Actions *variables*
#: so they stay readable in the run log. Every other setting is a *secret*:
#: GitHub hides a secret's value wherever it would appear in a log.
VARIABLE_SETTINGS: Final[frozenset[str]] = frozenset(
    {
        "LOG_LEVEL",
        "LINKEDIN_TOKEN_EXPIRES_ON",
        "OWNER_TIME_ZONE",
        "OWNER_WEEKEND_DAYS",
        "PRODUCT_NAME",
        "SUMMARY_SUBJECT_PREFIX",
        "MICROSOFT_CLIENT_ID",
        "MICROSOFT_TENANT",
        "MAIL_SOURCES",
        "IMAP_PROVIDER",
        "IMAP_HOST",
        "IMAP_PORT",
        "SUMMARY_DELIVERY",
        "SMTP_HOST",
        "SMTP_PORT",
    }
)

#: Settings the workflow fixes itself instead of reading from the repository.
WORKFLOW_FIXED_SETTINGS: Final[frozenset[str]] = frozenset({"APP_ENV"})

#: Secrets without which the workflow does nothing and finishes green, as in
#: the public template and in a copy that is not set up yet.
REQUIRED_SECRETS: Final[tuple[str, ...]] = (
    CLAUDE_TOKEN_SECRET,
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_ANON_KEY",
    "TOKEN_ENCRYPTION_KEY",
    "OWNER_EMAIL_ADDRESSES",
)

#: The daily time offered when the workflow file holds none yet.
DEFAULT_RUN_TIME: Final[str] = "07:00"

#: The repository page where secrets and variables are added.
ACTIONS_SECRETS_PAGE: Final[str] = "https://github.com/{repository}/settings/secrets/actions"

#: The workflow's page, where "Run workflow" and every run's log are.
WORKFLOW_PAGE: Final[str] = (
    f"https://github.com/{{repository}}/actions/workflows/{WORKFLOW_FILE_NAME}"
)

#: The commit message the set-up offers when the daily time changes.
SCHEDULE_COMMIT_MESSAGE: Final[str] = "Set the daily Threadline time"

#: The name offered for the owner's private copy when the set-up creates it.
DEFAULT_COPY_NAME: Final[str] = "threadline"

#: The git remote holding the owner's own copy on GitHub.
COPY_REMOTE: Final[str] = "origin"

#: What an existing ``origin`` that is not the owner's copy is renamed to before
#: the copy takes that name. The GitHub CLI prefers ``origin`` over it.
TEMPLATE_REMOTE: Final[str] = "template"

#: GitHub's REST API and the version Threadline speaks.
GITHUB_API_URL: Final[str] = "https://api.github.com"
GITHUB_API_VERSION: Final[str] = "2022-11-28"

#: The workflow as GitHub's API describes it; reading it starts nothing.
WORKFLOW_API_PATH: Final[str] = f"/repos/{{repository}}/actions/workflows/{WORKFLOW_FILE_NAME}"

#: A workflow's state when it runs on schedule and on request.
WORKFLOW_ACTIVE_STATE: Final[str] = "active"

#: GitHub's page for a new fine-grained token. GitHub fills the form from these
#: documented parameters; which repositories it may use cannot be pre-filled.
FINE_GRAINED_TOKEN_PAGE: Final[str] = "https://github.com/settings/personal-access-tokens/new"

#: What the "Refresh now" token is called on that page.
REFRESH_TOKEN_NAME: Final[str] = "Threadline refresh now"
REFRESH_TOKEN_DESCRIPTION: Final[str] = (
    "Lets the dashboard's Refresh now button start the Threadline workflow."
)

#: Days the "Refresh now" token lasts (GitHub allows 1 to 366).
REFRESH_TOKEN_DAYS: Final[int] = 365

#: The one permission it needs: start and read workflow runs.
REFRESH_TOKEN_PERMISSIONS: Final[dict[str, str]] = {"actions": "write"}
