"""The set-up's outside connections, with every request mocked."""

from __future__ import annotations

import stat
import webbrowser
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
import respx
from cryptography.fernet import Fernet
from postgrest import APIError
from pydantic import SecretStr
from structlog.testing import capture_logs
from supabase_auth.errors import AuthApiError
from typer.testing import CliRunner

from tests.conftest import FakeSupabaseClient, as_client
from tracker.cli.main import build_cli
from tracker.infrastructure import terminal_io
from tracker.infrastructure.env_file import EnvFile
from tracker.infrastructure.github_api import GitHubApi
from tracker.infrastructure.linkedin.client import LinkedInSnapshotClient
from tracker.infrastructure.local_time_zone import detect_time_zone
from tracker.infrastructure.microsoft.auth import DEVICE_CODE_URL, TOKEN_URL
from tracker.infrastructure.microsoft.connection import MicrosoftAccess, MicrosoftConnection
from tracker.infrastructure.microsoft.probe import CALENDAR_URL, INBOX_URL, GraphProbe
from tracker.infrastructure.supabase_admin import SupabaseAdmin
from tracker.infrastructure.supabase_platform import SupabasePlatform
from tracker.infrastructure.terminal_io import TerminalIO
from tracker.infrastructure.web_probe import WebProbe
from tracker.services.setup import values
from tracker.shared.clock import FixedClock
from tracker.shared.constants.collection import LINKEDIN_SNAPSHOT_URL
from tracker.shared.errors import (
    DatabaseUnavailableError,
    SourceAuthError,
    SourceRequestRejectedError,
    SourceUnavailableError,
    ValidationFailedError,
)

PROJECT = "https://abcdefghijklmnop.supabase.co"
MIGRATIONS = "https://api.supabase.com/v1/projects/abcdefghijklmnop/database/migrations"

# --- The computer's time zone ------------------------------------------------


def test_the_computers_zone_is_read_from_the_localtime_link(tmp_path: Path) -> None:
    zone_file = tmp_path / "usr" / "share" / "zoneinfo" / "Europe" / "Paris"
    zone_file.parent.mkdir(parents=True)
    zone_file.write_bytes(b"TZif")
    link = tmp_path / "localtime"
    link.symlink_to(zone_file)

    assert detect_time_zone(link, {}) == "Europe/Paris"
    assert detect_time_zone(link, {"TZ": "Asia/Tokyo"}) == "Asia/Tokyo"
    assert detect_time_zone(tmp_path / "missing", {"TZ": "nonsense"}) == "UTC"
    assert detect_time_zone(tmp_path / "missing", {"TZ": "asia/tokyo"}) == "Asia/Tokyo"


# --- .env ----------------------------------------------------------------------


def test_a_new_env_file_is_readable_by_its_owner_only(tmp_path: Path) -> None:
    path = tmp_path / ".env"

    EnvFile(path).set("SUPABASE_URL", PROJECT)

    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert EnvFile(path).get("SUPABASE_URL") == PROJECT


def test_setting_a_value_keeps_every_other_line(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("# comment\nA=1\nB=\n\nexport C='3'\n", encoding="utf-8")
    env = EnvFile(path)

    env.set("B", "two")
    env.set("D", "4")

    assert path.read_text(encoding="utf-8") == "# comment\nA=1\nB=two\n\nexport C='3'\nD=4\n"
    assert env.names() == ("A", "B", "C", "D")
    assert env.get("C") == "3"
    assert env.get("MISSING") is None


def test_a_value_on_several_lines_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValidationFailedError):
        EnvFile(tmp_path / ".env").set("A", "one\ntwo")


# --- Typed answers -------------------------------------------------------------


def test_value_checks() -> None:
    assert values.supabase_url("abcdefghijklmnop") == PROJECT
    assert values.project_ref(PROJECT + "/") == "abcdefghijklmnop"
    assert values.email_address(" You@Example.com ") == "you@example.com"
    assert values.web_address("https://you.vercel.app/") == "https://you.vercel.app"
    assert (
        values.merged_addresses("a@example.com", "B@example.com") == "a@example.com,b@example.com"
    )
    assert values.merged_addresses("a@example.com", "a@example.com") == "a@example.com"
    assert values.future_date("2027-01-01", date(2026, 9, 29)) == date(2027, 1, 1)
    with pytest.raises(ValidationFailedError):
        values.email_address("not an address")
    with pytest.raises(ValidationFailedError):
        values.non_empty("  ", "the key")
    with pytest.raises(ValidationFailedError):
        values.linkedin_profile("https://example.com/in/you")


