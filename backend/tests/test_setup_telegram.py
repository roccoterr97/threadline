"""The Telegram set-up step and its login, without a terminal or a network."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

import pytest
from pydantic import SecretStr
from telethon import TelegramClient, errors, types

from tests.setup_world import (
    GOOD_TELEGRAM_API_HASH,
    GOOD_TELEGRAM_API_ID,
    GOOD_TELEGRAM_CODE,
    GOOD_TELEGRAM_PHONE,
    TELEGRAM_SESSION_VALUE,
    World,
    configured_env,
    make_world,
)
from tracker.domain.telegram import TelegramApp, TelegramLoginProblem
from tracker.infrastructure.telegram.login import TelethonLoginGateway
from tracker.services.setup import values
from tracker.services.setup.models import StepGroup, StepName
from tracker.services.setup.skipped_steps import SKIPPED_STEPS
from tracker.services.setup.step_telegram import (
    API_HASH,
    API_ID,
    SESSION,
    TELEGRAM_OFFER,
    TelegramStep,
)
from tracker.services.setup.wizard import SetupWizard, default_steps
from tracker.shared.constants.telegram import TELEGRAM_APPS_PAGE
from tracker.shared.errors import (
    SourceUnavailableError,
    TelegramLoginError,
    ValidationFailedError,
)

pytestmark = pytest.mark.asyncio

_PASSWORD = "correct horse battery"
#: The phone number as a person types it.
_PHONE_TYPED = "+39 333 123 4567"
#: The application's two values, as pasted from my.telegram.org.
_APP: list[str | bool] = [GOOD_TELEGRAM_API_ID, GOOD_TELEGRAM_API_HASH]
_SAVED_APP: dict[str, str] = {API_ID: GOOD_TELEGRAM_API_ID, API_HASH: GOOD_TELEGRAM_API_HASH}


def _by_name(*answers: str | bool, env: dict[str, str] | None = None) -> World:
    """A world where ``tracker setup telegram`` was typed: the step asks nothing first."""
    return make_world(list(answers), configured_env() | (env or {}))


async def _run_by_name(world: World) -> bool:
    return await SetupWizard(world.context(), default_steps()).run_one(StepName.TELEGRAM)


def _telegram_values(world: World) -> dict[str, str]:
    return {name: value for name, value in world.env.values.items() if name.startswith("TELEGRAM")}


# --- By name: only what the person must do --------------------------------------


async def test_by_name_it_walks_through_the_app_and_logs_in_asking_nothing_else() -> None:
    world = _by_name(*_APP, _PHONE_TYPED, GOOD_TELEGRAM_CODE)

    assert await _run_by_name(world)

    assert _telegram_values(world) == {
        API_ID: GOOD_TELEGRAM_API_ID,
        API_HASH: GOOD_TELEGRAM_API_HASH,
        SESSION: TELEGRAM_SESSION_VALUE,
    }
    assert world.io.asked == [
        "App api_id",
        "App api_hash (it stays hidden)",
        "Your phone number for Telegram, with its country code",
        "The code",
    ]
    assert world.io.opened == [TELEGRAM_APPS_PAGE]
    assert world.telegram.phones == [GOOD_TELEGRAM_PHONE]
    assert world.telegram.disconnected == 1
    text = world.io.text()
    assert "'API development tools'" in text
    assert "App title: Threadline, Short name: threadline" in text
    assert "'ERROR'" in text
    assert "Logged in to Telegram as Sam Rivera." in text
    assert "Telegram > Settings > Devices" in text


async def test_the_values_are_sent_to_github_straight_away_as_secrets() -> None:
    world = _by_name(*_APP, _PHONE_TYPED, GOOD_TELEGRAM_CODE)

    await _run_by_name(world)

    assert world.github.secrets == {
        API_ID: GOOD_TELEGRAM_API_ID,
        API_HASH: GOOD_TELEGRAM_API_HASH,
        SESSION: TELEGRAM_SESSION_VALUE,
    }
    assert world.github.variables == {}
    assert not any("Send them to" in prompt for prompt in world.io.asked)


async def test_without_a_copy_on_github_it_says_the_command_that_sends_them() -> None:
    world = _by_name(*_APP, _PHONE_TYPED, GOOD_TELEGRAM_CODE)
    world.github.signed_in = False

    await _run_by_name(world)

    assert world.github.secrets == {}
    assert "To send them later, run: uv run tracker setup github" in world.io.text()


async def test_the_saved_login_the_hash_and_the_password_are_never_shown() -> None:
    world = _by_name(*_APP, _PHONE_TYPED, GOOD_TELEGRAM_CODE, _PASSWORD)
    world.telegram.password = _PASSWORD

    await _run_by_name(world)

    text = world.io.text()
    assert TELEGRAM_SESSION_VALUE not in text
    assert GOOD_TELEGRAM_API_HASH not in text
    assert _PASSWORD not in text
    assert _PASSWORD not in world.env.values.values()
    assert _PASSWORD not in world.github.secrets.values()


async def test_a_two_step_password_is_asked_hidden_and_used_once() -> None:
    world = _by_name(*_APP, _PHONE_TYPED, GOOD_TELEGRAM_CODE, "wrong", _PASSWORD)
    world.telegram.password = _PASSWORD

    assert await _run_by_name(world)

    assert world.telegram.passwords == ["wrong", _PASSWORD]
    assert world.io.secret_prompts.count("Your Telegram password (it stays hidden)") == 2
    assert "  made-up refusal: password_wrong. Please try again." in world.io.said
    assert world.env.get(SESSION) == TELEGRAM_SESSION_VALUE


async def test_a_wrong_code_is_asked_again() -> None:
    world = _by_name(*_APP, _PHONE_TYPED, "00000", GOOD_TELEGRAM_CODE)

    assert await _run_by_name(world)

    assert world.telegram.codes == ["00000", GOOD_TELEGRAM_CODE]
    assert world.env.get(SESSION) == TELEGRAM_SESSION_VALUE


async def test_a_refused_phone_number_is_asked_again() -> None:
    world = _by_name(*_APP, "+39 000 000 0000", _PHONE_TYPED, GOOD_TELEGRAM_CODE)

    assert await _run_by_name(world)

    assert world.telegram.phones == ["+390000000000", GOOD_TELEGRAM_PHONE]


async def test_a_refused_app_is_asked_for_again_on_a_new_connection() -> None:
    world = _by_name("7654321", GOOD_TELEGRAM_API_HASH, _PHONE_TYPED, *_APP, GOOD_TELEGRAM_CODE)

    assert await _run_by_name(world)

    assert world.telegram.opened == [7654321, int(GOOD_TELEGRAM_API_ID)]
    assert world.env.get(API_ID) == GOOD_TELEGRAM_API_ID
    assert world.io.opened == [TELEGRAM_APPS_PAGE, TELEGRAM_APPS_PAGE]


async def test_an_expired_code_stops_the_step_and_saves_nothing() -> None:
    world = _by_name(*_APP, _PHONE_TYPED, GOOD_TELEGRAM_CODE)
    world.telegram.code_expired = True

    assert not await _run_by_name(world)

    assert _telegram_values(world) == {}
    assert world.telegram.disconnected == 1
    assert "uv run tracker setup telegram" in world.io.text()


async def test_too_many_tries_stops_at_once_without_asking_for_a_code() -> None:
    world = _by_name(*_APP, _PHONE_TYPED)
    world.telegram.too_many_tries = True

    assert not await _run_by_name(world)

    assert "The code" not in world.io.asked
    assert _telegram_values(world) == {}


async def test_telegram_out_of_reach_stops_the_step_cleanly() -> None:
    world = _by_name(*_APP, _PHONE_TYPED)
    world.telegram.unreachable = True

    assert not await _run_by_name(world)

    assert "Stopped: Telegram could not be reached." in world.io.text()


async def test_logging_in_again_reuses_the_saved_app_and_asks_only_phone_and_code() -> None:
    world = _by_name(
        _PHONE_TYPED, GOOD_TELEGRAM_CODE, env=_SAVED_APP | {SESSION: "1BVold-ended-session"}
    )

    assert await _run_by_name(world)

    assert world.io.asked == ["Your phone number for Telegram, with its country code", "The code"]
    assert world.io.opened == []
    assert world.env.get(SESSION) == TELEGRAM_SESSION_VALUE
    assert world.github.secrets == {SESSION: TELEGRAM_SESSION_VALUE}


# --- In a run of every extra: one question, remembered --------------------------


async def test_in_the_extras_a_no_is_remembered_and_not_asked_again() -> None:
    world = make_world([False], configured_env())
    step = TelegramStep()

    await step.run(world.context())
    world.io.answers.clear()
    await step.run(world.context())

    assert world.io.asked == [TELEGRAM_OFFER]
    assert "telegram" in (world.env.get(SKIPPED_STEPS) or "")
    assert "Skipped earlier. To add it: uv run tracker setup telegram" in world.io.text()
    assert not await step.is_done(world.context())


async def test_in_the_extras_a_yes_goes_straight_on() -> None:
    world = make_world([True, *_APP, _PHONE_TYPED, GOOD_TELEGRAM_CODE], configured_env())

    await TelegramStep().run(world.context())

    assert await TelegramStep().is_done(world.context())


async def test_asking_by_name_forgets_an_earlier_no() -> None:
    world = _by_name(*_APP, _PHONE_TYPED, GOOD_TELEGRAM_CODE, env={SKIPPED_STEPS: "telegram"})

    assert await _run_by_name(world)

    assert TELEGRAM_OFFER not in world.io.asked
    assert world.env.get(SESSION) == TELEGRAM_SESSION_VALUE


async def test_telegram_is_an_extra() -> None:
    assert StepName.TELEGRAM.group is StepGroup.EXTRAS


# --- What is typed ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("typed", "cleaned"),
    [
        ("+39 333 123 4567", "+393331234567"),
        ("0039 (333) 123-4567", "+393331234567"),
        ("+1 415 555 0100", "+14155550100"),
    ],
)
async def test_a_phone_number_is_read_with_its_country_code(typed: str, cleaned: str) -> None:
    assert values.phone_number(typed) == cleaned


@pytest.mark.parametrize("typed", ["333 123 4567", "+12", "call me", ""])
async def test_a_phone_number_without_a_country_code_is_refused(typed: str) -> None:
    with pytest.raises(ValidationFailedError):
        values.phone_number(typed)


async def test_the_app_values_are_checked_before_telegram_sees_them() -> None:
    assert values.telegram_api_id(" 1234567 ") == 1234567
    assert values.telegram_api_hash(GOOD_TELEGRAM_API_HASH.upper()) == GOOD_TELEGRAM_API_HASH
    with pytest.raises(ValidationFailedError):
        values.telegram_api_id("12ab")
    with pytest.raises(ValidationFailedError) as caught:
        values.telegram_api_hash("not-a-hash")
    assert "not-a-hash" not in caught.value.message


# --- The Telethon login, with a fake client ---------------------------------------


@dataclass
class FakeLoginClient:
    """The Telethon client calls a login makes, answering like Telegram."""

    on_send_code: Exception | None = None
    on_code: Exception | None = None
    on_password: Exception | None = None
    calls: list[tuple[str, Any]] = field(default_factory=list)
    disconnects: int = 0
    session: Any = field(default_factory=lambda: _FakeSession())

    async def connect(self) -> None:
        self.calls.append(("connect", None))

    async def disconnect(self) -> None:
        self.disconnects += 1

    async def send_code_request(self, phone: str) -> None:
        self.calls.append(("send_code", phone))
        if self.on_send_code is not None:
            raise self.on_send_code

    async def sign_in(
        self, phone: str | None = None, code: str | None = None, *, password: str | None = None
    ) -> None:
        self.calls.append(("sign_in", (phone, code) if password is None else "password"))
        failure = self.on_code if password is None else self.on_password
        if failure is not None:
            raise failure

    async def get_me(self) -> Any:
        return types.User(id=42, first_name="Sam", last_name="Rivera")


class _FakeSession:
    def save(self) -> str:
        return TELEGRAM_SESSION_VALUE


_GOOD_APP = TelegramApp(int(GOOD_TELEGRAM_API_ID), SecretStr(GOOD_TELEGRAM_API_HASH))


def _gateway(client: FakeLoginClient) -> TelethonLoginGateway:
    return TelethonLoginGateway(lambda _app: cast(TelegramClient, client))


async def test_a_login_without_a_password_hands_back_the_session_and_the_name() -> None:
    client = FakeLoginClient()

    async with _gateway(client).open(_GOOD_APP) as flow:
        await flow.send_code(GOOD_TELEGRAM_PHONE)
        needs_password = await flow.enter_code(GOOD_TELEGRAM_CODE)
        login = await flow.finish()

    assert needs_password is False
    assert login.session.get_secret_value() == TELEGRAM_SESSION_VALUE
    assert login.account_name == "Sam Rivera"
    assert client.calls[2] == ("sign_in", (GOOD_TELEGRAM_PHONE, GOOD_TELEGRAM_CODE))
    assert client.disconnects == 1


async def test_an_account_with_a_password_says_so_after_the_code() -> None:
    client = FakeLoginClient(on_code=errors.SessionPasswordNeededError(request=None))

    async with _gateway(client).open(_GOOD_APP) as flow:
        await flow.send_code(GOOD_TELEGRAM_PHONE)
        assert await flow.enter_code(GOOD_TELEGRAM_CODE) is True
        await flow.enter_password(SecretStr(_PASSWORD))

    assert client.calls[-1] == ("sign_in", "password")


@pytest.mark.parametrize(
    ("raised", "problem"),
    [
        (errors.ApiIdInvalidError(request=None), TelegramLoginProblem.APP_REFUSED),
        (errors.PhoneNumberInvalidError(request=None), TelegramLoginProblem.PHONE_REFUSED),
        (errors.FloodWaitError(request=None, capture=600), TelegramLoginProblem.TOO_MANY_TRIES),
    ],
)
async def test_what_telegram_answers_to_the_phone_is_a_problem_the_step_tells_apart(
    raised: Exception, problem: TelegramLoginProblem
) -> None:
    client = FakeLoginClient(on_send_code=raised)

    with pytest.raises(TelegramLoginError) as caught:
        async with _gateway(client).open(_GOOD_APP) as flow:
            await flow.send_code(GOOD_TELEGRAM_PHONE)

    assert caught.value.problem == problem
    assert caught.value.__cause__ is None
    assert client.disconnects == 1


@pytest.mark.parametrize(
    ("raised", "problem"),
    [
        (errors.PhoneCodeInvalidError(request=None), TelegramLoginProblem.CODE_WRONG),
        (errors.PhoneCodeExpiredError(request=None), TelegramLoginProblem.CODE_EXPIRED),
    ],
)
async def test_what_telegram_answers_to_the_code_is_told_apart(
    raised: Exception, problem: TelegramLoginProblem
) -> None:
    client = FakeLoginClient(on_code=raised)

    with pytest.raises(TelegramLoginError) as caught:
        async with _gateway(client).open(_GOOD_APP) as flow:
            await flow.enter_code("1")

    assert caught.value.problem == problem


async def test_a_wrong_password_is_told_apart_and_never_repeated() -> None:
    client = FakeLoginClient(on_password=errors.PasswordHashInvalidError(request=None))

    with pytest.raises(TelegramLoginError) as caught:
        async with _gateway(client).open(_GOOD_APP) as flow:
            await flow.enter_password(SecretStr(_PASSWORD))

    assert caught.value.problem == TelegramLoginProblem.PASSWORD_WRONG
    assert _PASSWORD not in caught.value.message


async def test_telegram_out_of_reach_during_a_login_is_an_outage() -> None:
    client = FakeLoginClient(on_send_code=ConnectionError("down"))

    with pytest.raises(SourceUnavailableError):
        async with _gateway(client).open(_GOOD_APP) as flow:
            await flow.send_code(GOOD_TELEGRAM_PHONE)
