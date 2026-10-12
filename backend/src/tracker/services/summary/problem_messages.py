"""Error codes turned into two plain sentences: what happened, what to do.

The owner is not a programmer, and a morning e-mail is the worst possible place
to meet a stack trace. Every failure therefore arrives here as a stable code and
leaves as words: one sentence naming what did not happen, one naming the next
move — which is often "nothing, the next run will try again".

A code nobody has written a sentence for still produces a useful message, never
the code itself. Nothing in this module reads the failure's own text, so a
message from someone's inbox cannot reach the summary through an error.
"""

from __future__ import annotations

from typing import Final

from tracker.domain.enums import RunStep
from tracker.schemas.summary import SummaryProblem
from tracker.shared.constants.mailbox import (
    IMAP_MAX_MESSAGES_PER_FOLDER,
    IMAP_PRESETS,
    ImapProvider,
)
from tracker.shared.constants.runs import RUN_INTERRUPTED_CODE
from tracker.shared.errors import (
    AdminApprovalRequiredError,
    MailboxPasswordError,
    MailboxWindowCappedError,
    SlackApprovalNeededError,
    SlackRateLimitedError,
    SlackTokenRefusedError,
    TelegramFloodWaitError,
    WorkAccountRequiredError,
)

#: What to do when there is, honestly, nothing to do.
_WAIT_IT_OUT: Final[str] = (
    "Nothing to do — the next run tries again. If the same thing appears three "
    "mornings running, see 'When something keeps failing' in docs/operations.md."
)

#: What to do when a run needs a human before it can work again.
_CHECK_THE_RUN_PAGE: Final[str] = (
    "Open the run page on the dashboard to see which part stopped. If tomorrow's "
    "summary says the same thing, see 'When something keeps failing' in "
    "docs/operations.md."
)

#: What to do when the Teams sign-in has to be made again.
_SIGN_IN_TO_TEAMS_AGAIN: Final[str] = (
    "Sign in to Teams again with your work or school account: run "
    "'uv run tracker setup teams' on your computer. It takes about a minute."
)

