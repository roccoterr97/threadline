"""The single error hierarchy for Threadline.

Every failure the application raises on purpose derives from :class:`TrackerError`
and carries a stable ``code``. The command-line entry point turns any
:class:`TrackerError` into one clean error line; internal driver messages and
stack traces never reach the operator or a future HTTP response.
"""

from __future__ import annotations


class TrackerError(Exception):
    """Base class for every error raised on purpose by Threadline.

    Attributes:
        code: Stable, machine-readable identifier safe to show to an operator.
    """

    code: str = "tracker_error"

    def __init__(self, message: str) -> None:
        """Store the operator-facing message.

        Args:
            message: Short explanation, free of secrets and of message content.
        """
        super().__init__(message)
        self.message = message


class ConfigurationError(TrackerError):
    """Configuration is missing, malformed, or inconsistent."""

    code = "configuration_invalid"


class DatabaseUnavailableError(TrackerError):
    """The database could not be reached or refused the request."""

    code = "database_unavailable"


class SourceUnavailableError(TrackerError):
    """An external message source (LinkedIn, Microsoft Graph) is unreachable."""

    code = "source_unavailable"


class SourceRequestRejectedError(SourceUnavailableError):
    """A service understood a request but refused to carry it out (a 4xx answer).

    It is set apart from an outage because sending the same request again a
    moment later can work, and because the service's own reason is worth
    showing.
    """

    code = "source_request_rejected"


class SourceAuthError(TrackerError):
    """An external message source rejected the credentials we hold."""

    code = "source_auth_failed"


class MailboxPasswordError(SourceAuthError):
    """A standard (IMAP) mailbox refused its app password, or none is saved.

    It has its own code so the morning summary can say which provider refused
    and that a new app password is the fix, rather than a Microsoft sign-in.
    """

    code = "mailbox_password_refused"


class ValidationFailedError(TrackerError):
    """Data did not satisfy a rule the application guarantees."""

    code = "validation_failed"


class WorkFileError(TrackerError):
    """A file exchanged with the assistant could not be removed after use."""

    code = "work_file_not_removed"
