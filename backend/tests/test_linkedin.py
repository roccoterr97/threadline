"""The LinkedIn snapshot reader and the row parser.

Every payload here is made up. It copies the *shape* the 2026-09-18 test
recorded — the column names, the date format, the paging behaviour — and none of
the content.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import respx
from pydantic import SecretStr

from tracker.infrastructure.linkedin.client import LinkedInSnapshotClient
from tracker.infrastructure.linkedin.parser import (
    build_message_id,
    normalise_profile_url,
    parse_row,
    parse_rows,
    parse_timestamp,
)
from tracker.shared.constants.collection import LINKEDIN_SNAPSHOT_URL
from tracker.shared.errors import SourceAuthError, SourceUnavailableError

TOKEN = SecretStr("made-up-linkedin-key")


def row(
    conversation_id: str = "2-conv-aaa",
    *,
    sender: str = "https://www.linkedin.com/in/elodie-martin",
    sender_name: str = "Élodie Martin",
    date: str = "2026-09-10 09:30:00 UTC",
    content: str = "Hello Sam, are you open to a chat?",
    folder: str = "INBOX",
) -> dict[str, str]:
    """Build one made-up snapshot row."""
    return {
        "CONVERSATION ID": conversation_id,
        "CONVERSATION TITLE": "Élodie Martin",
        "FROM": sender_name,
        "SENDER PROFILE URL": sender,
        "TO": "Sam Rivera",
        "RECIPIENT PROFILE URLS": "https://www.linkedin.com/in/sam",
        "DATE": date,
        "SUBJECT": "",
        "CONTENT": content,
        "FOLDER": folder,
        "ATTACHMENTS": "",
    }


def page(rows: list[dict[str, str]]) -> dict[str, Any]:
    """Wrap rows in the envelope the snapshot endpoint uses."""
    return {
        "paging": {"start": 0, "count": 10, "total": 9999},
        "elements": [{"snapshotDomain": "INBOX", "snapshotData": rows}],
    }


def snapshot_handler(pages: dict[int, list[dict[str, str]]]) -> Any:
    """Answer each page, and 404 for the page after the last one."""

    def handle(request: httpx.Request) -> httpx.Response:
        index = int(request.url.params["start"])
        if index not in pages:
            return httpx.Response(404, json={"message": "no more data"})
        return httpx.Response(200, json=page(pages[index]))

    return handle


@pytest.mark.asyncio
async def test_paging_stops_cleanly_on_the_404_after_the_last_page() -> None:
    pages = {0: [row("2-a"), row("2-b")], 1: [row("2-c")]}

    with respx.mock:
        respx.get(LINKEDIN_SNAPSHOT_URL).mock(side_effect=snapshot_handler(pages))
        async with LinkedInSnapshotClient(TOKEN) as client:
            rows = [item async for item in client.inbox_rows()]

    assert len(rows) == 3
    assert [item["CONVERSATION ID"] for item in rows] == ["2-a", "2-b", "2-c"]


@pytest.mark.asyncio
async def test_an_empty_archive_is_not_an_error() -> None:
    with respx.mock:
        respx.get(LINKEDIN_SNAPSHOT_URL).mock(side_effect=snapshot_handler({}))
        async with LinkedInSnapshotClient(TOKEN) as client:
            rows = [item async for item in client.inbox_rows()]

    assert rows == []


@pytest.mark.asyncio
async def test_a_rejected_key_is_reported_in_plain_words() -> None:
    with respx.mock:
        respx.get(LINKEDIN_SNAPSHOT_URL).mock(return_value=httpx.Response(401, json={}))
        async with LinkedInSnapshotClient(TOKEN) as client:
            with pytest.raises(SourceAuthError, match="LinkedIn key rejected"):
                _ = [item async for item in client.inbox_rows()]


@pytest.mark.asyncio
async def test_an_unexpected_status_is_an_outage_not_a_crash() -> None:
    with respx.mock:
        respx.get(LINKEDIN_SNAPSHOT_URL).mock(return_value=httpx.Response(503, json={}))
        async with LinkedInSnapshotClient(TOKEN) as client:
            with pytest.raises(SourceUnavailableError, match="status 503"):
                _ = [item async for item in client.inbox_rows()]


@pytest.mark.asyncio
async def test_a_network_failure_is_an_outage_not_a_crash() -> None:
    with respx.mock:
        respx.get(LINKEDIN_SNAPSHOT_URL).mock(side_effect=httpx.ConnectError("no route"))
        async with LinkedInSnapshotClient(TOKEN) as client:
            with pytest.raises(SourceUnavailableError, match="could not be reached"):
                _ = [item async for item in client.inbox_rows()]


@pytest.mark.asyncio
async def test_the_key_and_the_version_travel_with_every_request() -> None:
    with respx.mock:
        route = respx.get(LINKEDIN_SNAPSHOT_URL).mock(side_effect=snapshot_handler({0: [row()]}))
        async with LinkedInSnapshotClient(TOKEN) as client:
            _ = [item async for item in client.inbox_rows()]

    sent = route.calls[0].request
    assert sent.headers["Authorization"] == "Bearer made-up-linkedin-key"
    assert sent.headers["Linkedin-Version"] == "202312"


def test_the_same_row_always_yields_the_same_identifier() -> None:
    first = parse_row(row())
    second = parse_row(dict(row()))

    assert first is not None
    assert second is not None
    assert first.message_id == second.message_id
    assert len(first.message_id) == 64


def test_a_different_message_yields_a_different_identifier() -> None:
    first = parse_row(row(content="Hello Sam"))
    second = parse_row(row(content="Hello Sam!"))

    assert first is not None
    assert second is not None
    assert first.message_id != second.message_id


def test_the_identifier_is_built_from_the_four_fields_that_make_a_row_unique() -> None:
    parsed = parse_row(row())

    assert parsed is not None
    assert parsed.message_id == build_message_id(
        "2-conv-aaa",
        datetime(2026, 9, 10, 9, 30, tzinfo=UTC),
        "linkedin.com/in/elodie-martin",
        "Hello Sam, are you open to a chat?",
    )


def test_a_row_is_read_into_its_parts() -> None:
    parsed = parse_row(row(folder="SPONSORED_INMAIL"))

    assert parsed is not None
    assert parsed.conversation_id == "2-conv-aaa"
    assert parsed.sent_at == datetime(2026, 9, 10, 9, 30, tzinfo=UTC)
    assert parsed.sender_profile_url == "linkedin.com/in/elodie-martin"
    assert parsed.sender_name == "Élodie Martin"
    assert parsed.recipient_profile_urls == ("linkedin.com/in/sam",)
    assert parsed.folder == "SPONSORED_INMAIL"


@pytest.mark.parametrize(
    "broken",
    [
        {"CONVERSATION ID": "", "DATE": "2026-09-10 09:30:00 UTC"},
        {"CONVERSATION ID": "2-a", "DATE": "yesterday"},
        {},
    ],
)
def test_rows_that_cannot_be_stored_safely_are_skipped(broken: dict[str, str]) -> None:
    assert parse_row(broken) is None


def test_parsing_a_batch_drops_only_the_unusable_rows() -> None:
    parsed = list(parse_rows([row("2-a"), {"CONVERSATION ID": "2-b", "DATE": "nonsense"}]))

    assert [item.conversation_id for item in parsed] == ["2-a"]


def test_timestamps_are_read_as_utc() -> None:
    assert parse_timestamp("2026-09-10 09:30:00 UTC") == datetime(2026, 9, 10, 9, 30, tzinfo=UTC)
    assert parse_timestamp("2026-09-10 09:30:00") == datetime(2026, 9, 10, 9, 30, tzinfo=UTC)
    assert parse_timestamp("not a date") is None


@pytest.mark.parametrize(
    "spelling",
    [
        "https://www.linkedin.com/in/sam",
        "http://linkedin.com/in/sam/",
        "LinkedIn.com/in/Sam?trk=abc",
        "  https://www.linkedin.com/in/sam#about ",
    ],
)
def test_every_spelling_of_one_profile_compares_equal(spelling: str) -> None:
    assert normalise_profile_url(spelling) == "linkedin.com/in/sam"
