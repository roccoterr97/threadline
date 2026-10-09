"""Send the morning summary from the owner's own mailbox, and record that it went.

``tracker summary build`` writes the summary file; this sends it, exactly as it
was built, to the one address the owner configured. The file is read as
untrusted: a recipient or a subject prefix that differs from the settings means
the file was changed after Python wrote it, and nothing is sent.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Final, Protocol
from uuid import UUID

from pydantic import ValidationError

from tracker.domain.enums import RunStep
from tracker.domain.models import RunLog
from tracker.infrastructure.smtp import SmtpAccount
from tracker.schemas.summary import SummaryEmail
from tracker.services.runs.run_recorder import RunRecorder, StepOutcome, StepResult
from tracker.services.summary.once_a_day import OnceADay, sent_outcome
from tracker.services.summary.send_once import SendOnce
from tracker.shared.config import Settings
from tracker.shared.constants.mailbox import IMAP_PRESETS, DeliveryRoute
from tracker.shared.errors import ConfigurationError, TrackerError, ValidationFailedError
from tracker.shared.logging import get_logger

_log = get_logger(__name__)


#: Unicode categories of control characters and line and paragraph separators.
_NOT_TEXT_CATEGORIES: Final[frozenset[str]] = frozenset({"Cc", "Zl", "Zp"})


class Mailer(Protocol):
    """Hands one message to the owner's mail server."""

    def send(self, message: EmailMessage) -> None:
        """Send it."""
        ...


def smtp_account(settings: Settings) -> SmtpAccount:
    """Describe the server the summary is sent through.

    Args:
        settings: The process configuration.

    Returns:
        The provider's sending server (or ``SMTP_HOST``), signed in to with the
        IMAP mailbox's name — the same app password opens both.

    Raises:
        ConfigurationError: If no IMAP mailbox is set up, or a custom provider
            has no sending server.
    """
    if not settings.imap_enabled:
        message = (
            "sending the summary by SMTP needs a Gmail or other IMAP mailbox: "
            "MAIL_SOURCES must include imap"
        )
        raise ConfigurationError(message)
    host, port = settings.smtp_server
    if not host:
        message = "SMTP_HOST is needed to send the summary from a custom mailbox"
        raise ConfigurationError(message)
    preset = IMAP_PRESETS[settings.imap_provider]
    username = settings.imap_username or ""
    return SmtpAccount(host, port, username, preset.label, preset.company)


def compose(summary: SummaryEmail, sender: str) -> EmailMessage:
    """Build the message: the plain body with the HTML body as its alternative.

    Args:
        summary: The summary exactly as Python built it.
        sender: The address it is sent from.

    Returns:
        A multipart/alternative message with the file's subject, unchanged.
    """
    message = EmailMessage()
    message["From"] = sender
    message["To"] = summary.recipient
    message["Subject"] = summary.subject
    message.set_content(summary.text_body)
    message.add_alternative(summary.html_body, subtype="html")
    return message


def read_summary(path: Path) -> SummaryEmail:
    """Read the summary file.

    Args:
        path: The file ``tracker summary build`` wrote.

    Returns:
        The summary.

    Raises:
        ValidationFailedError: If the file is missing or not a summary.
    """
    try:
        return SummaryEmail.model_validate_json(path.read_text(encoding="utf-8"))
    except OSError as error:
        message = f"the summary file {path} could not be read - run 'tracker summary build' first"
        raise ValidationFailedError(message) from error
    except ValidationError as error:
        message = f"{path} is not a summary built by 'tracker summary build'"
        raise ValidationFailedError(message) from error


def _has_control_character(text: str) -> bool:
    """Whether a header value holds a line break or another character that is not text."""
    return any(unicodedata.category(character) in _NOT_TEXT_CATEGORIES for character in text)


@dataclass(frozen=True, slots=True)
class SentSummary:
    """A summary that went out.

    Attributes:
        summary: What was sent.
        step_error_code: Why the ``summary_email`` step could not be recorded
            afterwards, or ``None`` when it was.
    """

    summary: SummaryEmail
    step_error_code: str | None = None


@dataclass(frozen=True, slots=True)
class SkippedSummary:
    """A summary not sent because another daily run sent today's already.

    Attributes:
        earlier: The run whose summary already went out today.
    """

    earlier: RunLog


