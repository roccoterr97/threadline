"""The set-up's mailbox step, the optional Microsoft step and the doctor's IMAP check."""

from __future__ import annotations

import pytest

from tests.setup_world import (
    GOOD_APP_PASSWORD,
    OWNER_EMAIL,
    PROJECT_REF,
    World,
    configured_env,
    make_world,
)
from tracker.infrastructure.imap.reader import MailboxSurvey
from tracker.services.doctor.checks import ImapMailboxCheck, NotConnectedCheck, SmtpLoginCheck
from tracker.services.doctor.models import CheckStatus
from tracker.services.doctor.service import DoctorService
from tracker.services.setup.step_cloud import allowed_hosts
from tracker.services.setup.step_mailbox import MailboxStep
from tracker.services.setup.step_microsoft import MicrosoftStep
from tracker.shared.errors import MailboxPasswordError, ValidationFailedError

pytestmark = pytest.mark.asyncio

GMAIL = "sam.rivera@gmail.example"
GMAIL_PAGE = "https://myaccount.google.com/apppasswords"


# --- Choosing and connecting a mailbox ----------------------------------------


async def test_gmail_is_checked_live_then_saved_encrypted_and_never_in_env() -> None:
    world = make_world(["gmail", GMAIL, "wxyz wxyz wxyz wxyz", True], configured_env())

    await MailboxStep().run(world.context())

    account, tried = world.mailbox.checked[0]
    assert (account.host, account.port, account.username) == ("imap.gmail.com", 993, GMAIL)
    assert tried == GOOD_APP_PASSWORD
    assert world.mailbox.saved == {GMAIL: GOOD_APP_PASSWORD}
    assert GOOD_APP_PASSWORD not in " ".join(world.env.values.values())
    assert world.env.values["MAIL_SOURCES"] == "imap"
    assert world.env.values["IMAP_PROVIDER"] == "gmail"
    assert world.env.values["IMAP_USERNAME"] == GMAIL
    assert world.env.values["OWNER_EMAIL_ADDRESSES"] == GMAIL


async def test_the_step_explains_app_passwords_and_opens_the_providers_page() -> None:
    world = make_world(["gmail", GMAIL, GOOD_APP_PASSWORD, True], configured_env())

    await MailboxStep().run(world.context())

    text = world.io.text()
    assert "app password: a separate password just for Threadline" in text
    assert "2-Step Verification" in text
    assert world.io.opened == [GMAIL_PAGE]
    assert "Connected. Your inbox has 42 messages from the last 30 days." in text
    assert "'[Gmail]/Sent Mail'" in text
    assert world.io.secret_prompts == ["Paste the Gmail app password (it is not shown)"]


async def test_a_refused_password_is_asked_for_again() -> None:
    world = make_world(["gmail", GMAIL, "wrong", GOOD_APP_PASSWORD, True], configured_env())

    await MailboxStep().run(world.context())

    assert "  Google refused the app password. Please try again." in world.io.said
    assert world.mailbox.saved == {GMAIL: GOOD_APP_PASSWORD}


async def test_three_refusals_stop_the_step_and_save_nothing() -> None:
    world = make_world(["gmail", GMAIL, "a", "b", "c"], configured_env())

    with pytest.raises(MailboxPasswordError):
        await MailboxStep().run(world.context())

    assert world.mailbox.saved == {}
    assert "MAIL_SOURCES" not in world.env.values


async def test_another_provider_asks_for_its_server_and_port() -> None:
    answers: list[str | bool] = [
        "other",
        "Mail.Example.org",
        "",
        "sam",
        GOOD_APP_PASSWORD,
        "smtp.mail.example",
        "",
    ]
    world = make_world(answers, configured_env() | {"OWNER_EMAIL_ADDRESSES": OWNER_EMAIL})

    await MailboxStep().run(world.context())

    account, _ = world.mailbox.checked[0]
    assert (account.host, account.port, account.username) == ("mail.example.org", 993, "sam")
    assert world.env.values["IMAP_HOST"] == "mail.example.org"
    assert world.env.values["IMAP_PORT"] == "993"
    assert world.io.opened == []


