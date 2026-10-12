"""The Google Calendar set-up step: one paste, checked once, saved, sent to GitHub."""

from __future__ import annotations

import pytest

from tests.ical_world import GOOGLE_ADDRESS, calendar_file, vevent
from tests.setup_world import PROJECT_REF, World, configured_env, make_world
from tracker.services.setup.step_cloud import allowed_hosts
from tracker.services.setup.step_google_calendar import GoogleCalendarStep, say_calendar_tip
from tracker.shared.constants.calendar_feed import (
    GOOGLE_CALENDAR_SETTINGS_PAGE,
    GOOGLE_CALENDAR_URL_SETTING,
)
from tracker.shared.errors import SourceAuthError

pytestmark = pytest.mark.asyncio

OLD_ADDRESS = "https://calendar.google.com/calendar/ical/x/private-reset-long-ago/basic.ics"


def _world(*answers: str | bool, env: dict[str, str] | None = None) -> World:
    """A world where Google serves a calendar with one meeting at the good address."""
    world = make_world(list(answers), env if env is not None else configured_env())
    world.downloads[GOOGLE_ADDRESS] = calendar_file(vevent("intro@google.com"))
    return world


async def test_one_paste_is_checked_saved_and_sent_to_github_without_a_question() -> None:
    world = _world(GOOGLE_ADDRESS)

    await GoogleCalendarStep().run(world.context())

    assert world.io.opened == [GOOGLE_CALENDAR_SETTINGS_PAGE]
    assert world.io.asked == ["Secret address in iCal format (press Enter to skip)"]
    assert world.env.values[GOOGLE_CALENDAR_URL_SETTING] == GOOGLE_ADDRESS
    assert world.github.secrets == {GOOGLE_CALENDAR_URL_SETTING: GOOGLE_ADDRESS}
    assert world.github.variables == {}
    text = world.io.text()
    assert "Your calendar answered: 1 event in the last 30 days and the next 60." in text
    assert "Under 'Secret address in iCal format', click the copy button." in text
    assert GOOGLE_ADDRESS not in text


async def test_enter_skips_without_reading_anything() -> None:
    world = _world("")

    await GoogleCalendarStep().run(world.context())

    assert GOOGLE_CALENDAR_URL_SETTING not in world.env.values
    assert world.github.secrets == {}
    assert "Skipped. Run 'uv run tracker setup google-calendar' whenever you want it." in (
        world.io.said
    )


async def test_an_address_google_no_longer_accepts_is_asked_again() -> None:
    world = _world(OLD_ADDRESS, GOOGLE_ADDRESS)

    await GoogleCalendarStep().run(world.context())

    assert world.env.values[GOOGLE_CALENDAR_URL_SETTING] == GOOGLE_ADDRESS
    text = world.io.text()
    assert "no longer accepts this secret address" in text
    assert "private-reset-long-ago" not in text


async def test_three_refused_addresses_stop_the_step_and_save_nothing() -> None:
    world = _world(OLD_ADDRESS, OLD_ADDRESS, OLD_ADDRESS)

    with pytest.raises(SourceAuthError):
        await GoogleCalendarStep().run(world.context())

    assert GOOGLE_CALENDAR_URL_SETTING not in world.env.values


async def test_an_address_that_is_not_https_is_refused_without_being_repeated() -> None:
    world = _world("http://calendar.example/secret-123.ics", GOOGLE_ADDRESS)

    await GoogleCalendarStep().run(world.context())

    text = world.io.text()
    assert "the calendar address must start with https://. Please try again." in text
    assert "secret-123" not in text
    assert world.env.values[GOOGLE_CALENDAR_URL_SETTING] == GOOGLE_ADDRESS


async def test_a_page_that_is_not_a_calendar_is_explained() -> None:
    world = _world("https://calendar.google.com/calendar/embed?src=sam", GOOGLE_ADDRESS)
    world.downloads["https://calendar.google.com/calendar/embed?src=sam"] = b"<html></html>"

    await GoogleCalendarStep().run(world.context())

    assert "did not give a calendar file" in world.io.text()
    assert world.env.values[GOOGLE_CALENDAR_URL_SETTING] == GOOGLE_ADDRESS


async def test_a_webcal_address_is_saved_as_https() -> None:
    world = _world(GOOGLE_ADDRESS.replace("https://", "webcal://", 1))

    await GoogleCalendarStep().run(world.context())

    assert world.env.values[GOOGLE_CALENDAR_URL_SETTING] == GOOGLE_ADDRESS


async def test_without_the_github_cli_the_command_is_named_and_nothing_is_asked() -> None:
    world = _world(GOOGLE_ADDRESS)
    world.github.signed_in = False

    await GoogleCalendarStep().run(world.context())

    assert world.github.secrets == {}
    assert "To send them later, run: uv run tracker setup github" in world.io.said


async def test_running_it_again_with_the_same_address_changes_nothing() -> None:
    world = _world(
        GOOGLE_ADDRESS, env=configured_env() | {GOOGLE_CALENDAR_URL_SETTING: GOOGLE_ADDRESS}
    )

    assert await GoogleCalendarStep().is_done(world.context())
    await GoogleCalendarStep().run(world.context())

    assert "This address is already saved." in world.io.said
    assert world.github.secrets == {}


async def test_enter_keeps_an_address_saved_before() -> None:
    world = _world("", env=configured_env() | {GOOGLE_CALENDAR_URL_SETTING: GOOGLE_ADDRESS})

    await GoogleCalendarStep().run(world.context())

    assert "Kept the address saved before." in world.io.said
    assert world.env.values[GOOGLE_CALENDAR_URL_SETTING] == GOOGLE_ADDRESS


async def test_it_is_not_done_until_an_address_is_saved() -> None:
    assert not await GoogleCalendarStep().is_done(_world().context())


@pytest.mark.parametrize(
    ("env", "said"),
    [
        ({"IMAP_PROVIDER": "gmail"}, True),
        ({"IMAP_PROVIDER": "icloud"}, False),
        ({"IMAP_PROVIDER": "gmail", GOOGLE_CALENDAR_URL_SETTING: GOOGLE_ADDRESS}, False),
        ({}, False),
    ],
)
async def test_a_gmail_owner_is_pointed_at_the_calendar_in_one_line(
    env: dict[str, str], said: bool
) -> None:
    world = _world(env=configured_env() | env)

    say_calendar_tip(world.context())

    assert world.io.asked == []
    tip = "Your mailbox is Gmail: add your Google Calendar too"
    assert any(line.startswith(tip) for line in world.io.said) is said


async def test_the_cloud_route_is_told_to_allow_the_calendars_server() -> None:
    world = _world(env=configured_env() | {GOOGLE_CALENDAR_URL_SETTING: GOOGLE_ADDRESS})

    assert allowed_hosts(world.context())[-1] == "calendar.google.com"
    assert allowed_hosts(world.context())[0] == f"{PROJECT_REF}.supabase.co"
