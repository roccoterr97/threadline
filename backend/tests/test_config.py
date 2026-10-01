"""Configuration is the only reader of the environment, and it fails loudly."""

from __future__ import annotations

from calendar import Day
from datetime import UTC
from zoneinfo import ZoneInfo

import pytest

from tracker.shared.config import (
    DEFAULT_PRODUCT_NAME,
    DEFAULT_SUMMARY_SUBJECT_PREFIX,
    DEFAULT_WEEKEND_DAYS,
    AppEnv,
    LogLevel,
    get_settings,
    reset_settings_cache,
)
from tracker.shared.errors import ConfigurationError


@pytest.mark.usefixtures("valid_environment")
def test_reads_every_required_value() -> None:
    settings = get_settings()

    assert settings.supabase_url == "https://sample-project.supabase.co"
    assert settings.supabase_service_role_key.get_secret_value() == "service-key"
    assert settings.app_env is AppEnv.DEVELOPMENT
    assert settings.log_level is LogLevel.INFO


@pytest.mark.usefixtures("valid_environment")
def test_owner_addresses_are_split_and_lowercased() -> None:
    assert get_settings().owner_email_addresses == (
        "sam.rivera@mailbox.example",
        "sam@other.example",
    )


@pytest.mark.usefixtures("valid_environment")
def test_settings_are_cached() -> None:
    assert get_settings() is get_settings()


def test_missing_values_raise_a_configuration_error() -> None:
    with pytest.raises(ConfigurationError) as raised:
        get_settings()

    message = str(raised.value)
    assert "SUPABASE_URL" in message
    assert "TOKEN_ENCRYPTION_KEY" in message


def test_non_https_database_address_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "http://sample-project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "key")
    monkeypatch.setenv("OWNER_LINKEDIN_PROFILE_URL", "https://www.linkedin.com/in/sam")
    monkeypatch.setenv("OWNER_EMAIL_ADDRESSES", "sam.rivera@mailbox.example")
    reset_settings_cache()

    with pytest.raises(ConfigurationError, match="SUPABASE_URL"):
        get_settings()


@pytest.mark.usefixtures("valid_environment")
def test_secret_values_are_not_printed() -> None:
    assert "service-key" not in repr(get_settings())


# --- Owner settings (Plan 18) ---------------------------------------------------


def _with(monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None:
    """Set one variable on top of the valid environment and forget the cache."""
    monkeypatch.setenv(name, value)
    reset_settings_cache()


@pytest.mark.usefixtures("valid_environment")
def test_every_owner_setting_has_a_default() -> None:
    settings = get_settings()

    assert settings.summary_recipient is None
    assert settings.summary_recipient_address == "sam.rivera@mailbox.example"
    assert settings.owner_display_name is None
    assert settings.owner_time_zone == "UTC"
    assert settings.owner_zone is UTC
    assert settings.owner_weekend_days == DEFAULT_WEEKEND_DAYS == {Day.SATURDAY, Day.SUNDAY}
    assert settings.product_name == DEFAULT_PRODUCT_NAME == "Threadline"
    assert settings.summary_subject_prefix == DEFAULT_SUMMARY_SUBJECT_PREFIX == "[Threadline]"


@pytest.mark.usefixtures("valid_environment")
def test_a_line_left_empty_as_in_the_example_file_means_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "SUMMARY_RECIPIENT",
        "OWNER_DISPLAY_NAME",
        "OWNER_TIME_ZONE",
        "OWNER_WEEKEND_DAYS",
        "PRODUCT_NAME",
        "SUMMARY_SUBJECT_PREFIX",
        "LINKEDIN_ACCESS_TOKEN",
        "LINKEDIN_TOKEN_EXPIRES_ON",
        "DASHBOARD_BASE_URL",
    ):
        monkeypatch.setenv(name, "")
    reset_settings_cache()

    settings = get_settings()

    assert settings.summary_recipient is None
    assert settings.owner_time_zone == "UTC"
    assert settings.owner_weekend_days == DEFAULT_WEEKEND_DAYS
    assert settings.product_name == DEFAULT_PRODUCT_NAME
    assert settings.summary_subject_prefix == DEFAULT_SUMMARY_SUBJECT_PREFIX
    assert settings.linkedin_access_token is None
    assert settings.linkedin_token_expires_on is None
    assert settings.dashboard_base_url is None


@pytest.mark.usefixtures("valid_environment")
def test_an_explicit_recipient_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    _with(monkeypatch, "SUMMARY_RECIPIENT", " Desk@Inbox.Example ")

    settings = get_settings()

    assert settings.summary_recipient == "desk@inbox.example"
    assert settings.summary_recipient_address == "desk@inbox.example"