# --- Supabase over HTTPS -------------------------------------------------------


@pytest.mark.asyncio
async def test_signups_are_read_with_the_publishable_key() -> None:
    with respx.mock:
        route = respx.get(f"{PROJECT}/auth/v1/settings").mock(
            return_value=httpx.Response(200, json={"disable_signup": True})
        )
        async with SupabasePlatform() as platform:
            disabled = await platform.signups_disabled(PROJECT, SecretStr("pub"))

    assert disabled
    assert route.calls.last.request.headers["apikey"] == "pub"


@pytest.mark.asyncio
async def test_a_refused_publishable_key_is_an_auth_error() -> None:
    with respx.mock:
        respx.get(f"{PROJECT}/auth/v1/settings").mock(return_value=httpx.Response(401))
        async with SupabasePlatform() as platform:
            with pytest.raises(SourceAuthError, match="publishable key"):
                await platform.signups_disabled(PROJECT, SecretStr("bad"))


@pytest.mark.asyncio
async def test_migrations_are_listed_and_applied_with_the_token() -> None:
    with respx.mock:
        respx.get(MIGRATIONS).mock(
            return_value=httpx.Response(200, json=[{"version": "1", "name": "0001_schema"}])
        )
        apply = respx.post(MIGRATIONS).mock(return_value=httpx.Response(200, json={}))
        async with SupabasePlatform() as platform:
            applied = await platform.applied_migrations("abcdefghijklmnop", SecretStr("t"))
            await platform.apply_migration(
                "abcdefghijklmnop", SecretStr("t"), "0002_x", "select 1;"
            )

    assert applied == frozenset({"0001_schema"})
    request = apply.calls.last.request
    assert request.headers["Authorization"] == "Bearer t"
    assert request.content == b'{"query":"select 1;","name":"0002_x"}'


@pytest.mark.asyncio
async def test_a_failed_migration_is_not_retried() -> None:
    with respx.mock:
        apply = respx.post(MIGRATIONS).mock(return_value=httpx.Response(400, json={}))
        async with SupabasePlatform() as platform:
            with pytest.raises(SourceUnavailableError, match="400"):
                await platform.apply_migration("abcdefghijklmnop", SecretStr("t"), "n", "bad")

    assert apply.call_count == 1


@pytest.mark.asyncio
async def test_a_refused_migration_carries_supabases_reason_but_never_the_token() -> None:
    reason = {"message": "Failed to insert migration: duplicate key value (version)"}
    with respx.mock, capture_logs() as logs:
        respx.post(MIGRATIONS).mock(return_value=httpx.Response(400, json=reason))
        async with SupabasePlatform() as platform:
            with pytest.raises(SourceRequestRejectedError, match="duplicate key") as caught:
                await platform.apply_migration(
                    "abcdefghijklmnop", SecretStr("sbp_secret_token"), "n", "select 1;"
                )

    assert "status 400" in caught.value.message
    assert logs[-1]["detail"] == reason["message"]
    assert "sbp_secret_token" not in repr(logs)


@pytest.mark.asyncio
async def test_a_server_error_without_a_body_is_still_explained() -> None:
    with respx.mock:
        respx.post(MIGRATIONS).mock(return_value=httpx.Response(500, text=""))
        async with SupabasePlatform() as platform:
            with pytest.raises(SourceUnavailableError, match="status 500$"):
                await platform.apply_migration("abcdefghijklmnop", SecretStr("t"), "n", "x")


@pytest.mark.asyncio
async def test_a_refused_token_is_an_auth_error() -> None:
    with respx.mock:
        respx.get(MIGRATIONS).mock(return_value=httpx.Response(401))
        async with SupabasePlatform() as platform:
            with pytest.raises(SourceAuthError, match="access token"):
                await platform.applied_migrations("abcdefghijklmnop", SecretStr("bad"))


FUNCTIONS = "https://api.supabase.com/v1/projects/abcdefghijklmnop/functions/deploy"
SECRETS = "https://api.supabase.com/v1/projects/abcdefghijklmnop/secrets"
WORKFLOW = "https://api.github.com/repos/you/threadline/actions/workflows/threadline-run.yml"


