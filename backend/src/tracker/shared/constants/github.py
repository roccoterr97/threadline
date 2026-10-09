"""Fixed facts about running Threadline on GitHub Actions.

The workflow file reads every setting from the repository's Actions secrets
and variables. Which setting is which is decided here, once: the set-up puts
each value where this module says, and a test checks the workflow file reads
each one from the same place. None of it is a secret or differs between
machines, so it is code rather than configuration.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Final

from tracker.shared.config import REPOSITORY_ROOT

#: The workflow's file name. The dashboard's "Refresh now" starts it by this
#: name through GitHub's API, so it must never change.
WORKFLOW_FILE_NAME: Final[str] = "threadline-run.yml"

#: The names a copy's default branch usually has, when git was not told which it is.
DEFAULT_BRANCH_NAMES: Final[tuple[str, ...]] = ("main", "master")

#: The command that switches the daily run on GitHub off, as the owner types it.
DISABLE_WORKFLOW_COMMAND: Final[str] = f"gh workflow disable {WORKFLOW_FILE_NAME}"

#: The workflow's title (its ``name:`` line), as GitHub's Actions tab lists it.
WORKFLOW_DISPLAY_NAME: Final[str] = "Threadline run"


class WorkflowMode(StrEnum):
    """The two ways the workflow is started by hand, its ``mode`` input."""

    DAILY = "daily"
    REFRESH = "refresh"


#: The workflow input that carries the mode.
WORKFLOW_MODE_INPUT: Final[str] = "mode"

#: GitHub's API path for whether Actions may run in a repository at all.
ACTIONS_PERMISSIONS_API_PATH: Final[str] = "repos/{repository}/actions/permissions"

#: The policy the set-up asks for when it has to switch Actions on: every
#: action may run, as the guide's by-hand route chooses too.
ALLOWED_ACTIONS_ALL: Final[str] = "all"

#: About how long a daily run takes before the summary e-mail is sent.
FIRST_SUMMARY_MINUTES: Final[int] = 10

#: How long the set-up follows the first run it started, and how often it
#: looks. A key Claude refuses stops the run in its first minute, so two
#: minutes catch that and keep the set-up waiting no longer.
FIRST_RUN_WATCH_SECONDS: Final[int] = 120
FIRST_RUN_POLL_SECONDS: Final[int] = 10

#: The title GitHub shows on a daily run, set by the workflow's ``run-name``.
#: The first run is found by it, so a refresh is never taken for it.
DAILY_RUN_TITLE: Final[str] = "Threadline daily run"

#: How far this computer's clock may be off GitHub's when the first run is
#: told apart from runs started before it.
FIRST_RUN_CLOCK_SKEW_SECONDS: Final[int] = 60

#: How many of the newest runs started with 'Run workflow' are read when
#: looking for the first run; others may start next to it.
RECENT_RUNS_LIMIT: Final[int] = 20

#: The event of a run started with 'Run workflow', by hand or by the set-up.
RUN_EVENT_BY_HAND: Final[str] = "workflow_dispatch"

#: A run's status once it has ended, and the conclusion of one that ended well.
RUN_STATUS_COMPLETED: Final[str] = "completed"
RUN_CONCLUSION_SUCCESS: Final[str] = "success"

#: GitHub's API path for the notes one job of a run left (errors, warnings).
JOB_ANNOTATIONS_API_PATH: Final[str] = "repos/{repository}/check-runs/{job}/annotations"

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

#: Where the GitHub command-line tool is explained and downloaded, for every system.
GITHUB_CLI_PAGE: Final[str] = "https://cli.github.com"

#: What git prints, in some line, when it has no name and address to put on a commit.
GIT_IDENTITY_MARKERS: Final[tuple[str, ...]] = (
    "Author identity unknown",
    "Please tell me who you are",
    "unable to auto-detect email address",
)

#: How git words a push that GitHub refuses because the sign-in lacks the
#: ``workflow`` permission, for an OAuth app or a personal access token alike.
GIT_WORKFLOW_SCOPE_REFUSAL: Final[str] = (
    r"refusing to allow .{1,60}? to create or update workflow .*?without .?workflow.? scope"
)

#: What the owner is told then: how to add the permission, and what to do after.
GIT_WORKFLOW_SCOPE_MESSAGE: Final[str] = (
    "GitHub refused the change because your sign-in may not change workflow files. "
    "Run: gh auth refresh -h github.com -s workflow, then run this step again."
)

#: The two lines that give git a name and an address, as the owner types them.
GIT_SET_NAME_COMMAND: Final[str] = 'git config --global user.name "Your Name"'
GIT_SET_EMAIL_COMMAND: Final[str] = 'git config --global user.email "you@example.com"'

#: The lines git starts with when it says what went wrong; the first of these is shown.
GIT_ERROR_PREFIXES: Final[tuple[str, ...]] = ("fatal:", "error:")

#: Longest stretch of what git said that is shown to the owner.
GIT_SAID_MAX_CHARACTERS: Final[int] = 200

#: The oldest GitHub CLI the set-up works with, as (major, minor): before it
#: ``gh attestation verify`` has no ``--source-ref`` (added in 2.68.0, March
#: 2025), which the dashboard check needs. ``install.sh`` and ``install.ps1``
#: repeat this number; a test keeps the three equal.
GITHUB_CLI_MINIMUM_VERSION: Final[tuple[int, int]] = (2, 68)

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
