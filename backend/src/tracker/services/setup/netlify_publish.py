"""Publishing the dashboard on Netlify: the files, the key, the site, the deploy.

The dashboard comes ready-made from the template's GitHub Release, checked
against its SHA-256 and against the signed build provenance GitHub holds for
it, which names the template's release workflow (or, for a contributor with
Node.js, is built here). Its ``config.js`` holds the project address and the
publishable key, nothing more. The owner pastes a Netlify personal access token, which one harmless
read checks, which stays in memory for this run only and which is never
written to ``.env``. The site is made once, under a random free name, and its
identifier is kept in ``.env`` as ``NETLIFY_SITE_ID`` (not a secret), so
running the step again publishes the newest dashboard to the same address.
"""

from __future__ import annotations

import asyncio
from typing import Final

from pydantic import SecretStr

from tracker.infrastructure.netlify_api import NetlifySite
from tracker.services.setup import values
from tracker.services.setup.context import SetupContext
from tracker.services.setup.dashboard_package import (
    BrowserSettings,
    BuildInfo,
    build_info,
    publishable_archive,
    read_archive,
    verify_checksum,
)
from tracker.services.setup.models import StepName
from tracker.shared.constants.dashboard import (
    ARCHIVE_MAX_BYTES,
    ARCHIVE_NAME,
    CHECKSUM_MAX_BYTES,
    CHECKSUM_NAME,
    DEPLOY_FAILED_STATES,
    DEPLOY_POLL_ATTEMPTS,
    DEPLOY_POLL_WAIT_SECONDS,
    DEPLOY_READY_STATE,
    GITHUB_CLI_MISSING_FOR_DASHBOARD,
    GITHUB_CLI_SIGNED_OUT_FOR_DASHBOARD,
    NETLIFY_SIGNUP_PAGE,
    NETLIFY_TOKEN_NAME,
    NETLIFY_TOKENS_PAGE,
    PAGE_OK_STATUS,
    PROVENANCE_SOURCE_REF,
    RELEASE_ASSET_URL,
    SIGNER_WORKFLOW,
    SITE_NAME_ATTEMPTS,
    SITE_NAME_PREFIX,
    SITE_PROBE_ATTEMPTS,
    SITE_PROBE_WAIT_SECONDS,
    TEMPLATE_REPOSITORY,
)
from tracker.shared.errors import (
    DashboardDeployError,
    DashboardProvenanceError,
    SiteNameTakenError,
    ValidationFailedError,
)
from tracker.shared.logging import get_logger

#: The ``.env`` setting naming the Netlify site; an identifier, not a secret.
SITE_ID: Final[str] = "NETLIFY_SITE_ID"

_SUPABASE_URL: Final[str] = "SUPABASE_URL"
_PUBLISHABLE_KEY: Final[str] = "SUPABASE_ANON_KEY"
_SECRET_KEY: Final[str] = "SUPABASE_SERVICE_ROLE_KEY"

_SECONDS_PER_MINUTE: Final[int] = 60

_log = get_logger(__name__)


async def publish_on_netlify(ctx: SetupContext) -> str:
    """Publish the dashboard, or its newest version, and return its address.

    Args:
        ctx: The conversation, the ``.env`` file and the services.

    Returns:
        The live address, ``https://<name>.netlify.app``.

    Raises:
        TrackerError: If a step of it failed; the message says which.
    """
    archive = await _prepared_archive(ctx)
    token = await _netlify_token(ctx)
    site = await _site(ctx, token)
    await _deploy(ctx, token, site, archive)
    await _check_live(ctx, site.address)
    return site.address


async def _prepared_archive(ctx: SetupContext) -> bytes:
    """The dashboard's files with their ``config.js``, zipped for Netlify."""
    settings = _browser_settings(ctx)
    builder = ctx.gateways.local_build
    if builder.available() and ctx.io.confirm(
        "Node.js is installed and this folder has the dashboard's source. Build it here "
        "instead of downloading the ready-made one? (Only for testing your own changes.)",
        default=False,
    ):
        files = await _built_files(ctx)
    else:
        files = await _downloaded_or_built_files(ctx)
    archive = publishable_archive(files, settings)
    ctx.io.say("The dashboard is ready, with your project's address and its public key.")
    return archive


async def _built_files(ctx: SetupContext) -> dict[str, bytes]:
    """Build the dashboard on this computer with Node.js."""
    ctx.io.say("Building the dashboard here (a few minutes the first time)...")
    return await asyncio.to_thread(ctx.gateways.local_build.build)


