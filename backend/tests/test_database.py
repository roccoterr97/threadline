"""The database client retries a bounded number of times, then fails cleanly."""

from __future__ import annotations

import httpx
import pytest
from postgrest import APIError

from tests.conftest import FakeSupabaseClient, as_client
from tracker.infrastructure.database import create_database_client, probe_database
from tracker.repositories.app_secrets import AppSecretRepository
from tracker.shared.config import get_settings
from tracker.shared.errors import DatabaseUnavailableError


class UnreachableClient(FakeSupabaseClient):
    """A client whose every request fails."""

    def __init__(self) -> None:
        super().__init__()
        self.attempts = 0

    def table(self, table_name: str) -> object:  # type: ignore[override]
        self.attempts += 1
        raise httpx.ConnectError("no route to host")


def test_a_working_database_is_probed_once(fake_client: FakeSupabaseClient) -> None:
    probe_database(as_client(fake_client), attempts=3, delay_seconds=0, sleep=lambda _: None)

    assert fake_client.executed == [("app_secrets", "select")]


def test_every_attempt_is_made_before_giving_up() -> None:
    client = UnreachableClient()
    waited: list[float] = []

    with pytest.raises(DatabaseUnavailableError, match="3 attempts"):
        probe_database(as_client(client), attempts=3, delay_seconds=5, sleep=waited.append)

    assert client.attempts == 3
    assert waited == [5, 5]


@pytest.mark.usefixtures("valid_environment")
def test_the_client_is_built_from_the_settings() -> None:
    client = create_database_client(get_settings())

    assert client is not None


class FlakyClient(FakeSupabaseClient):
    """A client whose first request drops, and whose next one works."""

    def __init__(self, failures: int) -> None:
        super().__init__()
        self.attempts = 0
        self._failures = failures

    def table(self, table_name: str) -> object:  # type: ignore[override]
        self.attempts += 1
        if self.attempts <= self._failures:
            raise httpx.ConnectError("dropped")
        return super().table(table_name)


class RefusingClient(FakeSupabaseClient):
    """A client whose every request is answered with a refusal."""

    def __init__(self) -> None:
        super().__init__()
        self.attempts = 0

    def table(self, table_name: str) -> object:  # type: ignore[override]
        self.attempts += 1
        raise APIError({"message": "permission denied", "code": "42501"})


def test_a_dropped_database_connection_is_tried_again() -> None:
    """A blip mid-run must not end a whole morning's collection.

    Every write is an upsert on a natural key or a delete by id, so repeating
    one is safe.
    """
    client = FlakyClient(failures=1)

    rows = AppSecretRepository(as_client(client)).list(limit=1)

    assert rows == []
    assert client.attempts == 2


def test_a_refusal_from_the_database_is_not_retried() -> None:
    """The database answered and said no; asking again gets the same no."""
    client = RefusingClient()

    with pytest.raises(DatabaseUnavailableError):
        AppSecretRepository(as_client(client)).list(limit=1)

    assert client.attempts == 1
