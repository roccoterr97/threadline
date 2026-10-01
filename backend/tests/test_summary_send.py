"""Sending the summary by SMTP: exactly as built, only to the configured recipient."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

import pytest
from pydantic import SecretStr

from tests.conftest import FakeSupabaseClient, as_client
from tests.summary_world import NOW, TODAYS_RUN, sample_client
from tracker.domain.enums import RunStatus, RunStep
from tracker.infrastructure.smtp import SmtpAccount, SmtpMailer
from tracker.repositories import build_repositories
from tracker.schemas.summary import SummaryEmail
from tracker.services.runs.run_recorder import RunRecorder
from tracker.services.summary.builder import SummaryBuilder
from tracker.services.summary.sender import SummarySender, smtp_account
from tracker.shared import config
from tracker.shared.clock import FixedClock
from tracker.shared.config import Settings
from tracker.shared.constants.mailbox import DeliveryRoute
from tracker.shared.constants.retry import SOURCE_REQUEST_ATTEMPTS
from tracker.shared.errors import (
    ConfigurationError,
    MailboxPasswordError,
    SourceUnavailableError,
    ValidationFailedError,
)

APP_PASSWORD = "abcdabcdabcdabcd"
MAILBOX = "sam.rivera@mailbox.example"


@pytest.fixture
def imap_settings(valid_environment: None, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """An owner who reads Gmail over IMAP, so the summary goes by SMTP."""
    monkeypatch.setenv("MAIL_SOURCES", "imap")
    monkeypatch.setenv("IMAP_PROVIDER", "gmail")
    monkeypatch.setenv("IMAP_USERNAME", MAILBOX)
    config.reset_settings_cache()
    return config.get_settings()


class FakeSmtp:
    """Records what the mailer asked of the server; fails where told to."""

    def __init__(self, *, refuse_login: bool = False, refuse_send: bool = False) -> None:
        self.calls: list[str] = []
        self.sent: list[EmailMessage] = []
        self.refuse_login = refuse_login
        self.refuse_send = refuse_send

    def starttls(self, *, context: ssl.SSLContext) -> object:
        self.calls.append("starttls")
        return context

    def login(self, user: str, password: str) -> object:
        self.calls.append(f"login {user}")
        if self.refuse_login:
            raise smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted")
        return None

    def send_message(self, msg: EmailMessage) -> object:
        if self.refuse_send:
            raise smtplib.SMTPDataError(554, b"rejected")
        self.sent.append(msg)
        return {}

    def quit(self) -> object:
        self.calls.append("quit")
        return None


def mailer_on(server: FakeSmtp, port: int = 465) -> SmtpMailer:
    account = SmtpAccount("smtp.gmail.com", port, MAILBOX, "Gmail", "Google")
    return SmtpMailer(
        account, SecretStr(APP_PASSWORD), connect=lambda *_: server, sleep=lambda _: None
    )


def written_summary(settings: Settings, folder: Path, client: FakeSupabaseClient) -> Path:
    repositories = build_repositories(as_client(client))
    email = SummaryBuilder(repositories, settings, FixedClock(NOW)).build(TODAYS_RUN)
    path = folder / "summary.json"
    path.write_text(email.model_dump_json(), encoding="utf-8")
    return path


def reopen_todays_run(client: FakeSupabaseClient) -> None:
    """Put today's run back to running, as it is while the summary goes out."""
    for row in client.tables["run_logs"]:
        if row["id"] == str(TODAYS_RUN):
            row["status"] = RunStatus.RUNNING.value
            row["finished_at"] = None


def sender_for(settings: Settings, client: FakeSupabaseClient, mailer: SmtpMailer) -> SummarySender:
    reopen_todays_run(client)
    recorder = RunRecorder(build_repositories(as_client(client)), FixedClock(NOW))
    return SummarySender(settings, lambda: mailer, recorder)


def summary_step(client: FakeSupabaseClient) -> dict[str, object]:
    rows = [
        row
        for row in client.tables["run_step_logs"]
        if row["step"] == RunStep.SUMMARY_EMAIL.value and row["run_id"] == str(TODAYS_RUN)
    ]
    assert len(rows) == 1
    return rows[0]


def test_a_summary_already_sent_for_this_run_is_not_sent_again(
    imap_settings: Settings, tmp_path: Path
) -> None:
    client = sample_client()
    path = written_summary(imap_settings, tmp_path, client)
    server = FakeSmtp()
    sender = sender_for(imap_settings, client, mailer_on(server))
    sender.send(path)

    with pytest.raises(ValidationFailedError, match="already sent"):
        sender.send(path)

    assert len(server.sent) == 1
    assert summary_step(client)["status"] == RunStatus.SUCCESS.value