async def _downloaded_or_built_files(ctx: SetupContext) -> dict[str, bytes]:
    """Download the ready-made dashboard; when its origin is unproven, offer to build it.

    Raises:
        DashboardProvenanceError: If GitHub cannot confirm who built the download
            and the owner cannot or will not build it here.
    """
    try:
        return await _downloaded_files(ctx)
    except DashboardProvenanceError as error:
        if not ctx.gateways.local_build.available():
            raise
        ctx.io.say(error.message)
        if not ctx.io.confirm(
            "Build the dashboard here with Node.js instead (nothing is downloaded)?",
            default=True,
        ):
            raise
        return await _built_files(ctx)


def _browser_settings(ctx: SetupContext) -> BrowserSettings:
    """The two public values ``config.js`` carries, refusing the secret key."""
    url = ctx.require(_SUPABASE_URL, StepName.SUPABASE)
    key = ctx.require(_PUBLISHABLE_KEY, StepName.SUPABASE)
    if key == ctx.env.get(_SECRET_KEY):
        message = (
            f"{_PUBLISHABLE_KEY} holds the secret key - run "
            f"'uv run tracker setup {StepName.SUPABASE}' and give the publishable key"
        )
        raise ValidationFailedError(message)
    return BrowserSettings(supabase_url=url, publishable_key=key)


async def _downloaded_files(ctx: SetupContext) -> dict[str, bytes]:
    """Download the ready-made dashboard, check it, and read its files."""
    ctx.io.say("Downloading the ready-made dashboard from GitHub...")
    download = ctx.gateways.download
    archive = await download(RELEASE_ASSET_URL.format(name=ARCHIVE_NAME), ARCHIVE_MAX_BYTES)
    checksum = await download(RELEASE_ASSET_URL.format(name=CHECKSUM_NAME), CHECKSUM_MAX_BYTES)
    verify_checksum(archive, checksum)
    await _verify_provenance(ctx, archive)
    files = read_archive(archive)
    _warn_if_database_is_older(ctx, build_info(files))
    _log.info("dashboard_downloaded", files=len(files), size=len(archive))
    return files


def _warn_if_database_is_older(ctx: SetupContext, built: BuildInfo | None) -> None:
    """Say so when the dashboard was built for database files this copy does not have yet.

    The release is rolling, so it can be newer than the owner's copy of
    Threadline. That is not an error: it is shown so the owner updates first.
    """
    own = [file.name for file in ctx.gateways.migrations]
    if built is None or not own or built.latest_migration in own:
        return
    if built.latest_migration < max(own):
        return
    ctx.io.say(
        f"Heads up: this dashboard expects a newer database than your copy of Threadline "
        f"knows (it needs {built.latest_migration}; your copy has up to {max(own)})."
    )
    ctx.io.say(
        "Better to update your copy of Threadline first (bring in the template's newest "
        f"files), then run 'uv run tracker setup {StepName.DATABASE}' and this step again."
    )


async def _verify_provenance(ctx: SetupContext, archive: bytes) -> None:
    """Ask GitHub to confirm the template's release workflow built exactly these bytes.

    Raises:
        DashboardProvenanceError: If the GitHub CLI cannot confirm it.
    """
    github = ctx.gateways.github
    if not github.installed():
        raise DashboardProvenanceError(GITHUB_CLI_MISSING_FOR_DASHBOARD)
    if not github.ready():
        raise DashboardProvenanceError(GITHUB_CLI_SIGNED_OUT_FOR_DASHBOARD)
    confirmed = await asyncio.to_thread(
        github.verify_attestation,
        archive,
        TEMPLATE_REPOSITORY,
        SIGNER_WORKFLOW,
        PROVENANCE_SOURCE_REF,
    )
    if not confirmed:
        message = (
            "GitHub could not confirm that the dashboard was built by Threadline's own "
            "release workflow, so it was not published. Try again in a minute; if you have "
            "Node.js 22 or newer, you can build the dashboard on this computer instead."
        )
        raise DashboardProvenanceError(message)
    ctx.io.say("Checked who built it: GitHub confirms Threadline's release workflow made it.")


async def _netlify_token(ctx: SetupContext) -> SecretStr:
    """Open Netlify's pages and take a token once Netlify accepts it."""
    io = ctx.io
    io.say("Next, a key from Netlify, used for this step only and never saved.")
    if not io.confirm("Do you already have a Netlify account?", default=True):
        io.say("On the page that opens, sign up for free (signing up with GitHub is quickest).")
        io.open_page(NETLIFY_SIGNUP_PAGE)
        io.pause("Once you are signed in to Netlify")
    io.say("On the Netlify page that opens (sign in if asked):")
    io.say("  1. Click 'New access token'.")
    io.say(f"  2. Name it '{NETLIFY_TOKEN_NAME}' and choose the shortest expiry offered.")
    io.say("  3. Click 'Generate token', then copy the token.")
    io.open_page(NETLIFY_TOKENS_PAGE)
    token = await ctx.ask_until_accepted(
        lambda: io.ask_secret("Paste the Netlify token (it stays hidden)"),
        lambda raw: _accepted_token(ctx, raw),
    )
    io.say("Netlify accepted the token.")
    return token


