"""The contract for the morning summary file.

``tracker summary build`` writes one :class:`SummaryEmail` to disk. The session
that runs the daily recipe reads that file and sends its ``subject`` and its
body exactly as they are: it never writes wording of its own, and it never
opens a message to do so.

Nothing in these models carries message text. The people sections hold a name,
an organisation, the next action the assessment wrote and a due date; the
attention section holds sentences chosen from a fixed list in
:mod:`tracker.services.summary.problem_messages`.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Final

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from tracker.domain.dashboard_link import DashboardAddress
from tracker.domain.enums import RunStatus, RunStep

_STRICT: Final[ConfigDict] = ConfigDict(extra="forbid", frozen=True)


def _one_line(value: str | None) -> str | None:
    """Collapse any run of whitespace, including line breaks, into one space.

    Every one of these fields is written by somebody else: a name and an
    organisation come from a sender's display name, and a next action is
    written by the assistant from their messages. The plain-text summary is
    built line by line, so a value carrying a line break could add lines of its
    own — a forged "Something needs your attention" heading with a link of the
    sender's choosing, in an e-mail the owner trusts.

    Args:
        value: The text to flatten, or ``None``.

    Returns:
        The same text on a single line, or ``None``.
    """
    if value is None:
        return None
    return " ".join(value.split())


#: Text that reaches the e-mail body and came from outside, flattened to one line.
OneLine = Annotated[str, AfterValidator(lambda value: _one_line(value) or "")]
OptionalOneLine = Annotated[str | None, AfterValidator(_one_line)]


class SummaryPerson(BaseModel):
    """One person in one of the summary's lists."""

    model_config = _STRICT

    name: OneLine
    organisation: OptionalOneLine = None
    next_action: OptionalOneLine = None
    due_date: date | None = None


class SummaryProblem(BaseModel):
    """Something that went wrong, in words the owner can act on.

    Attributes:
        step: The step of the run that failed, or ``None`` when the run stopped
            before any step could run.
        what_happened: One plain sentence naming what did not happen.
        what_to_do: One plain sentence naming the next move, which may be
            "nothing".
    """

    model_config = _STRICT

    step: RunStep | None = None
    what_happened: str
    what_to_do: str


class SummaryContent(BaseModel):
    """What the summary says, before it is turned into words."""

    model_config = _STRICT

    generated_at: datetime
    #: The owner's date the summary is for, read in their time zone.
    day: date
    run_status: RunStatus
    problems: tuple[SummaryProblem, ...] = ()
    do_today: tuple[SummaryPerson, ...] = ()
    do_today_total: int = Field(default=0, ge=0)
    overdue: tuple[SummaryPerson, ...] = ()
    overdue_total: int = Field(default=0, ge=0)
    chase: tuple[SummaryPerson, ...] = ()
    chase_total: int = Field(default=0, ge=0)
    replied: tuple[SummaryPerson, ...] = ()
    replied_total: int = Field(default=0, ge=0)
    open_questions: int = Field(default=0, ge=0)
    key_reminder: str | None = None
    #: The dashboard's address, and what follows the ``#`` of the owner's
    #: personal link when it is the shared one (``tracker.domain.dashboard_link``).
    dashboard_url: str | None = None
    dashboard_connect: str | None = None

    def dashboard_page(self, path: str = "") -> str | None:
        """The address of one page of the dashboard, personal when it is the shared one.

        Args:
            path: The page, such as ``/review``; empty for the start page.

        Returns:
            The address, or ``None`` until the dashboard has one.
        """
        if self.dashboard_url is None:
            return None
        return DashboardAddress(self.dashboard_url, self.dashboard_connect).page(path)


class SummaryEmail(BaseModel):
    """The morning summary, ready to send.

    Attributes:
        recipient: Where it goes. Decided by Python from the owner's
            configuration, never a choice made while a run is in progress.
        subject: The subject line, starting with Threadline's own prefix so the
            mailbox collector ignores it on the next run.
        subject_prefix: That prefix on its own, so the session sending the
            summary can check the subject still starts with it.
        text_body: The plain-text body.
        html_body: The same body as simple HTML.
        content: The facts the two bodies were rendered from.
    """

    model_config = _STRICT

    recipient: str
    subject: str
    subject_prefix: str
    text_body: str
    html_body: str
    content: SummaryContent