def test_a_summary_that_failed_can_be_sent_again(imap_settings: Settings, tmp_path: Path) -> None:
    client = sample_client()
    path = written_summary(imap_settings, tmp_path, client)
    refused = sender_for(imap_settings, client, mailer_on(FakeSmtp(refuse_send=True)))
    with pytest.raises(SourceUnavailableError):
        refused.send(path)
    server = FakeSmtp()

    sender_for(imap_settings, client, mailer_on(server)).send(path)

    assert len(server.sent) == 1
    assert summary_step(client)["status"] == RunStatus.SUCCESS.value


def test_the_summary_goes_out_exactly_as_built(imap_settings: Settings, tmp_path: Path) -> None:
    client = sample_client()
    path = written_summary(imap_settings, tmp_path, client)
    built = SummaryEmail.model_validate_json(path.read_text(encoding="utf-8"))
    server = FakeSmtp()

    sender_for(imap_settings, client, mailer_on(server)).send(path, TODAYS_RUN)

    [message] = server.sent
    assert message["To"] == imap_settings.summary_recipient_address
    assert message["From"] == MAILBOX
    assert message["Subject"] == built.subject
    assert message.get_content_type() == "multipart/alternative"
    plain = message.get_body(("plain",))
    html = message.get_body(("html",))
    assert plain is not None and html is not None
    assert plain.get_content().rstrip("\n") == built.text_body.rstrip("\n")
    assert html.get_content().rstrip("\n") == built.html_body.rstrip("\n")
    assert server.calls == [f"login {MAILBOX}", "quit"]
    step = summary_step(client)
    assert step["status"] == RunStatus.SUCCESS.value
    assert step["items_new"] == 1


def test_port_587_is_encrypted_with_starttls_before_the_password() -> None:
    server = FakeSmtp()

    mailer_on(server, port=587).verify()

    assert server.calls == ["starttls", f"login {MAILBOX}", "quit"]
    assert server.sent == []


def test_a_refused_app_password_is_recorded_and_never_shown(
    imap_settings: Settings, tmp_path: Path
) -> None:
    client = sample_client()
    path = written_summary(imap_settings, tmp_path, client)

    with pytest.raises(MailboxPasswordError, match="Google refused the app password") as raised:
        sender_for(imap_settings, client, mailer_on(FakeSmtp(refuse_login=True))).send(path)

    assert APP_PASSWORD not in raised.value.message
    step = summary_step(client)
    assert step["status"] == RunStatus.FAILED.value
    assert step["error_code"] == "mailbox_password_refused"


def test_an_unreachable_server_is_tried_a_few_times_then_recorded(
    imap_settings: Settings, tmp_path: Path
) -> None:
    client = sample_client()
    path = written_summary(imap_settings, tmp_path, client)
    attempts: list[str] = []

    def unreachable(host: str, port: int, timeout: float) -> FakeSmtp:
        attempts.append(host)
        raise ConnectionRefusedError

    account = SmtpAccount("smtp.gmail.com", 465, MAILBOX, "Gmail", "Google")
    mailer = SmtpMailer(account, SecretStr(APP_PASSWORD), connect=unreachable, sleep=lambda _: None)

    with pytest.raises(SourceUnavailableError, match="Gmail could not send the summary"):
        sender_for(imap_settings, client, mailer).send(path)

    assert len(attempts) == SOURCE_REQUEST_ATTEMPTS
    assert summary_step(client)["error_code"] == "source_unavailable"


def test_a_refused_message_is_not_sent_twice(imap_settings: Settings, tmp_path: Path) -> None:
    client = sample_client()
    path = written_summary(imap_settings, tmp_path, client)
    server = FakeSmtp(refuse_send=True)

    with pytest.raises(SourceUnavailableError):
        sender_for(imap_settings, client, mailer_on(server)).send(path)

    assert server.calls.count(f"login {MAILBOX}") == 1