#: Sentences chosen by the step *and* the code, where the source matters.
_BY_STEP_AND_CODE: Final[dict[tuple[RunStep, str], tuple[str, str]]] = {
    (RunStep.COLLECT_LINKEDIN, "source_auth_failed"): (
        "LinkedIn would not accept its key this morning, so no new LinkedIn messages were read.",
        "Renew the LinkedIn key: run 'uv run tracker setup linkedin' on your computer "
        "and click 'Allow' on LinkedIn's page. The steps are in 'Renew the LinkedIn "
        "key' in docs/operations.md.",
    ),
    (RunStep.COLLECT_LINKEDIN, "source_unavailable"): (
        "LinkedIn did not answer this morning, so no new LinkedIn messages were read.",
        _WAIT_IT_OUT,
    ),
    (RunStep.COLLECT_EMAIL, "source_auth_failed"): (
        "Your mailbox could not be read this morning: Microsoft refused the saved sign-in.",
        "Sign in to Microsoft once more — it takes about a minute. The steps are "
        "in 'Redo the Microsoft sign-in' in docs/operations.md.",
    ),
    (RunStep.COLLECT_EMAIL, "source_unavailable"): (
        "Your mailbox did not answer this morning, so no new e-mails were read.",
        _WAIT_IT_OUT,
    ),
    (RunStep.COLLECT_EMAIL, MailboxWindowCappedError.code): (
        "Your mailbox had more new mail than Threadline reads in one go, so only "
        f"the newest {IMAP_MAX_MESSAGES_PER_FOLDER:,} messages of a folder were read "
        "and the older ones from that stretch were skipped.",
        "Nothing to do: everything recent was read. A skipped conversation is read "
        "in full as soon as somebody writes in it again.",
    ),
    (RunStep.COLLECT_CALENDAR, "source_auth_failed"): (
        "Your calendar could not be read this morning: Microsoft refused the saved sign-in.",
        "Sign in to Microsoft once more — it takes about a minute. The steps are "
        "in 'Redo the Microsoft sign-in' in docs/operations.md.",
    ),
    (RunStep.COLLECT_CALENDAR, "source_unavailable"): (
        "Your calendar did not answer this morning, so no new meetings were read.",
        _WAIT_IT_OUT,
    ),
    (RunStep.COLLECT_SLACK, SlackTokenRefusedError.code): (
        "Slack would not accept its saved key this morning, so no new Slack messages "
        "were read from that workspace.",
        "Connect Slack again: run 'uv run tracker setup slack' on your computer and "
        "paste a new User OAuth Token. The steps are in the Slack part of "
        "docs/setup-your-accounts.md.",
    ),
    (RunStep.COLLECT_SLACK, SlackApprovalNeededError.code): (
        "Slack would not let Threadline read a workspace this morning: your workspace "
        "admin must approve the Threadline app first.",
        "Ask your Slack admin to approve the app, then run 'uv run tracker setup slack' "
        "on your computer.",
    ),
    (RunStep.COLLECT_SLACK, SlackRateLimitedError.code): (
        "Slack asked Threadline to slow down, so some Slack messages were not read this morning.",
        "Nothing to do — the next run reads the rest.",
    ),
    (RunStep.COLLECT_SLACK, "source_unavailable"): (
        "Slack did not answer this morning, so no new Slack messages were read.",
        _WAIT_IT_OUT,
    ),
    (RunStep.COLLECT_TEAMS, "source_auth_failed"): (
        "Your Teams chats could not be read this morning: Microsoft refused the saved "
        "Teams sign-in.",
        _SIGN_IN_TO_TEAMS_AGAIN,
    ),
    (RunStep.COLLECT_TEAMS, AdminApprovalRequiredError.code): (
        "Your Teams chats could not be read: your organisation does not allow "
        "Threadline to read them.",
        "Your organisation's IT admin has to allow this. Until then Threadline "
        "carries on with your other sources.",
    ),
    (RunStep.COLLECT_TEAMS, WorkAccountRequiredError.code): (
        "Your Teams chats could not be read: Teams works only with a work or school "
        "account, not a personal Microsoft account.",
        _SIGN_IN_TO_TEAMS_AGAIN,
    ),
    (RunStep.COLLECT_TEAMS, "source_unavailable"): (
        "Teams did not answer this morning, so no new Teams messages were read.",
        _WAIT_IT_OUT,
    ),
    (RunStep.COLLECT_TELEGRAM, "source_auth_failed"): (
        "Telegram no longer accepts Threadline's login, so no new Telegram messages were read.",
        "Log in again: run 'uv run tracker setup telegram' on your computer. It takes "
        "about a minute (your phone number and the code Telegram sends you).",
    ),
    (RunStep.COLLECT_TELEGRAM, "source_unavailable"): (
        "Telegram did not answer this morning, so no new Telegram messages were read.",
        _WAIT_IT_OUT,
    ),
    (RunStep.COLLECT_TELEGRAM, TelegramFloodWaitError.code): (
        "Telegram asked Threadline to pause, so not every Telegram chat was read this morning.",
        "Nothing to do — the pause passes by itself and the next run reads what was missed.",
    ),
    (RunStep.COLLECT_GOOGLE_CALENDAR, "source_auth_failed"): (
        "Your Google Calendar could not be read this morning: Google says its secret "
        "address no longer works.",
        "Make a new secret address and save it with 'uv run tracker setup google-calendar' "
        "- it takes about a minute. If Google no longer shows a secret address, your "
        "organisation's Google Workspace administrator has turned it off.",
    ),
    (RunStep.COLLECT_GOOGLE_CALENDAR, "source_unavailable"): (
        "Your Google Calendar did not answer this morning, so no new meetings were read.",
        _WAIT_IT_OUT,
    ),
    (RunStep.COLLECT_GOOGLE_CALENDAR, "download_too_large"): (
        "Your Google Calendar is larger than Threadline reads, so no new meetings were read.",
        "Nothing breaks; the Google meetings are just left out. If this keeps appearing, "
        "see 'When something keeps failing' in docs/operations.md.",
    ),
    (RunStep.COLLECT_GOOGLE_CALENDAR, "validation_failed"): (
        "Your Google Calendar's secret address did not give a calendar this morning.",
        "Copy the 'Secret address in iCal format' again and save it with "
        "'uv run tracker setup google-calendar'.",
    ),
}

#: What to do when a standard mailbox refused its app password.
_NEW_APP_PASSWORD: Final[str] = (
    "Create a new app password and save it with 'uv run tracker setup mailbox' — it "
    "takes about two minutes. The steps are in 'Renew a mailbox app password' in "
    "docs/operations.md."
)

