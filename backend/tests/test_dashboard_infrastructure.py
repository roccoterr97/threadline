"""What the dashboard step stands on: download, page check, local build, release workflow."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

import httpx
import pytest
import yaml

from tracker.infrastructure.local_dashboard_build import LocalDashboardBuild, read_site
from tracker.infrastructure.web_download import WebDownload
from tracker.infrastructure.web_probe import WebPage, WebProbe
from tracker.shared.config import REPOSITORY_ROOT
from tracker.shared.constants.dashboard import (
    ARCHIVE_NAME,
    CHECKSUM_NAME,
    LOCAL_BUILD_ENVIRONMENT,
    RELEASE_ASSET_URL,
    RELEASE_TAG,
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

    assert await probe.page_of("https://a.netlify.example") == WebPage(200, is_html)


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


def test_a_built_site_holding_a_link_is_refused(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<!doctype html>")
    (tmp_path / "secret.txt").symlink_to(tmp_path / "index.html")

    with pytest.raises(DashboardPackageError, match="link"):
        read_site(tmp_path)


# --- The release workflow ----------------------------------------------------------

RELEASE_WORKFLOW: Final[Path] = REPOSITORY_ROOT / ".github" / "workflows" / "dashboard-release.yml"


def test_the_release_workflow_publishes_the_files_the_set_up_downloads() -> None:
    workflow: dict[Any, Any] = yaml.safe_load(RELEASE_WORKFLOW.read_text(encoding="utf-8"))
    job = workflow["jobs"]["release"]
    publish = next(step for step in job["steps"] if step.get("name") == "Publish")["run"]
    pack = next(step for step in job["steps"] if step.get("name") == "Pack")["run"]

    assert job["env"] == {"RELEASE_TAG": RELEASE_TAG, "ARCHIVE": ARCHIVE_NAME}
    assert '"$ARCHIVE" "$ARCHIVE.sha256"' in publish
    assert '"$ARCHIVE.sha256"' in pack
    assert f"{ARCHIVE_NAME}.sha256" == CHECKSUM_NAME
    assert RELEASE_ASSET_URL.startswith(
        f"https://github.com/{TEMPLATE_REPOSITORY}/releases/download/{RELEASE_TAG}/"
    )


def test_the_release_workflow_builds_without_any_supabase_settings() -> None:
    workflow: dict[Any, Any] = yaml.safe_load(RELEASE_WORKFLOW.read_text(encoding="utf-8"))
    build = next(
        step for step in workflow["jobs"]["release"]["steps"] if step.get("name") == "Build"
    )

    assert build["env"] == LOCAL_BUILD_ENVIRONMENT