@pytest.mark.asyncio
async def test_function_settings_are_saved_as_one_list() -> None:
    with respx.mock, capture_logs() as logs:
        route = respx.post(SECRETS).mock(return_value=httpx.Response(201))
        async with SupabasePlatform() as platform:
            await platform.set_secrets(
                "abcdefghijklmnop", SecretStr("t"), {"A_NAME": SecretStr("hidden-value")}
            )

    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer t"
    assert request.content == b'[{"name":"A_NAME","value":"hidden-value"}]'
    assert "hidden-value" not in repr(logs)


@pytest.mark.asyncio
async def test_the_function_is_deployed_as_one_multipart_upload() -> None:
    files = {"index.ts": b"import './refresh.ts';", "refresh.ts": b"export {};"}
    with respx.mock:
        route = respx.post(FUNCTIONS).mock(return_value=httpx.Response(201, json={}))
        async with SupabasePlatform() as platform:
            await platform.deploy_function(
                "abcdefghijklmnop", SecretStr("t"), "refresh-now", files, verify_jwt=False
            )

    request = route.calls.last.request
    assert request.url.params["slug"] == "refresh-now"
    assert request.headers["Content-Type"].startswith("multipart/form-data")
    body = request.content.decode()
    assert '{"name": "refresh-now", "entrypoint_path": "index.ts", "verify_jwt": false}' in body
    assert 'name="file"; filename="index.ts"' in body
    assert 'name="file"; filename="refresh.ts"' in body
    assert "export {};" in body


@pytest.mark.asyncio
async def test_a_token_without_the_deploy_permission_is_an_auth_error() -> None:
    with respx.mock:
        respx.post(FUNCTIONS).mock(return_value=httpx.Response(403, json={}))
        async with SupabasePlatform() as platform:
            with pytest.raises(SourceAuthError, match="deploying the function"):
                await platform.deploy_function(
                    "abcdefghijklmnop", SecretStr("t"), "f", {"index.ts": b""}, verify_jwt=False
                )


@pytest.mark.asyncio
async def test_the_workflow_is_read_without_being_started() -> None:
    with respx.mock:
        route = respx.get(WORKFLOW).mock(return_value=httpx.Response(200, json={"state": "active"}))
        state = await GitHubApi().workflow_state("you/threadline", SecretStr("github_pat_x"))

    assert state == "active"
    assert route.calls.last.request.headers["Authorization"] == "Bearer github_pat_x"
    assert route.call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "error", "words"),
    [
        (401, SourceAuthError, "did not accept the token"),
        (403, SourceAuthError, "cannot see the workflow"),
        (404, SourceAuthError, "cannot see the workflow"),
        (500, SourceUnavailableError, "status 500"),
    ],
)
async def test_github_refusals_are_typed(status: int, error: type[Exception], words: str) -> None:
    with respx.mock:
        respx.get(WORKFLOW).mock(return_value=httpx.Response(status, json={}))
        with pytest.raises(error, match=words):
            await GitHubApi().workflow_state("you/threadline", SecretStr("bad"))


@pytest.mark.asyncio
async def test_github_unreachable_is_typed() -> None:
    with respx.mock:
        respx.get(WORKFLOW).mock(side_effect=httpx.ConnectError("down"))
        with pytest.raises(SourceUnavailableError, match="GitHub could not be reached"):
            await GitHubApi().workflow_state("you/threadline", SecretStr("t"))


# --- Supabase with the service key ---------------------------------------------


def _admin_with(error: APIError | None = None) -> tuple[SupabaseAdmin, MagicMock]:
    client = MagicMock()
    query = client.table.return_value.select.return_value.limit.return_value
    if error is not None:
        query.execute.side_effect = error
    return SupabaseAdmin(client), client


def test_a_missing_table_is_reported_as_absent_not_broken() -> None:
    admin, _ = _admin_with(APIError({"code": "PGRST205", "message": "not found"}))

    assert admin.has_columns("app_owner", "user_id") is False


def test_any_other_database_error_is_an_outage() -> None:
    admin, _ = _admin_with(APIError({"code": "57014", "message": "timeout"}))

    with pytest.raises(DatabaseUnavailableError):
        admin.has_columns("app_owner", "user_id")


def test_an_existing_table_is_present() -> None:
    admin, _ = _admin_with()

    assert admin.has_columns("app_owner", "user_id") is True


def _enum_probe_with(error: APIError | None = None) -> SupabaseAdmin:
    client = MagicMock()
    query = client.table.return_value.select.return_value.eq.return_value.limit.return_value
    if error is not None:
        query.execute.side_effect = error
    return SupabaseAdmin(client)


