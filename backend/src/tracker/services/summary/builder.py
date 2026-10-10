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

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from tracker.domain.dashboard_link import DashboardAddress, dashboard_address
from tracker.domain.enums import RunStatus, WaitingOn
from tracker.domain.models import PersonOverview, RunLog, RunStepLog
from tracker.repositories import Repositories
from tracker.schemas.summary import (
    SummaryContent,
    SummaryEmail,
    SummaryPerson,
    SummaryProblem,
)
from tracker.services.runs.run_recorder import triggers_of_kind
from tracker.services.runs.run_status import COLLECT_STEPS, derive_status_of_run
from tracker.services.summary.once_a_day import summary_went_out
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
    REPLY_LATE_COLLECTION_DAYS,
    REPLY_WINDOW_FALLBACK_HOURS,
)
from tracker.shared.errors import ValidationFailedError
from tracker.shared.logging import get_logger

#: Sorts people with no due date after everybody who has one.
_NO_DUE_DATE = datetime.max.date()

_log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class _DailyHistory:
    """The recent daily runs, read once for the reply window and the notices.

    Attributes:
        runs: The newest daily runs, newest first; never a refresh.
        interrupted: The runs closed as interrupted, with the step they stopped at.
        summarised: The runs whose summary actually reached the owner.
    """

    runs: list[RunLog]
    interrupted: dict[UUID, RunStepLog]
    summarised: frozenset[UUID]


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
            run_id: The run to report on. ``None`` uses the most recent run
                that is not a refresh, and a database with no such run simply
                reports no problem.

        Returns:
            The e-mail, ready to send.

        Raises:
            ValidationFailedError: If ``run_id`` names a run that does not exist.
        """
        return self.build_for(self.run_to_report(run_id))

    def build_for(self, run: RunLog | None) -> SummaryEmail:
        """Build the summary for a run already looked up with :meth:`run_to_report`.

        Args:
            run: The run to report on, or ``None`` when there is none.

        Returns:
            The e-mail, ready to send.
        """
        problems, status = self._run_outcome(run)
        history = self._daily_history()
        window_start = self._reply_window_start(run, history)
        problems += _interrupted_problems(run, history, window_start)
        overview = self._repositories.people_overview.list_every()
        do_today = [row for row in overview if _is_waiting_on_owner(row)]
        overdue = [row for row in overview if row.is_overdue]
        chase = [row for row in overview if row.is_chase_due]
        replied = self._replied_since(overview, window_start)
        dashboard = self._dashboard()
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
            open_questions=len(self._repositories.review_items.list_every_unanswered()),
            key_reminder=self._key_reminder(),
            dashboard_url=dashboard.base if dashboard is not None else None,
            dashboard_connect=dashboard.connect if dashboard is not None else None,
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

    def _dashboard(self) -> DashboardAddress | None:
        """Where the summary's links point: the personal link for the shared dashboard.

        A shared dashboard whose link cannot be made still gets its plain
        address, which opens on a device that was connected before; the
        problem is logged, and ``tracker doctor`` names it.
        """
        settings = self._settings
        dashboard = dashboard_address(
            settings.dashboard_base_url,
            settings.supabase_url,
            settings.supabase_anon_key.get_secret_value(),
        )
        if dashboard is not None and dashboard.shared and dashboard.connect is None:
            _log.warning("summary_personal_link_unavailable")
        return dashboard

    def run_to_report(self, run_id: UUID | None) -> RunLog | None:
        """Find the run a summary reports on.

        Args:
            run_id: The run asked for, or ``None`` for the most recent run that
                is not a refresh.

        Returns:
            The run, or ``None`` when no run has happened yet.

        Raises:
            ValidationFailedError: If ``run_id`` names a run that does not exist.
        """
        if run_id is None:
            # A refresh sends no summary, so the morning's run is the one to report.
            return self._repositories.run_logs.find_latest(triggers_of_kind(refresh=False))
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
        # The summary is the run's last step: it cannot be among the steps yet.
        status = derive_status_of_run(steps, run.trigger, summary_pending=True)
        if not steps:
            return (explain(None, None),), status
        problems = tuple(
            explain(step.step, step.error_code, self._settings.imap_provider)
            for step in steps
            if step.status is not RunStatus.SUCCESS
        )
        if COLLECT_STEPS.isdisjoint(step.step for step in steps):
            return (explain(None, None), *problems), status
        return problems, status

    def _daily_history(self) -> _DailyHistory:
        """Read the recent daily runs and what their steps say.

        Refreshes are left out in the query itself: they send no summary, and a
        busy afternoon of them must not push yesterday's run out of the list.
        """
        runs = self._repositories.run_logs.list_recent(
            triggers_of_kind(refresh=False), limit=RECENT_RUNS_SCANNED
        )
        steps = self._repositories.run_step_logs.list_for_runs([run.id for run in runs])
        return _DailyHistory(
            runs=runs,
            interrupted={
                step.run_id: step for step in steps if step.error_code == RUN_INTERRUPTED_CODE
            },
            summarised=frozenset(step.run_id for step in steps if summary_went_out(step)),
        )

    def _reply_window_start(self, run: RunLog | None, history: _DailyHistory) -> datetime:
        """Return the moment "replied since yesterday" counts from.

        That moment is the start of the previous daily run whose summary
        actually reached the owner, so a morning that was missed is caught up
        rather than skipped. A run whose summary failed, was skipped, or never
        got that far sent the owner nothing, so it does not count: otherwise
        the replies it saw would never appear in any e-mail. When there is no
        such run, the window is the last day.
        """
        earlier = [
            candidate.started_at
            for candidate in history.runs
            if candidate.id in history.summarised and (run is None or candidate.id != run.id)
        ]
        if earlier:
            return max(earlier)
        return self._clock.now() - timedelta(hours=REPLY_WINDOW_FALLBACK_HOURS)

    def _replied_since(
        self,
        overview: list[PersonOverview],
        since: datetime,
    ) -> list[PersonOverview]:
        """List the people who wrote back since a given moment.

        A reply counts when it was sent since then, or when it was only stored
        since then (the mailbox was unreachable the morning it arrived) and was
        sent not long before: a first import of old mail is stored all at once
        and is no reply.
        """
        by_person = {row.person_id: row for row in overview}
        if not by_person:
            return []
        threads = self._repositories.conversations.list_for_people(list(by_person))
        replied: dict[UUID, None] = {
            thread.person_id: None
            for thread in threads
            if thread.person_id is not None
            and thread.last_inbound_at is not None
            and thread.last_inbound_at >= since
        }
        owner_of = {thread.id: thread.person_id for thread in threads if thread.person_id}
        oldest_sent = since - timedelta(days=REPLY_LATE_COLLECTION_DAYS)
        for message in self._repositories.messages.list_inbound_stored_since(list(owner_of), since):
            if message.sent_at >= oldest_sent:
                replied[owner_of[message.conversation_id]] = None
        return [by_person[person_id] for person_id in replied]

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
            "To renew it, run 'uv run tracker setup linkedin' on your computer and click "
            "'Allow' on LinkedIn's page; 'Renew the LinkedIn key' in docs/operations.md "
            "has the details."
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
    history: _DailyHistory,
    since: datetime,
) -> tuple[SummaryProblem, ...]:
    """Explain the earlier daily runs that died part-way since the last summary.

    The run being reported on explains its own steps, so it is left out here.
    """
    return tuple(
        explain(history.interrupted[earlier.id].step, RUN_INTERRUPTED_CODE)
        for earlier in sorted(history.runs, key=lambda candidate: candidate.started_at)
        if earlier.id in history.interrupted
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
