"""Step: switch on the dashboard's "Refresh now" button, end to end.

The button asks the ``refresh-now`` Edge Function in the owner's Supabase
project to start the GitHub workflow once more. This step puts that function
in place with no extra program installed: GitHub's token page opens already
filled in, a harmless read proves the token can see the workflow (nothing is
started), and Supabase's Management API saves the function's settings and
deploys it from this repository's files, with the same Supabase access token
as the rest of the run. Both tokens are pasted hidden, kept in memory for this
run only, and never written to ``.env``. Then the function
is called without a sign-in: a deployed one refuses that, which shows it is
there and guarding.

Last, the same step switches on the on-time morning start
(``daily_start.py``): a fresh key for the database's timer goes into the
function's settings and, with the service key, into the database's Vault.
"""

from __future__ import annotations

from urllib.parse import urlencode, urlsplit

from pydantic import SecretStr

from tracker.services.setup import values
from tracker.services.setup.context import SetupContext
from tracker.services.setup.daily_start import daily_start_ready, switch_on_daily_start
from tracker.services.setup.github_copy import LinkedCopy, linked_copy
from tracker.services.setup.models import StepName
from tracker.services.setup.supabase_session import full_access_needed, require_supabase_token
from tracker.shared.constants.github import (
    FINE_GRAINED_TOKEN_PAGE,
    REFRESH_TOKEN_DAYS,
    REFRESH_TOKEN_DESCRIPTION,
    REFRESH_TOKEN_NAME,
    REFRESH_TOKEN_PERMISSIONS,
    WORKFLOW_ACTIVE_STATE,
    WORKFLOW_PAGE,
)
from tracker.shared.constants.setup import (
    FUNCTION_PATH,
    REFRESH_BRANCH,
    REFRESH_FUNCTION_SLUG,
    REFRESH_FUNCTION_VERIFY_JWT,
    REFRESH_GUARD_STATUSES,
    REFRESH_PROBE_ATTEMPTS,
    REFRESH_PROBE_WAIT_SECONDS,
    REFRESH_TARGET_GITHUB,
    RefreshSetting,
)
from tracker.shared.errors import SourceUnavailableError, ValidationFailedError

_SUPABASE_URL = "SUPABASE_URL"
_DASHBOARD_URL = "DASHBOARD_BASE_URL"


class RefreshStep:
    """Deploys the "Refresh now" function with its settings, then checks it answers."""

    name = StepName.REFRESH
    title = "The Refresh now button"

    async def is_done(self, ctx: SetupContext) -> bool:
        """Done when the function refuses a caller with no sign-in and the timer is on."""
        project_url = ctx.env.get(_SUPABASE_URL)
        if project_url is None:
            return False
        try:
            status = await ctx.gateways.status_of_post(function_url(project_url))
        except SourceUnavailableError:
            return False
        return status in REFRESH_GUARD_STATUSES and daily_start_ready(ctx)

    async def run(self, ctx: SetupContext) -> None:
        """Collect both tokens, save the settings, deploy, then check."""
        io = ctx.io
        io.say("The dashboard's Refresh now button starts one extra, quick run whenever you")
        io.say("want. It needs a small helper in your Supabase project, which this step adds.")
        io.say("The same helper also starts your daily run on time: GitHub's own timer is often")
        io.say("hours late.")
        copy = _ready_copy(ctx)
        # A copy that could not be checked is switched on only by a typed yes.
        if copy is None or not io.confirm(
            f"Switch on Refresh now for {copy.name}?", default=copy.confirmed
        ):
            io.say(f"Skipped. To switch it on later: uv run tracker setup {self.name}")
            return
        repository = copy.name
        project_url = ctx.require(_SUPABASE_URL, StepName.SUPABASE)
        daily_key = SecretStr(ctx.gateways.make_daily_start_key())
        github_token = await _github_token(ctx, repository)
        settings = _function_settings(ctx, repository, github_token, daily_key)
        ref = values.project_ref(project_url)
        await _save_and_deploy(ctx, ref, settings)
        await _check_deployed(ctx, project_url)
        switch_on_daily_start(ctx, function_url(project_url), daily_key)


def function_url(project_url: str) -> str:
    """Address of the "Refresh now" function in a project.

    Args:
        project_url: ``https://<project-ref>.supabase.co``.

    Returns:
        The function's address.
    """
    return project_url.rstrip("/") + FUNCTION_PATH.format(slug=REFRESH_FUNCTION_SLUG)


def token_page(repository: str) -> str:
    """GitHub's new-token page, filled in with the name, expiry and permission.

    Args:
        repository: The copy, as ``owner/name``; its owner owns the token.

    Returns:
        The page's address.
    """
    query = {
        "name": REFRESH_TOKEN_NAME,
        "description": REFRESH_TOKEN_DESCRIPTION,
        "target_name": repository.split("/")[0],
        "expires_in": str(REFRESH_TOKEN_DAYS),
        **REFRESH_TOKEN_PERMISSIONS,
    }
    return f"{FINE_GRAINED_TOKEN_PAGE}?{urlencode(query)}"