async def _accepted_token(ctx: SetupContext, raw: str) -> SecretStr:
    """Check the token with one read that changes nothing."""
    token = SecretStr(values.non_empty("".join(raw.split()), "the Netlify token"))
    await ctx.gateways.netlify.check_token(token)
    return token


async def _site(ctx: SetupContext, token: SecretStr) -> NetlifySite:
    """The site saved in ``.env``, or a new one saved there."""
    saved = ctx.env.get(SITE_ID)
    if saved is not None:
        site = await ctx.gateways.netlify.find_site(token, saved)
        if site is not None:
            ctx.io.say(f"Publishing the newest dashboard to your site, {site.address}.")
            return site
        ctx.io.say("The Netlify site saved in .env no longer exists for this account.")
        ctx.io.say("A new one is made instead.")
    site = await _new_site(ctx, token)
    # Kept even when the deploy below fails, so running the step again reuses it.
    ctx.env.set(SITE_ID, site.id)
    ctx.io.say(f"Saved {SITE_ID} in .env (it only names the site; it is not a secret).")
    return site


async def _new_site(ctx: SetupContext, token: SecretStr) -> NetlifySite:
    """Create a site under a random name, trying another when one is taken."""
    for _ in range(SITE_NAME_ATTEMPTS):
        name = SITE_NAME_PREFIX + ctx.gateways.site_name_suffix()
        try:
            site = await ctx.gateways.netlify.create_site(token, name)
        except SiteNameTakenError:
            continue
        ctx.io.say(f"Created your Netlify site: {site.address}")
        return site
    message = (
        f"Netlify said {SITE_NAME_ATTEMPTS} new names in a row were taken - run the step again"
    )
    raise DashboardDeployError(message)


async def _deploy(ctx: SetupContext, token: SecretStr, site: NetlifySite, archive: bytes) -> None:
    """Upload the zip and wait until Netlify says the new version is live."""
    netlify = ctx.gateways.netlify
    ctx.io.say("Uploading the dashboard to Netlify...")
    deploy = await netlify.deploy_zip(token, site.id, archive)
    for attempt in range(1, DEPLOY_POLL_ATTEMPTS + 1):
        if deploy.state == DEPLOY_READY_STATE:
            ctx.io.say("Netlify has published it.")
            return
        if deploy.state in DEPLOY_FAILED_STATES:
            _log.error("netlify_deploy_failed", deploy_id=deploy.id, state=deploy.state)
            message = f"Netlify could not publish it ({deploy.error or deploy.state})"
            raise DashboardDeployError(message)
        if attempt == DEPLOY_POLL_ATTEMPTS:
            break
        await ctx.gateways.sleep(DEPLOY_POLL_WAIT_SECONDS)
        deploy = await netlify.deploy_state(token, deploy.id)
    _log.error("netlify_deploy_not_ready", deploy_id=deploy.id, state=deploy.state)
    message = (
        f"Netlify had not finished publishing after {_minutes()} minutes (it says "
        f"'{deploy.state}') - run 'uv run tracker setup {StepName.DASHBOARD}' again"
    )
    raise DashboardDeployError(message)


def _minutes() -> int:
    """How many whole minutes the deploy is waited for."""
    return max(1, round(DEPLOY_POLL_ATTEMPTS * DEPLOY_POLL_WAIT_SECONDS / _SECONDS_PER_MINUTE))


async def _check_live(ctx: SetupContext, address: str) -> None:
    """Open the address until it shows a web page, as the dashboard does."""
    status = 0
    for attempt in range(1, SITE_PROBE_ATTEMPTS + 1):
        page = await ctx.gateways.page_of(address)
        status = page.status
        if status == PAGE_OK_STATUS and page.is_html:
            ctx.io.say(f"Check: {address} opens the dashboard.")
            return
        if attempt < SITE_PROBE_ATTEMPTS:
            await ctx.gateways.sleep(SITE_PROBE_WAIT_SECONDS)
    message = (
        f"{address} answered status {status} instead of the dashboard - open it in a "
        f"minute, then run 'uv run tracker setup {StepName.DASHBOARD}' again"
    )
    raise DashboardDeployError(message)
