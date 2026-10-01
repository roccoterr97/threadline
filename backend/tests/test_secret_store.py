"""Secrets survive a round trip, and never sit in the database in the clear."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from tests.conftest import TEST_ENCRYPTION_KEY, FakeSupabaseClient
from tracker.infrastructure.secret_store import SecretStore
from tracker.repositories import Repositories
from tracker.shared.clock import FixedClock
from tracker.shared.errors import ConfigurationError


@pytest.fixture
def store(repositories: Repositories, clock: FixedClock) -> SecretStore:
    return SecretStore(repositories.app_secrets, SecretStr(TEST_ENCRYPTION_KEY), clock)


def test_a_secret_survives_the_round_trip(store: SecretStore) -> None:
    store.put_secret("microsoft_refresh_token", "the-key")

    assert store.get_secret("microsoft_refresh_token") == "the-key"


def test_the_stored_value_is_not_readable(
    store: SecretStore,
    fake_client: FakeSupabaseClient,
) -> None:
    store.put_secret("microsoft_refresh_token", "the-key")

    stored = fake_client.tables["app_secrets"][0]["encrypted_value"]
    assert "the-key" not in stored


def test_an_unknown_secret_reads_as_nothing(store: SecretStore) -> None:
    assert store.get_secret("never_written") is None


def test_rotating_keeps_one_row_and_the_same_identifier(
    store: SecretStore,
    fake_client: FakeSupabaseClient,
) -> None:
    first = store.put_secret("microsoft_refresh_token", "old-key")
    second = store.put_secret("microsoft_refresh_token", "new-key")

    assert first.id == second.id
    assert len(fake_client.tables["app_secrets"]) == 1
    assert store.get_secret("microsoft_refresh_token") == "new-key"


def test_rotation_time_comes_from_the_injected_clock(
    store: SecretStore,
    clock: FixedClock,
) -> None:
    secret = store.put_secret("microsoft_refresh_token", "the-key")

    assert secret.rotated_at == clock.now()


def test_deleting_removes_the_row(store: SecretStore) -> None:
    store.put_secret("microsoft_refresh_token", "the-key")

    assert store.delete_secret("microsoft_refresh_token") is True
    assert store.get_secret("microsoft_refresh_token") is None


def test_a_malformed_encryption_key_is_refused(
    repositories: Repositories,
    clock: FixedClock,
) -> None:
    with pytest.raises(ConfigurationError, match="TOKEN_ENCRYPTION_KEY"):
        SecretStore(repositories.app_secrets, SecretStr("not-a-fernet-key"), clock)


def test_a_value_written_with_another_key_cannot_be_read(
    repositories: Repositories,
    clock: FixedClock,
) -> None:
    from cryptography.fernet import Fernet

    SecretStore(repositories.app_secrets, SecretStr(TEST_ENCRYPTION_KEY), clock).put_secret(
        "microsoft_refresh_token", "the-key"
    )
    other = SecretStore(repositories.app_secrets, SecretStr(Fernet.generate_key().decode()), clock)

    with pytest.raises(ConfigurationError, match="TOKEN_ENCRYPTION_KEY"):
        other.get_secret("microsoft_refresh_token")