def _custom_answers(*smtp: str | bool) -> list[str | bool]:
    """Another provider whose IMAP server is imap.mail.example, then the SMTP answers."""
    return ["other", "imap.mail.example", "", "sam", GOOD_APP_PASSWORD, *smtp]


async def test_another_provider_is_asked_its_sending_server_and_it_is_tried_live() -> None:
    world = make_world(_custom_answers("", "587"), configured_env())

    await MailboxStep().run(world.context())

    [sending] = world.mailbox.sending_checked
    assert (sending.host, sending.port, sending.username) == ("smtp.mail.example", 587, "sam")
    assert world.env.values["SMTP_HOST"] == "smtp.mail.example"
    assert world.env.values["SMTP_PORT"] == "587"
    assert "Nothing was sent" in world.io.text()


async def test_a_sending_server_that_cannot_be_reached_is_asked_again() -> None:
    world = make_world(
        _custom_answers("smtp.wrong.example", "", True, "smtp.mail.example", ""), configured_env()
    )

    await MailboxStep().run(world.context())

    assert [account.host for account in world.mailbox.sending_checked] == [
        "smtp.wrong.example",
        "smtp.mail.example",
    ]
    assert "Please check the server and port" in world.io.text()
    assert world.env.values["SMTP_HOST"] == "smtp.mail.example"
    assert world.env.values["SMTP_PORT"] == "465"


def _assert_mailbox_kept_without_sending(world: World) -> None:
    """The checked app password and the mailbox are saved; no sending server is."""
    assert world.mailbox.saved == {"sam": GOOD_APP_PASSWORD}
    assert world.env.values["IMAP_PROVIDER"] == "custom"
    assert world.env.values["IMAP_HOST"] == "imap.mail.example"
    assert world.env.values["MAIL_SOURCES"] == "imap"
    assert "SMTP_HOST" not in world.env.values
    text = world.io.text()
    assert "the morning summary cannot be e-mailed until the sending server works" in text
    assert "uv run tracker setup mailbox" in text


async def test_three_failed_sending_sign_ins_keep_the_checked_mailbox() -> None:
    wrong = ("smtp.wrong.example", "")
    world = make_world(_custom_answers(*wrong, True, *wrong, True, *wrong), configured_env())

    await MailboxStep().run(world.context())

    assert len(world.mailbox.sending_checked) == 3
    _assert_mailbox_kept_without_sending(world)


async def test_the_sending_server_can_be_left_for_later() -> None:
    world = make_world(_custom_answers("smtp.wrong.example", "", False), configured_env())

    await MailboxStep().run(world.context())

    assert len(world.mailbox.sending_checked) == 1
    _assert_mailbox_kept_without_sending(world)


async def test_a_refused_sending_password_can_be_left_for_later_too() -> None:
    world = make_world(_custom_answers("", "", False), configured_env())
    world.mailbox.smtp_refuses = True

    await MailboxStep().run(world.context())

    assert "refused the app password for sending" in world.io.text()
    _assert_mailbox_kept_without_sending(world)


async def test_a_sending_server_of_an_earlier_mailbox_is_forgotten_when_none_signs_in() -> None:
    env = configured_env() | {
        "IMAP_HOST": "imap.old.example",
        "IMAP_USERNAME": "sam",
        "SMTP_HOST": "smtp.old.example",
        "SMTP_PORT": "587",
    }
    world = make_world(_custom_answers("smtp.wrong.example", "", False), env)

    await MailboxStep().run(world.context())

    assert world.env.values["IMAP_HOST"] == "imap.mail.example"
    assert world.env.get("SMTP_HOST") is None
    assert world.env.get("SMTP_PORT") is None


async def test_the_same_mailbox_keeps_its_saved_sending_server_when_none_signs_in() -> None:
    env = configured_env() | {
        "IMAP_HOST": "imap.mail.example",
        "IMAP_USERNAME": "sam",
        "SMTP_HOST": "smtp.mail.example",
        "SMTP_PORT": "587",
    }
    world = make_world(_custom_answers("smtp.wrong.example", "", False), env)

    await MailboxStep().run(world.context())

    assert world.env.values["SMTP_HOST"] == "smtp.mail.example"
    assert world.env.values["SMTP_PORT"] == "587"