def test_a_column_that_refuses_an_unlisted_value_is_an_enum() -> None:
    admin = _enum_probe_with(APIError({"code": "22P02", "message": "invalid input value"}))

    assert admin.is_enum_column("run_logs", "trigger") is True


def test_a_text_column_that_finds_nothing_is_not_an_enum() -> None:
    assert _enum_probe_with().is_enum_column("run_logs", "trigger") is False


def test_a_missing_table_has_no_enum_column() -> None:
    admin = _enum_probe_with(APIError({"code": "PGRST205", "message": "not found"}))

    assert admin.is_enum_column("run_logs", "trigger") is False


def test_an_outage_during_the_enum_probe_is_typed() -> None:
    admin = _enum_probe_with(APIError({"code": "57014", "message": "timeout"}))

    with pytest.raises(DatabaseUnavailableError):
        admin.is_enum_column("run_logs", "trigger")


def test_owner_is_recorded_once_and_listed() -> None:
    fake = FakeSupabaseClient()
    fake.conflict_columns["app_owner"] = "user_id"
    admin = SupabaseAdmin(as_client(fake))

    admin.add_owner("user-1")
    admin.add_owner("user-1")

    assert admin.owner_ids() == ("user-1",)


def test_an_existing_login_is_found_instead_of_created() -> None:
    client = MagicMock()
    client.auth.admin.create_user.side_effect = AuthApiError("exists", 422, "email_exists")
    client.auth.admin.list_users.return_value = [
        MagicMock(id="other", email="other@example.com"),
        MagicMock(id="mine", email="You@Example.com"),
    ]
    admin = SupabaseAdmin(client)

    assert admin.create_confirmed_user("you@example.com") is None
    assert admin.find_user_id("you@example.com") == "mine"


def test_a_new_login_is_created_confirmed() -> None:
    client = MagicMock()
    client.auth.admin.create_user.return_value.user.id = "new"

    assert SupabaseAdmin(client).create_confirmed_user("you@example.com") == "new"
    client.auth.admin.create_user.assert_called_once_with(
        {"email": "you@example.com", "email_confirm": True}
    )


def test_a_publishable_key_in_place_of_the_secret_one_is_refused() -> None:
    client = MagicMock()
    client.auth.admin.list_users.side_effect = AuthApiError("no", 401, None)

    with pytest.raises(SourceAuthError, match="secret key"):
        SupabaseAdmin(client).check_service_key()


# --- Microsoft -----------------------------------------------------------------


class _Tokens:
    async def access_token(self) -> str:
        return "access"


@pytest.mark.asyncio
async def test_graph_probe_reads_the_calendar_owner() -> None:
    with respx.mock:
        respx.get(CALENDAR_URL).mock(
            return_value=httpx.Response(
                200, json={"id": "c", "owner": {"address": "You@Example.com"}}
            )
        )
        respx.get(INBOX_URL).mock(return_value=httpx.Response(200, json={"id": "i"}))
        async with GraphProbe(_Tokens()) as graph:
            await graph.check_mailbox()
            owner = await graph.calendar_owner()

    assert owner == "you@example.com"


@pytest.mark.asyncio
async def test_graph_probe_refusal_is_an_auth_error() -> None:
    with respx.mock:
        respx.get(INBOX_URL).mock(return_value=httpx.Response(401, json={}))
        async with GraphProbe(_Tokens()) as graph:
            with pytest.raises(SourceAuthError, match="mailbox"):
                await graph.check_mailbox()


@pytest.mark.asyncio
async def test_microsoft_connection_signs_in_and_names_the_account() -> None:
    fake = FakeSupabaseClient()
    fake.conflict_columns["app_secrets"] = "name"
    access = MicrosoftAccess(
        PROJECT, SecretStr("secret"), SecretStr(Fernet.generate_key().decode()), "app", "consumers"
    )
    connection = MicrosoftConnection(lambda url, key: as_client(fake), FixedClock(_NOW))
    shown: list[tuple[str, str]] = []
    with respx.mock:
        respx.post(DEVICE_CODE_URL).mock(return_value=httpx.Response(200, json=_DEVICE_CODE))
        respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=_TOKENS))
        respx.get(CALENDAR_URL).mock(
            return_value=httpx.Response(200, json={"owner": {"address": "you@example.com"}})
        )
        assert not await connection.is_signed_in(access)
        address = await connection.sign_in(access, lambda url, code: shown.append((url, code)))

    assert address == "you@example.com"
    assert shown == [("https://microsoft.example/link", "ABC")]
    assert await connection.is_signed_in(access)