@pytest.mark.usefixtures("valid_environment")
@pytest.mark.parametrize(
    "value",
    ["not-an-address", "a@inbox.example, b@inbox.example", "Sam <sam@inbox.example>"],
)
def test_a_recipient_that_is_not_one_address_is_refused(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    _with(monkeypatch, "SUMMARY_RECIPIENT", value)

    with pytest.raises(ConfigurationError, match="SUMMARY_RECIPIENT") as raised:
        get_settings()

    assert value not in str(raised.value)


@pytest.mark.usefixtures("valid_environment")
def test_an_explicit_display_name_is_tidied(monkeypatch: pytest.MonkeyPatch) -> None:
    _with(monkeypatch, "OWNER_DISPLAY_NAME", "  Jordan   Doe ")

    assert get_settings().owner_display_name == "Jordan Doe"


@pytest.mark.usefixtures("valid_environment")
def test_a_display_name_of_only_spaces_is_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    _with(monkeypatch, "OWNER_DISPLAY_NAME", "   ")

    assert get_settings().owner_display_name is None


@pytest.mark.usefixtures("valid_environment")
def test_an_explicit_time_zone_is_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    _with(monkeypatch, "OWNER_TIME_ZONE", " Asia/Tokyo ")

    settings = get_settings()

    assert settings.owner_time_zone == "Asia/Tokyo"
    assert settings.owner_zone == ZoneInfo("Asia/Tokyo")


@pytest.mark.usefixtures("valid_environment")
def test_a_time_zone_in_the_wrong_case_is_kept_in_its_real_spelling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with(monkeypatch, "OWNER_TIME_ZONE", "america/new_york")

    settings = get_settings()

    assert settings.owner_time_zone == "America/New_York"
    assert settings.owner_zone == ZoneInfo("America/New_York")


@pytest.mark.usefixtures("valid_environment")
def test_utc_is_accepted_in_any_case(monkeypatch: pytest.MonkeyPatch) -> None:
    _with(monkeypatch, "OWNER_TIME_ZONE", "utc")

    assert get_settings().owner_zone is UTC


@pytest.mark.usefixtures("valid_environment")
@pytest.mark.parametrize("value", ["Mars/Olympus_Mons", "Europe/", "../etc/passwd", "CEST+2 hours"])
def test_an_unknown_time_zone_is_refused(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    _with(monkeypatch, "OWNER_TIME_ZONE", value)

    with pytest.raises(ConfigurationError, match="OWNER_TIME_ZONE"):
        get_settings()


@pytest.mark.usefixtures("valid_environment")
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("fri,sat", {Day.FRIDAY, Day.SATURDAY}),
        ("Friday, Saturday", {Day.FRIDAY, Day.SATURDAY}),
        ("sun", {Day.SUNDAY}),
        ("none", set()),
    ],
)
def test_an_explicit_weekend_is_read(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: set[Day]
) -> None:
    _with(monkeypatch, "OWNER_WEEKEND_DAYS", value)

    assert get_settings().owner_weekend_days == expected


@pytest.mark.usefixtures("valid_environment")
@pytest.mark.parametrize(
    ("value", "reason"),
    [
        ("sat,funday", "such as sat,sun"),
        ("mon,tue,wed,thu,fri,sat,sun", "at least one working day"),
    ],
)
def test_a_weekend_that_cannot_work_is_refused(
    monkeypatch: pytest.MonkeyPatch, value: str, reason: str
) -> None:
    _with(monkeypatch, "OWNER_WEEKEND_DAYS", value)

    with pytest.raises(ConfigurationError, match=reason):
        get_settings()


@pytest.mark.usefixtures("valid_environment")
def test_an_explicit_product_name_and_prefix_are_used(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRODUCT_NAME", " Weekly   Desk ")
    _with(monkeypatch, "SUMMARY_SUBJECT_PREFIX", "[Weekly Desk]")

    settings = get_settings()

    assert settings.product_name == "Weekly Desk"
    assert settings.summary_subject_prefix == "[Weekly Desk]"


@pytest.mark.usefixtures("valid_environment")
def test_a_product_name_of_only_spaces_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    _with(monkeypatch, "PRODUCT_NAME", "   ")

    with pytest.raises(ConfigurationError, match="PRODUCT_NAME"):
        get_settings()


@pytest.mark.usefixtures("valid_environment")
@pytest.mark.parametrize("value", ["   ", "[]", "Re"])
def test_a_prefix_short_enough_to_match_real_mail_is_refused(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    _with(monkeypatch, "SUMMARY_SUBJECT_PREFIX", value)

    with pytest.raises(ConfigurationError, match="SUMMARY_SUBJECT_PREFIX"):
        get_settings()


@pytest.mark.usefixtures("valid_environment")
def test_linkedin_is_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OWNER_LINKEDIN_PROFILE_URL")
    reset_settings_cache()

    settings = get_settings()

    assert settings.owner_linkedin_profile_url is None
    assert settings.linkedin_enabled is False


@pytest.mark.usefixtures("valid_environment")
def test_linkedin_needs_both_the_profile_and_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    assert get_settings().linkedin_enabled is False

    _with(monkeypatch, "LINKEDIN_ACCESS_TOKEN", "made-up-linkedin-key")

    assert get_settings().linkedin_enabled is True