def _ready_copy(ctx: SetupContext) -> LinkedCopy | None:
    """Name the owner's private copy on GitHub when it and the dashboard both exist.

    The helper's GitHub key and settings go to this repository, so it must
    be the owner's own private copy, checked the same way as in the GitHub
    step; never the public template ``origin`` may still point at.
    """
    if ctx.env.get(_DASHBOARD_URL) is None:
        ctx.io.say(
            "The dashboard's address is not saved yet: publish the dashboard and run "
            f"'uv run tracker setup {StepName.DASHBOARD}' first."
        )
        return None
    copy = linked_copy(ctx)
    if copy is None:
        ctx.io.say(
            "This folder is not linked to your own private copy on GitHub yet: run "
            f"'uv run tracker setup {StepName.GITHUB}' first."
        )
        return None
    if not copy.confirmed:
        ctx.io.say(f"Without the GitHub CLI this cannot check that {copy.name} is your own")
        ctx.io.say("private copy. Answer y below only if it is; the public template never works.")
    return copy


async def _github_token(ctx: SetupContext, repository: str) -> SecretStr:
    """Open GitHub's filled-in token page and take the token once it can see the workflow."""
    io = ctx.io
    io.say("First, a GitHub key that can only start your Threadline workflow.")
    io.say("On the GitHub page that opens (sign in if asked):")
    io.say("  1. The name, expiry date and 'Actions: Read and write' are already filled in.")
    io.say(
        f"  2. Under 'Repository access', choose 'Only select repositories' and pick {repository}."
    )
    io.say("  3. Click 'Generate token' at the bottom, then copy the token (github_pat_...).")
    io.open_page(token_page(repository))
    token, state = await ctx.ask_until_accepted(
        lambda: io.ask_secret("Paste the GitHub token (it stays hidden)"),
        lambda raw: _read_workflow(ctx, repository, raw),
    )
    io.say("GitHub accepted the token: it can see your workflow. Nothing was started.")
    if state != WORKFLOW_ACTIVE_STATE:
        io.say("The workflow is switched off on GitHub, so Refresh now could not start it.")
        page = WORKFLOW_PAGE.format(repository=repository)
        io.say(f"Switch it on with 'Enable workflow' here: {page}")
    return token


async def _read_workflow(ctx: SetupContext, repository: str, raw: str) -> tuple[SecretStr, str]:
    """Check the token with one read that starts nothing."""
    token = SecretStr(values.non_empty("".join(raw.split()), "the GitHub token"))
    return token, await ctx.gateways.github_api.workflow_state(repository, token)


def _function_settings(
    ctx: SetupContext, repository: str, token: SecretStr, daily_key: SecretStr
) -> dict[str, SecretStr]:
    """The function's settings; the GitHub token goes nowhere else."""
    dashboard = urlsplit(ctx.require(_DASHBOARD_URL, StepName.DASHBOARD))
    return {
        RefreshSetting.TARGET: SecretStr(REFRESH_TARGET_GITHUB),
        RefreshSetting.REPOSITORY: SecretStr(repository),
        RefreshSetting.BRANCH: SecretStr(REFRESH_BRANCH),
        RefreshSetting.DASHBOARD_ORIGIN: SecretStr(f"{dashboard.scheme}://{dashboard.netloc}"),
        RefreshSetting.GITHUB_TOKEN: token,
        RefreshSetting.DAILY_START_KEY: daily_key,
    }


async def _save_and_deploy(ctx: SetupContext, ref: str, settings: dict[str, SecretStr]) -> None:
    """Save the settings with this run's Supabase token, then deploy the function."""
    io = ctx.io
    io.say("Next, Supabase saves the helper's settings and puts it in place.")
    token = await require_supabase_token(ctx)
    platform = ctx.gateways.platform
    with full_access_needed(ctx):
        await platform.set_secrets(ref, token, settings)
        io.say(f"Saved the helper's {len(settings)} settings in Supabase.")
        await platform.deploy_function(
            ref,
            token,
            REFRESH_FUNCTION_SLUG,
            ctx.gateways.refresh_function(),
            verify_jwt=REFRESH_FUNCTION_VERIFY_JWT,
        )
    io.say(f"Put the helper '{REFRESH_FUNCTION_SLUG}' in place.")


async def _check_deployed(ctx: SetupContext, project_url: str) -> None:
    """Call the function with no sign-in until it refuses, as a deployed one does.

    Raises:
        ValidationFailedError: If it still does not answer like the helper.
    """
    url = function_url(project_url)
    status = 0
    for attempt in range(1, REFRESH_PROBE_ATTEMPTS + 1):
        status = await ctx.gateways.status_of_post(url)
        if status in REFRESH_GUARD_STATUSES:
            ctx.io.say("Check: the helper answers and turns away callers who are not signed in.")
            ctx.io.say("Refresh now is switched on. Open your dashboard and press Refresh now:")
            ctx.io.say("the line under the header should say 'Refreshing…'.")
            return
        if attempt < REFRESH_PROBE_ATTEMPTS:
            await ctx.gateways.sleep(REFRESH_PROBE_WAIT_SECONDS)
    message = (
        f"the helper answered status {status} instead of asking for a sign-in - "
        f"run 'uv run tracker setup {StepName.REFRESH}' again in a minute"
    )
    raise ValidationFailedError(message)