#: Sentences chosen by the step alone, whatever went wrong inside it.
_BY_STEP: Final[dict[RunStep, tuple[str, str]]] = {
    RunStep.COLLECT_LINKEDIN: (
        "The LinkedIn messages could not be read this morning.",
        _CHECK_THE_RUN_PAGE,
    ),
    RunStep.COLLECT_EMAIL: (
        "Your mailbox could not be read this morning.",
        _CHECK_THE_RUN_PAGE,
    ),
    RunStep.COLLECT_CALENDAR: (
        "Your calendar could not be read this morning.",
        _CHECK_THE_RUN_PAGE,
    ),
    RunStep.COLLECT_SLACK: (
        "Your Slack messages could not be read this morning.",
        _CHECK_THE_RUN_PAGE,
    ),
    RunStep.COLLECT_TEAMS: (
        "Your Teams chats could not be read this morning.",
        _CHECK_THE_RUN_PAGE,
    ),
    RunStep.COLLECT_TELEGRAM: (
        "Your Telegram chats could not be read this morning.",
        _CHECK_THE_RUN_PAGE,
    ),
    RunStep.COLLECT_GOOGLE_CALENDAR: (
        "Your Google Calendar could not be read this morning.",
        _CHECK_THE_RUN_PAGE,
    ),
    RunStep.ASSESS: (
        "The new messages were collected but not read through, so the statuses "
        "below may be a day behind.",
        _WAIT_IT_OUT,
    ),
    RunStep.SUMMARY_EMAIL: (
        "This summary was put together, but something went wrong while sending it.",
        _CHECK_THE_RUN_PAGE,
    ),
}

#: Sentences chosen by the code alone, whatever step met it.
_BY_CODE: Final[dict[str, tuple[str, str]]] = {
    "database_unavailable": (
        "Threadline could not reach its own database during this part of the run.",
        _WAIT_IT_OUT,
    ),
    "configuration_invalid": (
        "A setting Threadline needs is missing or wrong, so this part of the run could not start.",
        "See 'When a setting is missing' in docs/operations.md. Nothing is lost — "
        "the next run picks up where this one stopped.",
    ),
    "validation_failed": (
        "Some of what came back did not look right, so it was left out rather than saved wrongly.",
        _WAIT_IT_OUT,
    ),
    RUN_INTERRUPTED_CODE: (
        "An earlier run stopped part-way and never finished (for example, GitHub "
        "stopped it), so it was closed as failed.",
        "Nothing to do — this run read everything that run missed. If the same "
        "thing appears three mornings running, see 'When something keeps failing' "
        "in docs/operations.md.",
    ),
}

#: Used when a run stopped before it could record a single step.
_RUN_DID_NOT_START: Final[tuple[str, str]] = (
    "This morning's run stopped before it could read anything, so nothing below "
    "is newer than yesterday.",
    _CHECK_THE_RUN_PAGE,
)

#: Used when nothing above fits.
_FALLBACK: Final[tuple[str, str]] = (
    "One part of this morning's run stopped before it finished.",
    _CHECK_THE_RUN_PAGE,
)


def explain(
    step: RunStep | None,
    error_code: str | None,
    mail_provider: ImapProvider = ImapProvider.CUSTOM,
) -> SummaryProblem:
    """Turn a failed step into two sentences the owner can act on.

    Args:
        step: The step that failed, or ``None`` when the run recorded no step
            at all.
        error_code: The stable code stored with the failure, if there is one.
        mail_provider: Who runs the owner's IMAP mailbox, so a refused app
            password names it ("Google refused…").

    Returns:
        The problem, in plain English.
    """
    what_happened, what_to_do = _sentences(step, (error_code or "").strip(), mail_provider)
    return SummaryProblem(step=step, what_happened=what_happened, what_to_do=what_to_do)


def _sentences(step: RunStep | None, code: str, mail_provider: ImapProvider) -> tuple[str, str]:
    """Pick the most specific pair of sentences available for a failure."""
    if step is None:
        return _RUN_DID_NOT_START
    if code == MailboxPasswordError.code:
        preset = IMAP_PRESETS[mail_provider]
        return (
            f"Your {preset.label} could not be read this morning: {preset.company} "
            "refused the app password.",
            _NEW_APP_PASSWORD,
        )
    specific = _BY_STEP_AND_CODE.get((step, code))
    if specific is not None:
        return specific
    by_code = _BY_CODE.get(code)
    if by_code is not None:
        return by_code
    return _BY_STEP.get(step, _FALLBACK)