def test_a_file_naming_another_recipient_sends_nothing(
    imap_settings: Settings, tmp_path: Path
) -> None:
    client = sample_client()
    path = written_summary(imap_settings, tmp_path, client)
    tampered = SummaryEmail.model_validate_json(path.read_text(encoding="utf-8")).model_copy(
        update={"recipient": "somebody@else.example"}
    )
    path.write_text(tampered.model_dump_json(), encoding="utf-8")
    server = FakeSmtp()

    with pytest.raises(ValidationFailedError, match="different recipient"):
        sender_for(imap_settings, client, mailer_on(server)).send(path)

    assert server.sent == []
    assert server.calls == []
    assert summary_step(client)["error_code"] == "validation_failed"


def test_a_subject_without_the_prefix_sends_nothing(
    imap_settings: Settings, tmp_path: Path
) -> None:
    client = sample_client()
    path = written_summary(imap_settings, tmp_path, client)
    tampered = SummaryEmail.model_validate_json(path.read_text(encoding="utf-8")).model_copy(
        update={"subject": "Your day"}
    )
    path.write_text(tampered.model_dump_json(), encoding="utf-8")
    server = FakeSmtp()

    with pytest.raises(ValidationFailedError, match="subject prefix"):
        sender_for(imap_settings, client, mailer_on(server)).send(path)

    assert server.sent == []


def test_a_missing_file_is_recorded_as_failed(imap_settings: Settings, tmp_path: Path) -> None:
    client = sample_client()

    with pytest.raises(ValidationFailedError, match="summary build"):
        sender_for(imap_settings, client, mailer_on(FakeSmtp())).send(tmp_path / "absent.json")

    assert summary_step(client)["status"] == RunStatus.FAILED.value


def test_the_gmail_connector_route_refuses_to_send_by_smtp(
    imap_settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SUMMARY_DELIVERY", "gmail_connector")
    config.reset_settings_cache()
    settings = config.get_settings()
    client = sample_client()
    path = written_summary(settings, tmp_path, client)
    server = FakeSmtp()

    with pytest.raises(ConfigurationError, match="Gmail connector"):
        sender_for(settings, client, mailer_on(server)).send(path)

    assert server.sent == []


# --- The delivery setting ------------------------------------------------------


def test_an_imap_mailbox_sends_by_smtp_by_default(imap_settings: Settings) -> None:
    assert imap_settings.summary_route is DeliveryRoute.SMTP


def test_outlook_alone_leaves_the_summary_to_the_gmail_connector(
    settings_without_linkedin_key: Settings,
) -> None:
    assert settings_without_linkedin_key.summary_route is DeliveryRoute.GMAIL_CONNECTOR


def test_the_delivery_setting_wins_however_it_is_capitalised(
    valid_environment: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SUMMARY_DELIVERY", "SMTP")
    config.reset_settings_cache()

    assert config.get_settings().summary_route is DeliveryRoute.SMTP


@pytest.mark.parametrize(
    ("provider", "host", "port"),
    [
        ("gmail", "smtp.gmail.com", 465),
        ("icloud", "smtp.mail.me.com", 587),
        ("yahoo", "smtp.mail.yahoo.com", 465),
        ("fastmail", "smtp.fastmail.com", 465),
    ],
)
def test_each_provider_sends_through_its_own_server(
    valid_environment: None, monkeypatch: pytest.MonkeyPatch, provider: str, host: str, port: int
) -> None:
    monkeypatch.setenv("MAIL_SOURCES", "imap")
    monkeypatch.setenv("IMAP_PROVIDER", provider)
    monkeypatch.setenv("IMAP_USERNAME", MAILBOX)
    config.reset_settings_cache()

    account = smtp_account(config.get_settings())

    assert (account.host, account.port, account.username) == (host, port, MAILBOX)


def test_a_custom_mailbox_needs_its_sending_server(
    valid_environment: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MAIL_SOURCES", "imap")
    monkeypatch.setenv("IMAP_HOST", "imap.example.org")
    monkeypatch.setenv("IMAP_USERNAME", MAILBOX)
    config.reset_settings_cache()

    with pytest.raises(ConfigurationError, match="SMTP_HOST"):
        smtp_account(config.get_settings())

    monkeypatch.setenv("SMTP_HOST", "smtp.example.org")
    monkeypatch.setenv("SMTP_PORT", "587")
    config.reset_settings_cache()
    assert smtp_account(config.get_settings()).host == "smtp.example.org"
    assert smtp_account(config.get_settings()).port == 587


def test_without_an_imap_mailbox_there_is_nothing_to_send_from(
    settings_without_linkedin_key: Settings,
) -> None:
    with pytest.raises(ConfigurationError, match="MAIL_SOURCES"):
        smtp_account(settings_without_linkedin_key)
