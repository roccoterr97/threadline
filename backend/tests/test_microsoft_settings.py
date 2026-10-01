"""The Microsoft application and tenant are settings with safe defaults."""

from __future__ import annotations

import httpx
import pytest
import respx

from tracker.infrastructure.microsoft.auth import MicrosoftAuthenticator, login_urls
from tracker.infrastructure.secret_store import SecretStore
from tracker.repositories import Repositories
from tracker.shared import config
from tracker.shared.clock import FixedClock
from tracker.shared.config import Settings
from tracker.shared.constants.collection import MICROSOFT_CLIENT_ID
from tracker.shared.errors import ConfigurationError


def test_defaults_are_the_public_application_and_personal_accounts(
    settings: Settings,
) -> None:
    assert settings.microsoft_client_id == MICROSOFT_CLIENT_ID
    assert settings.microsoft_tenant == "consumers"


def test_an_empty_value_falls_back_to_the_default(
    valid_environment: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MICROSOFT_TENANT", "  ")
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "")
    config.reset_settings_cache()

    loaded = config.get_settings()

    assert loaded.microsoft_tenant == "consumers"
    assert loaded.microsoft_client_id == MICROSOFT_CLIENT_ID


def test_a_tenant_with_a_slash_is_refused(
    valid_environment: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MICROSOFT_TENANT", "common/oauth2")
    config.reset_settings_cache()

    with pytest.raises(ConfigurationError, match="MICROSOFT_TENANT"):
        config.get_settings()


def test_login_urls_follow_the_tenant() -> None:
    device, token = login_urls("common")

    assert device == "https://login.microsoftonline.com/common/oauth2/v2.0/devicecode"
    assert token == "https://login.microsoftonline.com/common/oauth2/v2.0/token"


@pytest.mark.asyncio
async def test_the_configured_application_and_tenant_are_used(
    valid_environment: None,
    monkeypatch: pytest.MonkeyPatch,
    repositories: Repositories,
    clock: FixedClock,
) -> None:
    monkeypatch.setenv("MICROSOFT_TENANT", "common")
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "own-app-id")
    config.reset_settings_cache()
    loaded = config.get_settings()
    store = SecretStore(repositories.app_secrets, loaded.token_encryption_key, clock)
    device_url, _ = login_urls("common")

    with respx.mock:
        route = respx.post(device_url).mock(
            return_value=httpx.Response(
                200,
                json={
                    "user_code": "ABC",
                    "verification_uri": "https://microsoft.example/link",
                    "device_code": "handle",
                    "interval": 1,
                },
            )
        )
        async with MicrosoftAuthenticator.for_settings(store, clock, loaded) as authenticator:
            prompt = await authenticator.request_device_code()

    assert prompt.user_code == "ABC"
    assert b"client_id=own-app-id" in route.calls.last.request.content