class SummarySender:
    """Sends the summary file to the configured recipient and records the step."""

    def __init__(
        self,
        settings: Settings,
        mailer_for: Callable[[], Mailer],
        recorder: RunRecorder,
        once_a_day: OnceADay,
    ) -> None:
        """Bind the sender to the settings, a mail server and the run log.

        Args:
            settings: Where the summary may go, and how it must start.
            mailer_for: Builds the mailer; called only once the file passed its
                checks, so a missing password is recorded like any failure.
            recorder: Records the ``summary_email`` step.
            once_a_day: Finds a summary another daily run sent earlier today.
        """
        self._settings = settings
        self._mailer_for = mailer_for
        self._recorder = recorder
        self._once_a_day = once_a_day

    def send(
        self, path: Path, run_id: UUID | None = None, *, send_again: bool = False
    ) -> SentSummary | SkippedSummary:
        """Send the summary and record the step, whether it went or not.

        Args:
            path: The summary file.
            run_id: The run to record against; the daily run still open when
                omitted.
            send_again: Send even when another daily run already sent
                today's summary.

        Returns:
            What was sent, and the code that kept the step from being recorded
            when the mail went but the run log could not say so; or, when
            today's summary already went out with another run, the skip,
            already recorded.

        Raises:
            ValidationFailedError: If this run's summary already went out; nothing
                is sent and nothing is recorded.
            TrackerError: If anything stopped the sending; the step is recorded
                as failed with the error's code first.
        """
        run = self._recorder.resolve(run_id)
        once = SendOnce(self._recorder, path)
        if once.already_sent(run.id):
            _log.info("summary_already_sent", run_id=str(run.id))
            message = "this run's summary was already sent, so it was not sent again"
            raise ValidationFailedError(message)
        earlier = self._once_a_day.skip_if_sent_today(run, self._recorder, send_again=send_again)
        if earlier is not None:
            return SkippedSummary(earlier=earlier)
        try:
            summary = self._checked(read_summary(path))
            self._mailer_for().send(compose(summary, self._sender()))
        except TrackerError as error:
            outcome = StepOutcome(RunStep.SUMMARY_EMAIL, StepResult.FAILED, error_code=error.code)
            self._recorder.record_step(run.id, outcome)
            _log.warning("summary_not_sent", run_id=str(run.id), code=error.code)
            raise
        once.remember(run.id)
        _log.info("summary_sent", run_id=str(run.id))
        return SentSummary(summary=summary, step_error_code=self._record_success(run.id))

    def _record_success(self, run_id: UUID) -> str | None:
        """Record that the summary went, and hand back the code when that failed.

        The mail is already in the owner's inbox by now, so a failure here is
        reported, never raised: an error would read as "not sent" and invite a
        second copy. The marker beside the file still stops one.
        """
        try:
            self._recorder.record_step(run_id, sent_outcome())
        except TrackerError as error:
            _log.error("summary_sent_step_not_recorded", run_id=str(run_id), code=error.code)
            return error.code
        return None

    def _checked(self, summary: SummaryEmail) -> SummaryEmail:
        """Refuse a file whose recipient or subject is not what the settings say."""
        settings = self._settings
        if settings.summary_route is not DeliveryRoute.SMTP:
            message = (
                "SUMMARY_DELIVERY is gmail_connector: this summary is sent through "
                "the Gmail connector, not by this command"
            )
            raise ConfigurationError(message)
        if summary.recipient != settings.summary_recipient_address:
            message = "the summary file names a different recipient than your settings"
            raise ValidationFailedError(message)
        if _has_control_character(summary.subject):
            message = "the summary subject holds a line break or another control character"
            raise ValidationFailedError(message)
        prefix = settings.summary_subject_prefix
        if summary.subject_prefix != prefix or not summary.subject.startswith(prefix):
            message = "the summary subject does not start with your subject prefix"
            raise ValidationFailedError(message)
        return summary

    def _sender(self) -> str:
        """The address the summary comes from: the mailbox's own, else the owner's first."""
        username = self._settings.imap_username or ""
        return username if "@" in username else self._settings.owner_email_addresses[0]