async def test_sending_server_names_that_never_pass_keep_the_checked_mailbox() -> None:
    unusable = "not a server"
    world = make_world(_custom_answers(unusable, unusable, unusable), configured_env())

    await MailboxStep().run(world.context())

    assert world.mailbox.sending_checked == []
    _assert_mailbox_kept_without_sending(world)


async def test_leaving_the_sending_server_for_later_says_how_to_add_it() -> None:
    world = make_world(_custom_answers("smtp.wrong.example", "", False), configured_env())

    await MailboxStep().run(world.context())

    text = world.io.text()
    assert "it asks for the app password" in text
    assert "uv run tracker setup github" in text


async def test_no_sending_server_is_asked_when_the_summary_goes_through_gmail() -> None:
    env = configured_env() | {"SUMMARY_DELIVERY": "gmail_connector"}
    world = make_world(_custom_answers(), env)

    await MailboxStep().run(world.context())

    assert world.mailbox.sending_checked == []
    assert "SMTP_HOST" not in world.env.values


async def test_a_built_in_provider_clears_a_sending_server_left_from_another() -> None:
    env = configured_env() | {
        "SMTP_HOST": "smtp.mail.example",
        "SMTP_PORT": "587",
        "OWNER_EMAIL_ADDRESSES": GMAIL,
    }
    world = make_world(["gmail", GMAIL, GOOD_APP_PASSWORD], env)

    await MailboxStep().run(world.context())

    assert world.mailbox.sending_checked == []
    assert world.env.get("SMTP_HOST") is None
    assert world.env.get("SMTP_PORT") is None


async def test_a_missing_sent_folder_is_said_plainly() -> None:
    world = make_world(["icloud", GMAIL, GOOD_APP_PASSWORD, True], configured_env())
    world.mailbox.sent_folder = None

    await MailboxStep().run(world.context())

    assert "No Sent folder was found" in world.io.text()


async def test_an_existing_outlook_user_is_asked_whether_to_keep_it() -> None:
    world = make_world(["yahoo", GMAIL, GOOD_APP_PASSWORD, True, True], configured_env())
    world.microsoft.signed_in = True

    await MailboxStep().run(world.context())

    assert world.env.values["MAIL_SOURCES"] == "outlook,imap"


async def test_switching_to_gmail_forgets_an_old_custom_server() -> None:
    env = configured_env() | {"IMAP_HOST": "mail.example.org", "IMAP_PORT": "143"}
    world = make_world(["gmail", GMAIL, GOOD_APP_PASSWORD, True], env)

    await MailboxStep().run(world.context())

    assert world.env.get("IMAP_HOST") is None
    assert world.env.get("IMAP_PORT") is None


async def test_choosing_outlook_hands_over_to_the_microsoft_step() -> None:
    world = make_world(["hotmail"], configured_env())

    await MailboxStep().run(world.context())

    assert world.env.values["MAIL_SOURCES"] == "outlook"
    assert world.mailbox.checked == []
    assert "uv run tracker setup microsoft" in world.io.text()


async def test_an_unknown_answer_is_asked_again_then_refused() -> None:
    world = make_world(["pigeon", "carrier", "raven"], configured_env())

    with pytest.raises(ValidationFailedError, match="gmail, outlook"):
        await MailboxStep().run(world.context())


@pytest.mark.parametrize(
    ("env", "saved", "done"),
    [
        ({}, {}, False),
        ({"MAIL_SOURCES": "outlook"}, {}, True),
        ({"MAIL_SOURCES": "imap", "IMAP_USERNAME": GMAIL}, {}, False),
        ({"MAIL_SOURCES": "imap", "IMAP_USERNAME": GMAIL}, {GMAIL: "x"}, True),
        ({"MAIL_SOURCES": "imap"}, {}, False),
    ],
)
async def test_the_step_is_done_once_a_mailbox_is_ready(
    env: dict[str, str], saved: dict[str, str], done: bool
) -> None:
    world = make_world([], configured_env() | env)
    world.mailbox.saved = saved

    assert await MailboxStep().is_done(world.context()) is done


# --- Outlook as an option -----------------------------------------------------


