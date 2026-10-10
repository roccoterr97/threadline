"""The personal link to the shared dashboard, and where it reaches the owner."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from html import escape

import pytest
from pydantic import SecretStr

from tests.conftest import as_client
from tests.summary_world import NOW as SAMPLE_NOW
from tests.summary_world import TODAYS_RUN, sample_client
from tracker.domain.dashboard_link import (
    DashboardAddress,
    connect_fragment,
    dashboard_address,
    require_public_key,
)
from tracker.domain.enums import RunStatus
from tracker.repositories import build_repositories
from tracker.schemas.summary import SummaryContent, SummaryEmail
from tracker.services.summary.builder import SummaryBuilder
from tracker.services.summary.html_layout import render_html
from tracker.services.summary.renderer import render_email
from tracker.services.summary.wording import Branding
from tracker.shared.clock import FixedClock
from tracker.shared.config import Settings
from tracker.shared.constants.dashboard import HOSTED_DASHBOARD_URL
from tracker.shared.errors import ValidationFailedError

PROJECT_URL = "https://abcdefghijklmnop.supabase.co"
PUBLISHABLE = "sb_publishable_AbC-123_x"
CONNECT = f"project=abcdefghijklmnop&key={PUBLISHABLE}"
NOW = datetime(2026, 10, 9, 5, 0, tzinfo=UTC)


def _built(settings: Settings) -> SummaryEmail:
    """Build the summary of the sample run with these settings."""
    repositories = build_repositories(as_client(sample_client()))
    return SummaryBuilder(repositories, settings, FixedClock(SAMPLE_NOW)).build(TODAYS_RUN)


def _legacy_key(role: str) -> str:
    """A made-up legacy (JWT) key claiming ``role``; its signature is never checked here."""
    claims = base64.urlsafe_b64encode(json.dumps({"role": role}).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJIUzI1NiJ9.{claims}.c2lnbmF0dXJl"


# --- The link itself ---------------------------------------------------------------


def test_the_link_names_the_project_and_the_publishable_key_after_the_hash() -> None:
    assert connect_fragment(PROJECT_URL, PUBLISHABLE) == CONNECT


def test_a_legacy_public_key_keeps_its_dots() -> None:
    key = _legacy_key("anon")

    assert connect_fragment(PROJECT_URL, key) == f"project=abcdefghijklmnop&key={key}"


@pytest.mark.parametrize(
    "key",
    ["sb_secret_abc", _legacy_key("service_role"), _legacy_key("supabase_admin"), "a key", ""],
)
def test_a_key_the_browser_must_never_hold_is_refused(key: str) -> None:
    with pytest.raises(ValidationFailedError, match="SUPABASE_ANON_KEY"):
        connect_fragment(PROJECT_URL, key)


@pytest.mark.parametrize(
    "url", ["http://abcdefghijklmnop.supabase.co", "https://db.example.com", "abcdefghijklmnop"]
)
def test_an_address_that_is_not_a_supabase_project_is_refused(url: str) -> None:
    with pytest.raises(ValidationFailedError, match="SUPABASE_URL"):
        connect_fragment(url, PUBLISHABLE)


def test_a_public_key_is_returned_unchanged() -> None:
    assert require_public_key(PUBLISHABLE) == PUBLISHABLE


# --- The address of each page -----------------------------------------------------------


def test_every_page_of_the_shared_dashboard_carries_the_personal_part_after_its_path() -> None:
    address = DashboardAddress(HOSTED_DASHBOARD_URL, CONNECT)

    assert address.shared
    assert address.page() == f"{HOSTED_DASHBOARD_URL}/#{CONNECT}"
    assert address.page("/review") == f"{HOSTED_DASHBOARD_URL}/review#{CONNECT}"


def test_an_own_copy_gets_no_personal_part() -> None:
    address = dashboard_address("https://you.netlify.app/", PROJECT_URL, PUBLISHABLE)

    assert address == DashboardAddress("https://you.netlify.app")
    assert address is not None
    assert not address.shared
    assert address.page("/runs") == "https://you.netlify.app/runs"


def test_the_shared_address_gets_the_personal_part() -> None:
    address = dashboard_address(f"{HOSTED_DASHBOARD_URL}/", PROJECT_URL, PUBLISHABLE)

    assert address == DashboardAddress(HOSTED_DASHBOARD_URL, CONNECT)


def test_no_address_means_no_links() -> None:
    assert dashboard_address(None, PROJECT_URL, PUBLISHABLE) is None
    assert dashboard_address("  ", PROJECT_URL, PUBLISHABLE) is None


def test_a_shared_address_whose_link_cannot_be_made_keeps_its_plain_address() -> None:
    address = dashboard_address(HOSTED_DASHBOARD_URL, PROJECT_URL, "sb_secret_abc")

    assert address == DashboardAddress(HOSTED_DASHBOARD_URL)


# --- The morning e-mail -------------------------------------------------------------------


def _shared_content(**changes: object) -> SummaryContent:
    base = {
        "generated_at": NOW,
        "day": NOW.date(),
        "run_status": RunStatus.SUCCESS,
        "open_questions": 2,
        "dashboard_url": HOSTED_DASHBOARD_URL,
        "dashboard_connect": CONNECT,
    }
    return SummaryContent(**{**base, **changes})  # pyright: ignore[reportArgumentType]


def test_the_plain_text_e_mail_links_every_page_with_the_personal_link() -> None:
    branding = Branding("Threadline", "[Threadline]")
    email = render_email(_shared_content(), "owner@inbox.example", branding)

    assert f"Open the dashboard: {HOSTED_DASHBOARD_URL}/#{CONNECT}" in email.text_body
    assert f"{HOSTED_DASHBOARD_URL}/review#{CONNECT}" in email.text_body
    assert f"Run page: {HOSTED_DASHBOARD_URL}/runs#{CONNECT}" in email.text_body


def test_the_formatted_e_mail_links_every_page_with_the_personal_link() -> None:
    html = render_html(_shared_content(), "Threadline")
    connect = escape(CONNECT, quote=True)

    assert f"href='{HOSTED_DASHBOARD_URL}/#{connect}'" in html
    assert f"href='{HOSTED_DASHBOARD_URL}/review#{connect}'" in html
    assert f"href='{HOSTED_DASHBOARD_URL}/runs#{connect}'" in html


def test_an_own_copy_s_links_are_unchanged() -> None:
    content = _shared_content(dashboard_url="https://you.netlify.app", dashboard_connect=None)

    assert content.dashboard_page("/review") == "https://you.netlify.app/review"
    assert _shared_content(dashboard_url=None).dashboard_page() is None


def test_the_summary_builder_makes_the_personal_link_from_the_run_s_settings(
    settings: Settings,
) -> None:
    shared = settings.model_copy(
        update={
            "dashboard_base_url": HOSTED_DASHBOARD_URL,
            "supabase_url": PROJECT_URL,
            "supabase_anon_key": SecretStr(PUBLISHABLE),
        }
    )

    email = _built(shared)

    assert f"Open the dashboard: {HOSTED_DASHBOARD_URL}/#{CONNECT}" in email.text_body


def test_the_summary_builder_falls_back_to_the_plain_address_without_a_usable_key(
    settings: Settings,
) -> None:
    shared = settings.model_copy(
        update={
            "dashboard_base_url": HOSTED_DASHBOARD_URL,
            "supabase_url": PROJECT_URL,
            "supabase_anon_key": SecretStr("sb_secret_abc"),
        }
    )

    email = _built(shared)

    assert f"Open the dashboard: {HOSTED_DASHBOARD_URL}\n" in email.text_body
    assert "sb_secret_abc" not in email.text_body
