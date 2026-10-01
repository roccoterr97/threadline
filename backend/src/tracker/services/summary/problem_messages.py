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
from tracker.shared.constants.mailbox import IMAP_PRESETS, ImapProvider
from tracker.shared.constants.runs import RUN_INTERRUPTED_CODE
from tracker.shared.errors import MailboxPasswordError

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

#: Sentences chosen by the step *and* the code, where the source matters.
_BY_STEP_AND_CODE: Final[dict[tuple[RunStep, str], tuple[str, str]]] = {
    (RunStep.COLLECT_LINKEDIN, "source_auth_failed"): (
        "LinkedIn would not accept its key this morning, so no new LinkedIn "
        "messages were read.",
        "Renew the LinkedIn key — it lasts about a year and takes five minutes. "
        "The steps are in 'Renew the LinkedIn key' in docs/operations.md.",
    ),
    (RunStep.COLLECT_LINKEDIN, "source_unavailable"): (
        "LinkedIn did not answer this morning, so no new LinkedIn messages were read.",
        _WAIT_IT_OUT,
    ),
    (RunStep.COLLECT_EMAIL, "source_auth_failed"): (
        "Your mailbox could not be read this morning: Microsoft refused the "
        "saved sign-in.",
        "Sign in to Microsoft once more — it takes about a minute. The steps are "
        "in 'Redo the Microsoft sign-in' in docs/operations.md.",
    ),
    (RunStep.COLLECT_EMAIL, "source_unavailable"): (
        "Your mailbox did not answer this morning, so no new e-mails were read.",
        _WAIT_IT_OUT,
    ),
    (RunStep.COLLECT_CALENDAR, "source_auth_failed"): (
        "Your calendar could not be read this morning: Microsoft refused "
        "the saved sign-in.",
        "Sign in to Microsoft once more — it takes about a minute. The steps are "
        "in 'Redo the Microsoft sign-in' in docs/operations.md.",
    ),
    (RunStep.COLLECT_CALENDAR, "source_unavailable"): (
        "Your calendar did not answer this morning, so no new meetings "
        "were read.",
        _WAIT_IT_OUT,
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
        "A setting Threadline needs is missing or wrong, so this part of the run "
        "could not start.",
        "See 'When a setting is missing' in docs/operations.md. Nothing is lost — "
        "the next run picks up where this one stopped.",
    ),
    "validation_failed": (
        "Some of what came back did not look right, so it was left out rather than "
        "saved wrongly.",
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