async def test_microsoft_is_optional_once_gmail_is_read() -> None:
    world = make_world([False], configured_env() | {"MAIL_SOURCES": "imap"})

    await MicrosoftStep().run(world.context())

    assert world.microsoft.accesses == []
    assert "Skipped. To add it later: uv run tracker setup microsoft" in world.io.said
    assert world.env.values["MAIL_SOURCES"] == "imap"


async def test_microsoft_can_be_added_beside_gmail() -> None:
    env = configured_env() | {"MAIL_SOURCES": "imap", "OWNER_EMAIL_ADDRESSES": OWNER_EMAIL}
    world = make_world([True], env)

    await MicrosoftStep().run(world.context())

    assert world.microsoft.signed_in
    assert world.env.values["MAIL_SOURCES"] == "outlook,imap"


async def test_the_cloud_is_told_the_imap_server_and_not_graph_without_outlook() -> None:
    env = configured_env() | {
        "MAIL_SOURCES": "imap",
        "IMAP_PROVIDER": "gmail",
        "IMAP_USERNAME": GMAIL,
    }
    world = make_world([], env)

    assert allowed_hosts(world.context()) == (f"{PROJECT_REF}.supabase.co", "imap.gmail.com")


async def test_the_cloud_keeps_graph_for_an_outlook_set_up() -> None:
    world = make_world([], configured_env())

    assert "graph.microsoft.com" in allowed_hosts(world.context())


# --- The doctor ---------------------------------------------------------------


def surveyed(sent_folder: str | None) -> ImapMailboxCheck:
    """An IMAP check whose mailbox answers with a made-up survey."""

    async def survey() -> MailboxSurvey:
        return MailboxSurvey(inbox_messages=7, sent_folder=sent_folder)

    return ImapMailboxCheck(survey, "Gmail")


async def test_the_imap_check_passes_when_inbox_and_sent_answer() -> None:
    result = await surveyed("[Gmail]/Sent Mail").run()

    assert result.status is CheckStatus.OK
    assert "your Gmail signed in and the inbox has 7 messages" in result.detail
    assert "'[Gmail]/Sent Mail'" in result.detail


async def test_the_imap_check_warns_without_a_sent_folder() -> None:
    result = await surveyed(None).run()

    assert result.status is CheckStatus.WARNING
    assert "no Sent folder was found" in result.detail


async def test_the_imap_check_is_skipped_without_an_imap_mailbox() -> None:
    result = await ImapMailboxCheck(None, "mailbox").run()

    assert result.status is CheckStatus.SKIPPED


async def test_a_refused_app_password_is_a_problem_with_the_fix() -> None:
    async def refused() -> MailboxSurvey:
        message = "Google refused the app password"
        raise MailboxPasswordError(message)

    report = await DoctorService([ImapMailboxCheck(refused, "Gmail")]).run()

    [result] = report.results
    assert result.status is CheckStatus.PROBLEM
    assert result.detail == "Google refused the app password"
    assert result.fix == "make a new app password, then run 'uv run tracker setup mailbox'"


async def test_outlook_checks_are_skipped_not_failed_without_outlook() -> None:
    report = await DoctorService([NotConnectedCheck("Calendar", "Outlook only")]).run()

    assert report.healthy
    assert report.results[0].status is CheckStatus.SKIPPED


async def test_the_smtp_check_signs_in_and_sends_nothing() -> None:
    signed_in: list[str] = []

    async def verify() -> None:
        signed_in.append("yes")

    result = await SmtpLoginCheck(verify, "Gmail").run()

    assert signed_in == ["yes"]
    assert result.status is CheckStatus.OK
    assert "nothing was sent" in result.detail


async def test_the_smtp_check_is_skipped_on_the_gmail_connector_route() -> None:
    result = await SmtpLoginCheck(None, "mailbox").run()

    assert result.status is CheckStatus.SKIPPED
    assert "Gmail connector" in result.detail
    assert "a run on GitHub cannot e-mail the summary" in result.detail


async def test_a_refused_sending_password_is_a_problem_with_the_fix() -> None:
    async def refused() -> None:
        message = "Google refused the app password for sending"
        raise MailboxPasswordError(message)

    report = await DoctorService([SmtpLoginCheck(refused, "Gmail")]).run()

    [result] = report.results
    assert result.status is CheckStatus.PROBLEM
    assert "refused the app password" in result.detail
    assert "setup mailbox" in result.fix