# --- LinkedIn and the dashboard ------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 404])
async def test_linkedin_key_that_answers_is_accepted(status: int) -> None:
    with respx.mock:
        route = respx.get(url__startswith=LINKEDIN_SNAPSHOT_URL).mock(
            return_value=httpx.Response(status, json={"elements": []})
        )
        async with LinkedInSnapshotClient(SecretStr("key")) as client:
            await client.check_access()

    assert route.calls.last.request.headers["Linkedin-Version"] == "202312"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "error", "words"),
    [
        (401, SourceAuthError, "expired"),
        (403, SourceAuthError, "permission"),
        (426, SourceUnavailableError, "426"),
    ],
)
async def test_linkedin_key_refusals(status: int, error: type[Exception], words: str) -> None:
    with respx.mock:
        respx.get(url__startswith=LINKEDIN_SNAPSHOT_URL).mock(
            return_value=httpx.Response(status, json={})
        )
        async with LinkedInSnapshotClient(SecretStr("key")) as client:
            with pytest.raises(error, match=words):
                await client.check_access()


@pytest.mark.asyncio
async def test_web_probe_follows_redirects() -> None:
    with respx.mock:
        respx.get("https://you.vercel.app/login").mock(return_value=httpx.Response(200))
        respx.get("https://you.vercel.app").mock(
            return_value=httpx.Response(307, headers={"Location": "https://you.vercel.app/login"})
        )
        assert await WebProbe().status_of("https://you.vercel.app") == 200


@pytest.mark.asyncio
async def test_web_probe_unreachable_is_typed() -> None:
    with respx.mock:
        respx.get("https://you.vercel.app").mock(side_effect=httpx.ConnectError("down"))
        with pytest.raises(SourceUnavailableError):
            await WebProbe().status_of("https://you.vercel.app")


@pytest.mark.asyncio
async def test_the_function_probe_posts_without_a_sign_in() -> None:
    url = f"{PROJECT}/functions/v1/refresh-now"
    with respx.mock:
        route = respx.post(url).mock(return_value=httpx.Response(401))
        assert await WebProbe().status_of_post(url) == 401

    assert "Authorization" not in route.calls.last.request.headers


@pytest.mark.asyncio
async def test_the_function_probe_unreachable_is_typed() -> None:
    url = f"{PROJECT}/functions/v1/refresh-now"
    with respx.mock:
        respx.post(url).mock(side_effect=httpx.ConnectError("down"))
        with pytest.raises(SourceUnavailableError):
            await WebProbe().status_of_post(url)


# --- The terminal --------------------------------------------------------------


def test_terminal_without_browser_or_clipboard_carries_on(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def no_browser(url: str) -> bool:
        raise webbrowser.Error(url)

    monkeypatch.setattr(terminal_io.webbrowser, "open", no_browser)
    monkeypatch.setattr(terminal_io.shutil, "which", lambda name: None)
    io = TerminalIO()

    io.open_page("https://example.com")

    assert io.copy("value") is False
    assert "open that address yourself" in capsys.readouterr().out


def test_terminal_copies_with_pbcopy(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(terminal_io.shutil, "which", lambda name: "/usr/bin/pbcopy")
    monkeypatch.setattr(terminal_io.subprocess, "run", lambda args, **kwargs: calls.append(kwargs))

    assert TerminalIO().copy("value") is True
    assert calls[0]["input"] == "value"


# --- The commands --------------------------------------------------------------


def test_doctor_without_configuration_exits_one_in_plain_words() -> None:
    result = CliRunner().invoke(build_cli(), ["doctor"])

    assert result.exit_code == 1
    assert "PROBLEM  Configuration: missing or wrong:" in result.output
    assert "Traceback" not in result.output


def test_setup_help_lists_the_steps() -> None:
    result = CliRunner().invoke(build_cli(), ["setup", "--help"])

    assert result.exit_code == 0
    for step in ("supabase", "database", "login", "categories", "microsoft", "linkedin", "cloud"):
        assert step in result.output


_NOW = datetime(2026, 9, 29, 7, 0, tzinfo=UTC)

_DEVICE_CODE = {
    "user_code": "ABC",
    "verification_uri": "https://microsoft.example/link",
    "device_code": "handle",
    "interval": 0,
}

_TOKENS = {"access_token": "access", "refresh_token": "refresh", "expires_in": 3600}
