"""Build the morning summary from what the database already knows.

The summary is assembled by Python, not written by an assistant: it reads the
dashboard's own read model (``people_overview``), the open questions and the
steps of the run that has just happened, and puts them in a fixed order. No
message body and no subject is read anywhere in this module, so nothing a
stranger wrote can reach the owner's inbox through the summary.

Each person appears once. Somebody who is both waiting on the owner and past
their follow-up date belongs in "overdue", which is the more urgent of the two,
and is not repeated under "do today". Somebody the owner is waiting on, past
the date to chase them, belongs in "time to chase" — never in "overdue", which
is kept for replies the owner owes.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from tracker.domain.enums import RunStatus, RunTrigger, WaitingOn
from tracker.domain.models import PersonOverview, RunLog, RunStepLog
from tracker.repositories import Repositories
from tracker.schemas.summary import (
    SummaryContent,
    SummaryEmail,
    SummaryPerson,
    SummaryProblem,
)
from tracker.services.identity.matcher import read_every
from tracker.services.runs.run_recorder import derive_run_status
from tracker.services.summary.problem_messages import explain
from tracker.services.summary.renderer import format_day, render_email
from tracker.services.summary.wording import Branding
from tracker.shared.clock import Clock
from tracker.shared.config import Settings
from tracker.shared.constants.runs import RUN_INTERRUPTED_CODE
from tracker.shared.constants.summary import (
    KEY_REMINDER_DAYS,
    MAX_PEOPLE_PER_SECTION,
    RECENT_RUNS_SCANNED,
    REPLY_WINDOW_FALLBACK_HOURS,
)
from tracker.shared.errors import ValidationFailedError
from tracker.shared.logging import get_logger

#: Sorts people with no due date after everybody who has one.
_NO_DUE_DATE = datetime.max.date()

_log = get_logger(__name__)


class SummaryBuilder:
    """Assembles the morning summary."""

    def __init__(self, repositories: Repositories, settings: Settings, clock: Clock) -> None:
        """Bind the builder to the database, the configuration and a clock.

        Args:
            repositories: The repository container.
            settings: The process configuration: the recipient, the product
                name, the subject prefix and the LinkedIn key date.
            clock: Source of the current moment.
        """
        self._repositories = repositories
        self._settings = settings
        self._clock = clock

    def build(self, run_id: UUID | None = None) -> SummaryEmail:
        """Build the summary for one run.

        Args:
            run_id: The run to report on. ``None`` uses the most recent run, and
                a database with no run at all simply reports no problem.

        Returns:
            The e-mail, ready to send.

        Raises:
            ValidationFailedError: If ``run_id`` names a run that does not exist.
        """
        run = self._resolve_run(run_id)
        problems, status = self._run_outcome(run)
        recent = self._repositories.run_logs.list(limit=RECENT_RUNS_SCANNED)
        interrupted = self._interrupted(recent)
        window_start = self._reply_window_start(run, recent, interrupted)
        problems += _interrupted_problems(run, recent, interrupted, window_start)
        overview = read_every(self._repositories.people_overview.list)
        do_today = [row for row in overview if _is_waiting_on_owner(row)]
        overdue = [row for row in overview if row.is_overdue]
        chase = [row for row in overview if row.is_chase_due]
        replied = self._replied_since(overview, window_start)
        content = SummaryContent(
            generated_at=self._clock.now(),
            day=self._clock.today(),
            run_status=status,
            problems=problems,
            do_today=_section(do_today),
            do_today_total=len(do_today),
            overdue=_section(overdue),
            overdue_total=len(overdue),
            chase=_section(chase),
            chase_total=len(chase),
            replied=_section(replied),
            replied_total=len(replied),
            open_questions=len(read_every(self._repositories.review_items.list_unanswered)),
            key_reminder=self._key_reminder(),
            dashboard_url=self._settings.dashboard_base_url,
        )
        _log.info(
            "summary_built",
            run_id=str(run.id) if run is not None else None,
            status=status.value,
            do_today=content.do_today_total,
            overdue=content.overdue_total,
            chase=content.chase_total,
            problems=len(problems),
        )
        return render_email(
            content,
            self._settings.summary_recipient_address,
            Branding(
                product_name=self._settings.product_name,
                subject_prefix=self._settings.summary_subject_prefix,
            ),
        )

    def _resolve_run(self, run_id: UUID | None) -> RunLog | None:
        """Find the run to report on.

        Raises:
            ValidationFailedError: If ``run_id`` names a run that does not exist.
        """
        if run_id is None:
            return self._repositories.run_logs.find_latest()
        run = self._repositories.run_logs.get(run_id)
        if run is None:
            message = f"no run with identifier {run_id}"
            raise ValidationFailedError(message)
        return run

    def _run_outcome(self, run: RunLog | None) -> tuple[tuple[SummaryProblem, ...], RunStatus]:
        """Describe how the run went, in problems and in one status."""
        if run is None:
            return (), RunStatus.SUCCESS
        steps = self._repositories.run_step_logs.list_for_run(run.id)
        status = derive_run_status([step.status for step in steps])
        if not steps:
            return (explain(None, None),), status
        problems = tuple(
            explain(step.step, step.error_code, self._settings.imap_provider)
            for step in steps
            if step.status is not RunStatus.SUCCESS
        )
        return problems, status

    def _interrupted(self, recent: list[RunLog]) -> dict[UUID, RunStepLog]:
        """Find the recent runs that were closed as interrupted, with the step they stopped at."""
        steps = self._repositories.run_step_logs.list_for_runs([run.id for run in recent])
        return {step.run_id: step for step in steps if step.error_code == RUN_INTERRUPTED_CODE}

    def _reply_window_start(
        self, run: RunLog | None, recent: list[RunLog], interrupted: dict[UUID, RunStepLog]
    ) -> datetime:
        """Return the moment "replied since yesterday" counts from.

        That moment is the start of the previous finished run, so a morning that
        was missed is caught up rather than skipped. A refresh between two
        mornings sends no summary, so it does not count: otherwise a reply seen
        by an afternoon refresh would never be reported. A run that was
        interrupted does not count either: it may never have sent its summary.
        When there is no earlier run, the window is the last day.
        """
        earlier = [
            candidate
            for candidate in recent
            if candidate.finished_at is not None
            and candidate.trigger is not RunTrigger.REFRESH
            and candidate.id not in interrupted
            and (run is None or candidate.id != run.id)
        ]
        if earlier:
            return max(candidate.started_at for candidate in earlier)
        return self._clock.now() - timedelta(hours=REPLY_WINDOW_FALLBACK_HOURS)

    def _replied_since(
        self,
        overview: list[PersonOverview],
        since: datetime,
    ) -> list[PersonOverview]:
        """List the people who wrote back since a given moment."""
        by_person = {row.person_id: row for row in overview}
        if not by_person:
            return []
        latest_inbound: dict[UUID, datetime] = {}
        for thread in self._repositories.conversations.list_for_people(list(by_person)):
            inbound = thread.last_inbound_at
            owner = thread.person_id
            if owner is None or inbound is None or inbound < since:
                continue
            latest_inbound[owner] = max(inbound, latest_inbound.get(owner, inbound))
        return [by_person[person_id] for person_id in latest_inbound]

    def _key_reminder(self) -> str | None:
        """Return the LinkedIn key reminder, or ``None`` while the key is fresh.

        An owner who never set LinkedIn up is not reminded about its key.
        """
        expires_on = self._settings.linkedin_token_expires_on
        if expires_on is None or not self._settings.linkedin_enabled:
            return None
        days_left = (expires_on - self._clock.today()).days
        if days_left > KEY_REMINDER_DAYS:
            return None
        renew = (
            "Renewing takes about five minutes: see 'Renew the LinkedIn key' in "
            "docs/operations.md."
        )
        if days_left < 0:
            return (
                f"The LinkedIn key expired on {format_day(expires_on)}, so LinkedIn "
                f"messages cannot be read until it is renewed. {renew}"
            )
        when = "today" if days_left == 0 else f"in {days_left} days"
        return f"The LinkedIn key stops working {when} ({format_day(expires_on)}). {renew}"


def _interrupted_problems(
    run: RunLog | None,
    recent: list[RunLog],
    interrupted: dict[UUID, RunStepLog],
    since: datetime,
) -> tuple[SummaryProblem, ...]:
    """Explain the earlier runs that died part-way since the last summary.

    The run being reported on explains its own steps, so it is left out here.
    """
    return tuple(
        explain(interrupted[earlier.id].step, RUN_INTERRUPTED_CODE)
        for earlier in sorted(recent, key=lambda candidate: candidate.started_at)
        if earlier.id in interrupted
        and earlier.started_at >= since
        and (run is None or earlier.id != run.id)
    )


def _is_waiting_on_owner(row: PersonOverview) -> bool:
    """Whether this person is waiting on the owner and is not already overdue."""
    return row.waiting_on is WaitingOn.ME and not row.is_overdue


def _section(rows: list[PersonOverview]) -> tuple[SummaryPerson, ...]:
    """Render one section's people, soonest first, capped at the section size."""
    ordered = sorted(rows, key=lambda row: (row.due_date or _NO_DUE_DATE, row.full_name))
    return tuple(_as_person(row) for row in ordered[:MAX_PEOPLE_PER_SECTION])


def _as_person(row: PersonOverview) -> SummaryPerson:
    """Render one row of the read model as one line of the summary."""
    return SummaryPerson(
        name=row.full_name,
        organisation=row.organisation_name,
        next_action=row.next_action,
        due_date=row.due_date,
    )
