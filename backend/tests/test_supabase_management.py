"""Supabase's Management API for the project, its keys and its auth settings, mocked."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from pydantic import SecretStr
from structlog.testing import capture_logs

from tracker.domain.supabase import ApiKeyKind, AuthSettings, NewProject
from tracker.infrastructure.supabase_platform import SupabasePlatform
from tracker.shared.constants.retry import SOURCE_REQUEST_ATTEMPTS
from tracker.shared.constants.setup import RegionGroup
from tracker.shared.errors import (
    SourceAuthError,
    SourceRequestRejectedError,
    SourceUnavailableError,
)

pytestmark = pytest.mark.asyncio

API = "https://api.supabase.com/v1"
REF = "abcdefghijklmnopqrst"
TOKEN = SecretStr("sbp_made_up_token")
ORGANIZATIONS = f"{API}/organizations"
PROJECTS = f"{API}/projects"
PROJECT = f"{PROJECTS}/{REF}"
KEYS = f"{PROJECT}/api-keys"
AUTH = f"{PROJECT}/config/auth"


def _project_json(status: str = "COMING_UP") -> dict[str, object]:
    """A project as the Management API describes it, deprecated fields included."""
    return {
        "id": REF,
        "ref": REF,
        "organization_id": "made-up-org",
        "organization_slug": "made-up-org",
        "name": "threadline",
        "region": "eu-central-1",
        "created_at": "2026-10-09T07:00:00Z",
        "status": status,
    }


def _body(route: respx.Route) -> object:
    return json.loads(route.calls.last.request.content)


async def test_organizations_are_read_by_slug_with_the_token() -> None:
    answer = [{"id": "old-id", "slug": "made-up-org", "name": "Made-up organization"}]
    with respx.mock:
        route = respx.get(ORGANIZATIONS).mock(return_value=httpx.Response(200, json=answer))
        async with SupabasePlatform() as platform:
            organizations = await platform.organizations(TOKEN)

    assert [(item.slug, item.name) for item in organizations] == [
        ("made-up-org", "Made-up organization")
    ]
    assert route.calls.last.request.headers["Authorization"] == "Bearer sbp_made_up_token"


async def test_a_refused_token_is_an_auth_error_and_never_logged() -> None:
    with respx.mock, capture_logs() as logs:
        respx.get(ORGANIZATIONS).mock(return_value=httpx.Response(401, json={"message": "no"}))
        async with SupabasePlatform() as platform:
            with pytest.raises(SourceAuthError, match="access token"):
                await platform.organizations(TOKEN)

    assert "sbp_made_up_token" not in repr(logs)


async def test_too_many_requests_is_retried_then_reported_with_supabases_reason() -> None:
    with respx.mock:
        route = respx.get(ORGANIZATIONS).mock(
            return_value=httpx.Response(429, json={"message": "Too many requests"})
        )
        async with SupabasePlatform() as platform:
            with pytest.raises(SourceRequestRejectedError, match="status 429"):
                await platform.organizations(TOKEN)

    assert route.call_count == SOURCE_REQUEST_ATTEMPTS


async def test_an_answer_that_is_not_a_list_is_unexpected() -> None:
    with respx.mock:
        respx.get(PROJECTS).mock(return_value=httpx.Response(200, json={"ref": REF}))
        async with SupabasePlatform() as platform:
            with pytest.raises(SourceUnavailableError, match="unexpected"):
                await platform.projects(TOKEN)


async def test_projects_are_listed_with_their_status() -> None:
    with respx.mock:
        respx.get(PROJECTS).mock(
            return_value=httpx.Response(200, json=[_project_json("ACTIVE_HEALTHY")])
        )
        async with SupabasePlatform() as platform:
            [project] = await platform.projects(TOKEN)

    assert (project.ref, project.organization_slug, project.status) == (
        REF,
        "made-up-org",
        "ACTIVE_HEALTHY",
    )


async def test_a_project_is_created_in_a_smart_region_and_its_password_never_logged() -> None:
    request = NewProject(
        organization_slug="made-up-org",
        name="threadline",
        region=RegionGroup.EMEA,
        database_password=SecretStr("made-up-db-password"),
    )
    with respx.mock, capture_logs() as logs:
        route = respx.post(PROJECTS).mock(return_value=httpx.Response(201, json=_project_json()))
        async with SupabasePlatform() as platform:
            project = await platform.create_project(TOKEN, request)

    assert project.status == "COMING_UP"
    assert _body(route) == {
        "name": "threadline",
        "organization_slug": "made-up-org",
        "db_pass": "made-up-db-password",
        "region_selection": {"type": "smartGroup", "code": "emea"},
    }
    assert route.call_count == 1
    assert "made-up-db-password" not in repr(logs)


async def test_a_refused_project_keeps_supabases_reason() -> None:
    reason = {"message": "The following organization members have reached their maximum limits"}
    with respx.mock:
        route = respx.post(PROJECTS).mock(return_value=httpx.Response(400, json=reason))
        async with SupabasePlatform() as platform:
            with pytest.raises(SourceRequestRejectedError, match="maximum limits"):
                await platform.create_project(
                    TOKEN,
                    NewProject("made-up-org", "threadline", RegionGroup.APAC, SecretStr("p")),
                )

    assert route.call_count == 1


@pytest.mark.parametrize("status", [429, 502])
async def test_creating_a_project_is_never_sent_twice(status: int) -> None:
    with respx.mock:
        route = respx.post(PROJECTS).mock(return_value=httpx.Response(status, json={}))
        async with SupabasePlatform() as platform:
            with pytest.raises(SourceUnavailableError, match=f"status {status}"):
                await platform.create_project(
                    TOKEN,
                    NewProject("made-up-org", "threadline", RegionGroup.EMEA, SecretStr("p")),
                )

    assert route.call_count == 1


async def test_one_project_is_read() -> None:
    with respx.mock:
        respx.get(PROJECT).mock(
            return_value=httpx.Response(200, json=_project_json("ACTIVE_HEALTHY"))
        )
        async with SupabasePlatform() as platform:
            project = await platform.project(TOKEN, REF)

    assert project.status == "ACTIVE_HEALTHY"


async def test_keys_are_read_revealed_and_legacy_ones_left_out() -> None:
    answer = [
        {"name": "anon", "api_key": "eyJ-legacy", "type": "legacy"},
        {"name": "default", "api_key": "sb_publishable_made_up", "type": "publishable"},
        {"name": "default", "api_key": None, "type": "secret"},
    ]
    with respx.mock, capture_logs() as logs:
        route = respx.get(KEYS).mock(return_value=httpx.Response(200, json=answer))
        async with SupabasePlatform() as platform:
            keys = await platform.api_keys(REF, TOKEN)

    assert route.calls.last.request.url.params["reveal"] == "true"
    assert [(key.kind, key.value is not None) for key in keys] == [
        (ApiKeyKind.PUBLISHABLE, True),
        (ApiKeyKind.SECRET, False),
    ]
    assert "sb_publishable_made_up" not in repr(logs)


async def test_a_key_is_created_and_returned() -> None:
    answer = {"name": "threadline_backend", "api_key": "sb_secret_made_up", "type": "secret"}
    with respx.mock, capture_logs() as logs:
        route = respx.post(KEYS).mock(return_value=httpx.Response(201, json=answer))
        async with SupabasePlatform() as platform:
            key = await platform.create_api_key(REF, TOKEN, ApiKeyKind.SECRET, "threadline_backend")

    assert key.get_secret_value() == "sb_secret_made_up"
    assert route.calls.last.request.url.params["reveal"] == "true"
    body = _body(route)
    assert isinstance(body, dict)
    assert (body["type"], body["name"]) == ("secret", "threadline_backend")
    assert "sb_secret_made_up" not in repr(logs)


async def test_a_created_key_that_comes_back_hidden_is_unexpected() -> None:
    answer = {"name": "threadline_backend", "api_key": None, "type": "secret"}
    with respx.mock:
        respx.post(KEYS).mock(return_value=httpx.Response(201, json=answer))
        async with SupabasePlatform() as platform:
            with pytest.raises(SourceUnavailableError, match="unexpected"):
                await platform.create_api_key(REF, TOKEN, ApiKeyKind.SECRET, "threadline_backend")


async def test_auth_settings_send_only_what_is_set() -> None:
    with respx.mock:
        route = respx.patch(AUTH).mock(return_value=httpx.Response(200, json={}))
        async with SupabasePlatform() as platform:
            await platform.configure_auth(REF, TOKEN, AuthSettings(disable_signup=True))

    assert _body(route) == {"disable_signup": True}


async def test_redirect_addresses_go_as_one_comma_separated_list() -> None:
    settings = AuthSettings(
        site_url="https://you.example",
        redirect_urls=("https://you.example/**", "http://localhost:5173/**"),
    )
    with respx.mock:
        route = respx.patch(AUTH).mock(return_value=httpx.Response(200, json={}))
        async with SupabasePlatform() as platform:
            await platform.configure_auth(REF, TOKEN, settings)

    assert _body(route) == {
        "site_url": "https://you.example",
        "uri_allow_list": "https://you.example/**,http://localhost:5173/**",
    }


async def test_empty_auth_settings_send_nothing() -> None:
    with respx.mock:
        route = respx.patch(AUTH).mock(return_value=httpx.Response(200, json={}))
        async with SupabasePlatform() as platform:
            await platform.configure_auth(REF, TOKEN, AuthSettings())

    assert route.call_count == 0


async def test_a_token_that_may_not_change_auth_is_an_auth_error() -> None:
    with respx.mock:
        respx.patch(AUTH).mock(return_value=httpx.Response(403, json={}))
        async with SupabasePlatform() as platform:
            with pytest.raises(SourceAuthError, match="auth settings"):
                await platform.configure_auth(REF, TOKEN, AuthSettings(disable_signup=True))
