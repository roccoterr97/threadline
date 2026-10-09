"""What the dashboard step stands on: download, page check, local build, release workflow."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

import httpx
import pytest
import yaml

from tracker.infrastructure.github_cli import GitHubCli
from tracker.infrastructure.local_dashboard_build import LocalDashboardBuild, read_site, run_program
from tracker.infrastructure.web_download import WebDownload
from tracker.infrastructure.web_probe import WebPage, WebProbe
from tracker.shared.config import REPOSITORY_ROOT
from tracker.shared.constants.dashboard import (
    ARCHIVE_NAME,
    CHECKSUM_NAME,
    LOCAL_BUILD_ENVIRONMENT,
    RELEASE_ASSET_URL,
    RELEASE_TAG,
    RELEASE_WORKFLOW_PATH,
    SIGNER_WORKFLOW,
    TEMPLATE_REPOSITORY,
)
from tracker.shared.constants.retry import SOURCE_REQUEST_ATTEMPTS
from tracker.shared.errors import (
    DashboardBuildError,
    DashboardPackageError,
    DownloadTooLargeError,
    SourceRequestRejectedError,
    SourceUnavailableError,
)

ASSET: Final[str] = "https://github.com/someone/threadline/releases/download/latest/dashboard.zip"
STORAGE: Final[str] = "https://objects.storage.example/dashboard.zip"


def _client(answer: Any) -> httpx.AsyncClient:  # noqa: ANN401 - a request handler
    return httpx.AsyncClient(transport=httpx.MockTransport(answer))


async def _no_wait(_seconds: float) -> None:
    return None


# --- Download -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_download_follows_github_s_redirect_to_its_storage() -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        if str(request.url) == ASSET:
            return httpx.Response(302, headers={"Location": STORAGE})
        return httpx.Response(200, content=b"zip bytes")

    assert await WebDownload(_client(answer)).fetch(ASSET, 100) == b"zip bytes"


@pytest.mark.asyncio
async def test_a_download_past_its_limit_is_stopped() -> None:
    download = WebDownload(_client(lambda _: httpx.Response(200, content=b"x" * 101)))

    with pytest.raises(DownloadTooLargeError, match="larger than 100 bytes"):
        await download.fetch(ASSET, 100)


@pytest.mark.asyncio
async def test_a_missing_file_names_the_address() -> None:
    download = WebDownload(_client(lambda _: httpx.Response(404)))

    with pytest.raises(SourceRequestRejectedError, match="dashboard.zip answered status 404"):
        await download.fetch(ASSET, 100)


@pytest.mark.asyncio
async def test_a_busy_server_is_asked_again() -> None:
    answers = [httpx.Response(503), httpx.Response(200, content=b"ok")]
    waits: list[float] = []

    async def wait(seconds: float) -> None:
        waits.append(seconds)

    download = WebDownload(_client(lambda _: answers.pop(0)), sleep=wait)

    assert await download.fetch(ASSET, 100) == b"ok"
    assert len(waits) == 1


@pytest.mark.asyncio
async def test_a_connection_that_keeps_failing_gives_up_cleanly() -> None:
    calls: list[str] = []

    def refuse(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        raise httpx.ConnectError("no route", request=request)

    download = WebDownload(_client(refuse), sleep=_no_wait)

    with pytest.raises(SourceUnavailableError, match="could not be downloaded"):
        await download.fetch(ASSET, 100)
    assert len(calls) == SOURCE_REQUEST_ATTEMPTS


# --- The page check ---------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content_type", "is_html"),
    [("text/html; charset=UTF-8", True), ("TEXT/HTML", True), ("text/plain", False), ("", False)],
)
async def test_the_page_check_tells_a_web_page_from_anything_else(
    content_type: str, is_html: bool
) -> None:
    headers = {"Content-Type": content_type} if content_type else {}
    probe = WebProbe(_client(lambda _: httpx.Response(200, headers=headers, content=b"<p>")))

    page = await probe.page_of("https://a.netlify.example")

    assert (page.status, page.is_html, page.address) == (200, is_html, "https://a.netlify.example")


@pytest.mark.asyncio
async def test_the_page_check_tells_where_a_redirect_ended() -> None:
    site = "https://threadline-abc123.netlify.app"
    login = "https://app.netlify.com/edge-access?domain=threadline-abc123.netlify.app"

    def answer(request: httpx.Request) -> httpx.Response:
        if str(request.url) == site:
            return httpx.Response(302, headers={"Location": login})
        return httpx.Response(401, headers={"Content-Type": "text/html"}, content=b"<p>")

    http = httpx.AsyncClient(transport=httpx.MockTransport(answer), follow_redirects=True)

    assert await WebProbe(http).page_of(site) == WebPage(401, is_html=True, address=login)


# --- The local build --------------------------------------------------------------


class FakeRunner:
    """Answers each program from a table; records what ran."""

    def __init__(self, answers: Mapping[str, tuple[int, str]], dist: Path | None = None) -> None:
        self.answers = answers
        self.dist = dist
        self.ran: list[tuple[tuple[str, ...], dict[str, str]]] = []

    def __call__(
        self, arguments: Sequence[str], cwd: Path, extra_env: Mapping[str, str], timeout: float
    ) -> tuple[int, str]:
        self.ran.append((tuple(arguments), dict(extra_env)))
        if tuple(arguments) == ("npm", "run", "build") and self.dist is not None:
            (self.dist / "assets").mkdir(parents=True)
            (self.dist / "index.html").write_text("<!doctype html>")
            (self.dist / "assets" / "index.js").write_text("run()")
        return self.answers.get(" ".join(arguments), (0, ""))


def _frontend(tmp_path: Path) -> Path:
    for name in ("package.json", "package-lock.json"):
        (tmp_path / name).write_text("{}")
    return tmp_path


def _found(name: str) -> str | None:
    return f"/usr/bin/{name}"


@pytest.mark.parametrize(
    ("version", "usable"),
    [("v22.3.0\n", True), ("v26.7.0", True), ("v20.11.1", False), ("", False)],
)
def test_the_local_build_needs_node_22_or_newer(tmp_path: Path, version: str, usable: bool) -> None:
    run = FakeRunner({"node --version": (0, version)})

    assert LocalDashboardBuild(_frontend(tmp_path), run, _found).available() is usable


def test_the_local_build_needs_node_and_the_source(tmp_path: Path) -> None:
    run = FakeRunner({"node --version": (0, "v22.0.0")})

    assert not LocalDashboardBuild(_frontend(tmp_path), run, lambda _: None).available()
    assert not LocalDashboardBuild(tmp_path / "absent", run, _found).available()


def test_the_local_build_installs_builds_without_settings_and_reads_the_site(
    tmp_path: Path,
) -> None:
    frontend = _frontend(tmp_path)
    run = FakeRunner({}, dist=frontend / "dist")

    files = LocalDashboardBuild(frontend, run, _found).build()

    assert files == {"assets/index.js": b"run()", "index.html": b"<!doctype html>"}
    assert [arguments for arguments, _ in run.ran] == [("npm", "ci"), ("npm", "run", "build")]
    assert all(env == LOCAL_BUILD_ENVIRONMENT for _, env in run.ran)


def test_installed_dependencies_are_not_installed_again(tmp_path: Path) -> None:
    frontend = _frontend(tmp_path)
    (frontend / "node_modules").mkdir()
    run = FakeRunner({}, dist=frontend / "dist")

    LocalDashboardBuild(frontend, run, _found).build()

    assert [arguments for arguments, _ in run.ran] == [("npm", "run", "build")]


def test_a_failed_build_names_the_command(tmp_path: Path) -> None:
    run = FakeRunner({"npm run build": (1, "")})

    with pytest.raises(DashboardBuildError, match="npm run build"):
        LocalDashboardBuild(_frontend(tmp_path), run, _found).build()


def test_a_program_is_started_by_the_path_the_system_finds_for_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started: list[list[str]] = []

    def fake_run(command: list[str], **_options: object) -> subprocess.CompletedProcess[str]:
        started.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    npm_cmd = r"C:\Program Files\nodejs\npm.cmd"

    status, output = run_program(["npm", "ci"], tmp_path, {}, 1.0, which=lambda _: npm_cmd)

    assert (status, output) == (0, "ok")
    assert started == [[npm_cmd, "ci"]]


def test_a_program_the_system_cannot_find_is_still_tried_by_its_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started: list[list[str]] = []

    def fake_run(command: list[str], **_options: object) -> subprocess.CompletedProcess[str]:
        started.append(command)
        raise FileNotFoundError(command[0])

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert run_program(["npm", "ci"], tmp_path, {}, 1.0, which=lambda _: None) == (1, "")
    assert started == [["npm", "ci"]]


def test_a_built_site_holding_a_link_is_refused(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<!doctype html>")
    (tmp_path / "secret.txt").symlink_to(tmp_path / "index.html")

    with pytest.raises(DashboardPackageError, match="link"):
        read_site(tmp_path)


# --- Provenance with the GitHub CLI --------------------------------------------------

SIGNER = "you/threadline/.github/workflows/dashboard-release.yml"


def test_gh_checks_the_archive_against_the_workflow_that_must_have_built_it() -> None:
    calls: list[list[str]] = []
    held: list[bytes] = []

    def run(arguments: Sequence[str], stdin: str | None) -> tuple[int, str]:
        calls.append(list(arguments))
        held.append(Path(arguments[3]).read_bytes())
        assert stdin is None
        return 0, ""

    cli = GitHubCli(run, which=lambda _: "/usr/bin/gh")

    assert cli.verify_attestation(b"zip bytes", "you/threadline", SIGNER, "refs/heads/main")

    [call] = calls
    assert call[:3] == ["gh", "attestation", "verify"]
    assert call[4:] == [
        "--repo", "you/threadline",
        "--signer-workflow", SIGNER,
        "--source-ref", "refs/heads/main",
        "--deny-self-hosted-runners",
    ]  # fmt: skip
    assert held == [b"zip bytes"]
    assert not Path(call[3]).exists()


def test_gh_that_does_not_confirm_the_attestation_says_so() -> None:
    cli = GitHubCli(lambda _arguments, _stdin: (1, ""), which=lambda _: "/usr/bin/gh")

    assert not cli.verify_attestation(b"zip", "you/threadline", SIGNER, "refs/heads/main")


# --- The release workflow ----------------------------------------------------------

RELEASE_WORKFLOW: Final[Path] = REPOSITORY_ROOT / ".github" / "workflows" / "dashboard-release.yml"
PINNED_ACTION: Final[re.Pattern[str]] = re.compile(r"^\s*-?\s*uses:\s+\S+@[0-9a-f]{40}\s+# v\d")


def _workflow() -> dict[Any, Any]:
    return yaml.safe_load(RELEASE_WORKFLOW.read_text(encoding="utf-8"))


def _step(job: str, name: str) -> dict[str, Any]:
    return next(step for step in _workflow()["jobs"][job]["steps"] if step.get("name") == name)


def test_the_release_workflow_publishes_the_files_the_set_up_downloads() -> None:
    workflow = _workflow()

    assert workflow["env"] == {"RELEASE_TAG": RELEASE_TAG, "ARCHIVE": ARCHIVE_NAME}
    assert '"$ARCHIVE" "$ARCHIVE.sha256"' in _step("publish", "Publish")["run"]
    assert '"$ARCHIVE.sha256"' in _step("publish", "Checksum")["run"]
    assert f"{ARCHIVE_NAME}.sha256" == CHECKSUM_NAME
    assert RELEASE_ASSET_URL.startswith(
        f"https://github.com/{TEMPLATE_REPOSITORY}/releases/download/{RELEASE_TAG}/"
    )


def test_the_release_workflow_builds_without_any_supabase_settings() -> None:
    assert _step("build", "Build")["env"] == LOCAL_BUILD_ENVIRONMENT


def test_the_job_that_installs_npm_packages_can_only_read_and_keeps_no_token() -> None:
    build = _workflow()["jobs"]["build"]
    checkout = build["steps"][0]

    assert build["permissions"] == {"contents": "read"}
    assert checkout["uses"].startswith("actions/checkout@")
    assert checkout["with"]["persist-credentials"] is False


def test_the_build_records_its_commit_and_the_newest_database_file_in_the_zip() -> None:
    steps = _workflow()["jobs"]["build"]["steps"]
    names = [step.get("name") for step in steps]
    record = _step("build", "Record what it was built from")["run"]

    assert names.index("Record what it was built from") < names.index("Pack")
    assert "supabase/migrations" in record
    assert "$GITHUB_SHA" in record
    assert "frontend/dist/build-info.json" in record


def test_the_published_zip_is_signed_with_its_build_provenance() -> None:
    publish = _workflow()["jobs"]["publish"]["steps"]
    names = [step.get("name") or step["uses"].split("@")[0] for step in publish]
    attest = next(step for step in publish if "attest-build-provenance" in step.get("uses", ""))

    assert attest["with"] == {"subject-path": "${{ env.ARCHIVE }}"}
    assert names.index("actions/attest-build-provenance") < names.index("Publish")
    assert f"{TEMPLATE_REPOSITORY}/{RELEASE_WORKFLOW_PATH}" == SIGNER_WORKFLOW
    assert (REPOSITORY_ROOT / RELEASE_WORKFLOW_PATH).is_file()


def test_the_job_that_can_write_never_runs_the_projects_code() -> None:
    publish = _workflow()["jobs"]["publish"]
    text = yaml.safe_dump(publish["steps"])

    assert publish["needs"] == "build"
    assert publish["permissions"] == {
        "contents": "write",
        "id-token": "write",
        "attestations": "write",
    }
    assert "npm" not in text
    assert "actions/checkout" not in text
    assert "setup-node" not in text


def test_every_action_is_pinned_to_a_full_commit() -> None:
    uses = [
        line
        for line in RELEASE_WORKFLOW.read_text(encoding="utf-8").splitlines()
        if "uses:" in line and not line.lstrip().startswith("#")
    ]

    assert uses
    assert all(PINNED_ACTION.match(line) for line in uses), uses
