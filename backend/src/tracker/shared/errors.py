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


class DatabaseStructureMissingError(TrackerError):
    """The database lacks a table, column or function a newer structure file adds."""

    code = "database_structure_missing"


class SourceUnavailableError(TrackerError):
    """An external message source (LinkedIn, Microsoft Graph) is unreachable."""

    code = "source_unavailable"


class SourceFailedError(TrackerError):
    """A source stopped on something nobody planned for.

    The collection hands this back in place of the unexpected error, so one
    source's surprise is recorded as that source's failed step and the other
    sources are still read. The surprise itself is logged by its type only: its
    text could carry a piece of somebody's mail.
    """

    code = "source_failed"


class SourceRequestRejectedError(SourceUnavailableError):
    """A service understood a request but refused to carry it out (a 4xx answer).

    It is set apart from an outage because sending the same request again a
    moment later can work, and because the service's own reason is worth
    showing.
    """

    code = "source_request_rejected"


class SiteNameTakenError(SourceRequestRejectedError):
    """Netlify refused a new site's name because another site already has it.

    The set-up answers it by trying another name, so it is set apart from
    every other refusal.
    """

    code = "site_name_taken"


class DashboardPackageError(TrackerError):
    """The prebuilt dashboard is not what it should be.

    Its checksum does not match, it is too large, or it holds a file that
    would land outside the site (an absolute path, ``..``, a link). Nothing
    from it is published.
    """

    code = "dashboard_package_invalid"


class DashboardProvenanceError(DashboardPackageError):
    """GitHub could not confirm that the template's own workflow built the dashboard.

    The checksum only proves the download is whole; the signed build
    provenance proves who built it. Nothing from the download is published.
    """

    code = "dashboard_provenance_unconfirmed"


class DownloadTooLargeError(TrackerError):
    """A download was larger than the most it may be, so it was stopped."""

    code = "download_too_large"


class DashboardBuildError(TrackerError):
    """Building the dashboard on this computer with Node.js did not finish."""

    code = "dashboard_build_failed"


class DashboardDeployError(TrackerError):
    """The host did not put the dashboard live: its deploy failed or never finished."""

    code = "dashboard_deploy_failed"


class DashboardPrivateError(DashboardDeployError):
    """The dashboard is live but its host keeps it behind the host's own login.

    New Netlify teams make every new project private, and Netlify's API offers
    no way to change that, so the owner switches it to public by hand.
    """

    code = "dashboard_private"


class SourceAuthError(TrackerError):
    """An external message source rejected the credentials we hold."""

    code = "source_auth_failed"


class SourcePermissionError(SourceAuthError):
    """A service accepted the credentials, but they lack the access one request needs.

    Supabase answers a limited (scoped) access token this way, so the set-up
    can say how to make a token that may do everything, rather than calling a
    good token wrong.
    """

    code = "source_permission_missing"


class LinkedInSignInError(SourceAuthError):
    """Signing in to LinkedIn with the owner's own application did not end with a key.

    Attributes:
        problem: Why, as far as the set-up must tell apart; a
            :class:`~tracker.domain.linkedin_sign_in.SignInProblem` value.
    """

    code = "linkedin_sign_in_failed"

    def __init__(self, message: str, problem: str) -> None:
        """Store the owner-facing message and why it happened.

        Args:
            message: Short, plain explanation, free of secrets.
            problem: Why, as a ``SignInProblem`` value.
        """
        super().__init__(message)
        self.problem = problem


class MailboxPasswordError(SourceAuthError):
    """A standard (IMAP) mailbox refused its app password, or none is saved.

    It has its own code so the morning summary can say which provider refused
    and that a new app password is the fix, rather than a Microsoft sign-in.
    """

    code = "mailbox_password_refused"


class MailboxWindowCappedError(TrackerError):
    """A mailbox held more new mail than is read at once; its oldest part was left unread.

    The collector hands it back on its report after storing what was read,
    rather than raising it: the run counts the mailbox as collected and assesses
    what was stored, and records the step as failed with this code so the owner
    is told. Only a collection typed by hand raises it, once it has stored.
    """

    code = "mailbox_window_capped"


class RunAlreadyGoingError(TrackerError):
    """Another run of the same kind is still going, so a second one was not opened."""

    code = "run_already_going"


class SetupStoppedError(TrackerError):
    """The person running the set-up stopped it, or walked away from its page."""

    code = "setup_stopped"


class ValidationFailedError(TrackerError):
    """Data did not satisfy a rule the application guarantees."""

    code = "validation_failed"


class WorkflowNotEnabledError(TrackerError):
    """GitHub would not switch on Actions, or the Threadline workflow, in the owner's copy."""

    code = "workflow_not_enabled"


class WorkflowNotStartedError(TrackerError):
    """GitHub did not start the Threadline workflow when asked to."""

    code = "workflow_not_started"


class WorkFileError(TrackerError):
    """A file exchanged with the assistant could not be removed after use."""

    code = "work_file_not_removed"
