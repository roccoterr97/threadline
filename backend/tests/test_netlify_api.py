"""Netlify's API client, against a stand-in transport: no network, ever."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from pydantic import SecretStr

from tracker.infrastructure.netlify_api import NetlifyApi, NetlifyDeploy, NetlifySite
from tracker.shared.constants.dashboard import NETLIFY_API_URL
from tracker.shared.errors import (
    SiteNameTakenError,
    SourceAuthError,
    SourceRequestRejectedError,
    SourceUnavailableError,
    ValidationFailedError,
)

pytestmark = pytest.mark.asyncio

TOKEN = SecretStr("nfp_made_up")
SITE_JSON = {
    "id": "3970e0fe-site",
    "name": "threadline-abc123",
    "url": "http://threadline-abc123.netlify.app",
    "ssl_url": "https://threadline-abc123.netlify.app/",
}


def _api(
    answer: Callable[[httpx.Request], httpx.Response], seen: list[httpx.Request]
) -> NetlifyApi:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return answer(request)

    return NetlifyApi(httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def test_the_token_is_checked_with_a_read_of_its_own_account() -> None:
    seen: list[httpx.Request] = []
    api = _api(lambda _: httpx.Response(200, json={"id": "user-1"}), seen)

    await api.check_token(TOKEN)

    [request] = seen
    assert (request.method, str(request.url)) == ("GET", f"{NETLIFY_API_URL}/user")
    assert request.headers["Authorization"] == "Bearer nfp_made_up"
    assert "Threadline" in request.headers["User-Agent"]


@pytest.mark.parametrize("status", [401, 403])
async def test_a_refused_token_is_an_auth_error_that_never_repeats_it(status: int) -> None:
    api = _api(lambda _: httpx.Response(status, json={"message": "Access Denied"}), [])

    with pytest.raises(SourceAuthError, match="did not accept the token") as raised:
        await api.check_token(TOKEN)

    assert "nfp_made_up" not in raised.value.message


async def test_a_site_is_created_by_name_and_read_with_its_https_address() -> None:
    seen: list[httpx.Request] = []
    api = _api(lambda _: httpx.Response(201, json=SITE_JSON), seen)

    site = await api.create_site(TOKEN, "threadline-abc123")

    assert site == NetlifySite(
        id="3970e0fe-site",
        name="threadline-abc123",
        address="https://threadline-abc123.netlify.app",
    )
    assert seen[0].method == "POST"
    assert json.loads(seen[0].content) == {"name": "threadline-abc123"}


async def test_a_site_with_only_a_plain_address_is_given_https() -> None:
    plain = {key: value for key, value in SITE_JSON.items() if key != "ssl_url"}
    api = _api(lambda _: httpx.Response(201, json=plain), [])

    site = await api.create_site(TOKEN, "threadline-abc123")

    assert site.address == "https://threadline-abc123.netlify.app"


async def test_a_site_s_page_in_netlify_is_read_only_when_it_is_on_netlify_s_own_site() -> None:
    admin = {**SITE_JSON, "admin_url": "https://app.netlify.com/projects/threadline-abc123/"}
    elsewhere = {**SITE_JSON, "admin_url": "https://app.netlify.com.example/projects/x"}
    answers = iter([admin, elsewhere])
    api = _api(lambda _: httpx.Response(201, json=next(answers)), [])

    named = await api.create_site(TOKEN, "threadline-abc123")
    unknown = await api.create_site(TOKEN, "threadline-abc123")

    assert named.admin_address == "https://app.netlify.com/projects/threadline-abc123"
    assert unknown.admin_address is None


async def test_a_taken_name_has_its_own_error() -> None:
    answer = {"errors": {"subdomain": ["must be unique"]}}
    api = _api(lambda _: httpx.Response(422, json=answer), [])

    with pytest.raises(SiteNameTakenError, match="threadline-abc123"):
        await api.create_site(TOKEN, "threadline-abc123")


@pytest.mark.parametrize(
    "answer",
    [
        {"errors": {"name": ["has already been taken"]}},
        {"message": "Validation Failed", "errors": {"subdomain": ["must be unique"]}},
    ],
)
async def test_a_refusal_about_the_name_is_a_taken_name(answer: dict[str, object]) -> None:
    api = _api(lambda _: httpx.Response(422, json=answer), [])

    with pytest.raises(SiteNameTakenError):
        await api.create_site(TOKEN, "threadline-abc123")


async def test_another_validation_failure_says_what_netlify_found_wrong() -> None:
    answer = {"message": "Validation Failed", "errors": {"account_slug": ["is not allowed"]}}
    api = _api(lambda _: httpx.Response(422, json=answer), [])

    with pytest.raises(SourceRequestRejectedError, match="account_slug is not allowed") as raised:
        await api.create_site(TOKEN, "threadline-abc123")

    assert not isinstance(raised.value, SiteNameTakenError)


async def test_a_422_with_no_reason_is_not_taken_for_a_name_clash() -> None:
    api = _api(lambda _: httpx.Response(422, text="no"), [])

    with pytest.raises(SourceRequestRejectedError, match="status 422") as raised:
        await api.create_site(TOKEN, "threadline-abc123")

    assert not isinstance(raised.value, SiteNameTakenError)


async def test_a_saved_site_is_found_and_a_gone_one_is_none() -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/sites/3970e0fe-site"):
            return httpx.Response(200, json=SITE_JSON)
        return httpx.Response(404, json={"code": 404, "message": "Not Found"})

    api = _api(answer, [])

    assert (await api.find_site(TOKEN, "3970e0fe-site")) is not None
    assert (await api.find_site(TOKEN, "deleted-site")) is None


@pytest.mark.parametrize(
    "site_id",
    ["../user", "a/b", "a?x=1", "", " ", "site id", "%2e%2e", "-leading-dash", "x" * 64],
)
async def test_a_site_identifier_that_is_not_one_never_reaches_the_address(site_id: str) -> None:
    seen: list[httpx.Request] = []
    api = _api(lambda _: httpx.Response(200, json=SITE_JSON), seen)

    with pytest.raises(ValidationFailedError, match="NETLIFY_SITE_ID"):
        await api.find_site(TOKEN, site_id)
    with pytest.raises(ValidationFailedError, match="NETLIFY_SITE_ID"):
        await api.deploy_zip(TOKEN, site_id, b"zip")

    assert seen == []


@pytest.mark.parametrize("site_id", ["3970e0fe-1c2d-4b5a-9e8f-0123456789ab", "threadline-abc123"])
async def test_a_uuid_or_a_plain_site_name_is_a_site_identifier(site_id: str) -> None:
    seen: list[httpx.Request] = []
    api = _api(lambda _: httpx.Response(200, json=SITE_JSON), seen)

    assert await api.find_site(TOKEN, site_id) is not None
    assert seen[0].url.path.endswith(f"/sites/{site_id}")


async def test_a_zip_is_sent_as_the_raw_body_of_a_new_deploy() -> None:
    seen: list[httpx.Request] = []
    api = _api(lambda _: httpx.Response(200, json={"id": "d-1", "state": "uploaded"}), seen)

    deploy = await api.deploy_zip(TOKEN, "3970e0fe-site", b"PK zip bytes")

    assert deploy == NetlifyDeploy(id="d-1", state="uploaded", error=None)
    [request] = seen
    assert str(request.url) == f"{NETLIFY_API_URL}/sites/3970e0fe-site/deploys"
    assert request.headers["Content-Type"] == "application/zip"
    assert request.content == b"PK zip bytes"


async def test_a_deploy_state_carries_netlify_s_reason_on_one_short_line() -> None:
    answer = {"id": "d-1", "state": "error", "error_message": "Failed\n  to   extract"}
    seen: list[httpx.Request] = []
    api = _api(lambda _: httpx.Response(200, json=answer), seen)

    deploy = await api.deploy_state(TOKEN, "d-1")

    assert deploy == NetlifyDeploy(id="d-1", state="error", error="Failed to extract")
    assert str(seen[0].url) == f"{NETLIFY_API_URL}/deploys/d-1"


async def test_another_refusal_keeps_netlify_s_message() -> None:
    api = _api(lambda _: httpx.Response(400, json={"message": "Bad zip"}), [])

    with pytest.raises(SourceRequestRejectedError, match="Bad zip"):
        await api.deploy_zip(TOKEN, "site", b"zip")


async def test_an_answer_that_is_not_the_expected_json_is_unavailable() -> None:
    api = _api(lambda _: httpx.Response(200, text="<html>"), [])

    with pytest.raises(SourceUnavailableError, match="unexpected"):
        await api.deploy_state(TOKEN, "d-1")


async def test_an_unreachable_netlify_is_one_clean_error() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    api = _api(refuse, [])

    with pytest.raises(SourceUnavailableError, match="could not be reached"):
        await api.create_site(TOKEN, "threadline-abc123")
