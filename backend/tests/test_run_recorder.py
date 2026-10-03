"""Recording a run: its steps, its idempotence, and the status it adds up to."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from tests.conftest import FakeSupabaseClient, as_client
from tracker.domain.enums import RunStatus, RunStep, RunTrigger
from tracker.repositories import Repositories, build_repositories
from tracker.services.runs.run_recorder import (
    DEFAULT_ERROR_CODE,
    RunRecorder,
    StepOutcome,
    StepResult,
    derive_run_status,
    unconfigured_steps,
)
from tracker.shared.clock import FixedClock
from tracker.shared.config import Settings
from tracker.shared.constants.runs import INTERRUPTED_RUN_AFTER_HOURS, RUN_INTERRUPTED_CODE
from tracker.shared.constants.summary import MAX_ERROR_DETAIL_LENGTH
from tracker.shared.errors import ValidationFailedError

NOW = datetime(2026, 9, 18, 5, 0, tzinfo=UTC)


@pytest.fixture
def recorder(repositories: Repositories) -> RunRecorder:
    return RunRecorder(repositories, FixedClock(NOW))


def test_a_run_with_no_step_at_all_is_a_failure() -> None:
    assert derive_run_status([]) is RunStatus.FAILED


def test_a_run_whose_steps_all_finished_is_a_success() -> None:
    assert derive_run_status([RunStatus.SUCCESS, RunStatus.SUCCESS]) is RunStatus.SUCCESS


def test_a_run_with_one_failed_step_among_others_is_partial() -> None:
    statuses = [RunStatus.SUCCESS, RunStatus.FAILED, RunStatus.SUCCESS]

    assert derive_run_status(statuses) is RunStatus.PARTIAL


def test_a_run_whose_every_step_failed_is_a_failure() -> None:
    assert derive_run_status([RunStatus.FAILED, RunStatus.FAILED]) is RunStatus.FAILED


def test_starting_a_run_stores_it_as_running(
    recorder: RunRecorder,
    fake_client: FakeSupabaseClient,
) -> None:
    run = recorder.start(RunTrigger.CLOUD)

    stored = fake_client.tables["run_logs"]
    assert len(stored) == 1
    assert stored[0]["id"] == str(run.id)
    assert stored[0]["status"] == RunStatus.RUNNING.value
    assert stored[0]["trigger"] == RunTrigger.CLOUD.value
    assert stored[0]["started_at"].startswith("2026-09-18T05:00:00")


def _running_since(fake_client: FakeSupabaseClient, hours: float, trigger: RunTrigger) -> str:
    """Store a run still marked running that started some hours before ``NOW``."""
    run_id = str(uuid4())
    fake_client.tables.setdefault("run_logs", []).append(
        {
            "id": run_id,
            "started_at": (NOW - timedelta(hours=hours)).isoformat(),
            "finished_at": None,
            "status": RunStatus.RUNNING.value,
            "trigger": trigger.value,
        }
    )
    return run_id


def _steps_of(fake_client: FakeSupabaseClient, run_id: str) -> list[dict[str, object]]:
    rows = fake_client.tables.get("run_step_logs", [])
    return [row for row in rows if row["run_id"] == run_id]


def test_a_run_that_died_long_ago_is_closed_as_interrupted_where_it_stopped(
    repositories: Repositories, fake_client: FakeSupabaseClient
) -> None:
    stale = _running_since(fake_client, INTERRUPTED_RUN_AFTER_HOURS + 1, RunTrigger.GITHUB)
    unconfigured = frozenset({RunStep.COLLECT_LINKEDIN})
    old = RunRecorder(repositories, FixedClock(NOW - timedelta(hours=5)), unconfigured)
    old.record_step(UUID(stale), StepOutcome(RunStep.COLLECT_EMAIL, StepResult.SUCCESS))

    RunRecorder(repositories, FixedClock(NOW), unconfigured).start(RunTrigger.GITHUB)

    closed = next(row for row in fake_client.tables["run_logs"] if row["id"] == stale)
    assert closed["status"] == RunStatus.FAILED.value
    assert closed["finished_at"] is not None
    added = [row for row in _steps_of(fake_client, stale) if row["status"] == "failed"]
    assert [(row["step"], row["error_code"]) for row in added] == [
        (RunStep.COLLECT_CALENDAR.value, RUN_INTERRUPTED_CODE)
    ]


def test_a_run_still_within_its_time_is_left_running(
    recorder: RunRecorder, fake_client: FakeSupabaseClient
) -> None:
    recent = _running_since(fake_client, 0.5, RunTrigger.GITHUB)

    recorder.start(RunTrigger.REFRESH)

    kept = next(row for row in fake_client.tables["run_logs"] if row["id"] == recent)
    assert kept["status"] == RunStatus.RUNNING.value
    assert _steps_of(fake_client, recent) == []


def test_an_interrupted_refresh_is_never_blamed_on_the_summary(
    repositories: Repositories, fake_client: FakeSupabaseClient
) -> None:
    stale = _running_since(fake_client, 4, RunTrigger.REFRESH)
    earlier = RunRecorder(repositories, FixedClock(NOW))
    for step in (RunStep.COLLECT_LINKEDIN, RunStep.COLLECT_EMAIL, RunStep.COLLECT_CALENDAR):
        earlier.record_step(UUID(stale), StepOutcome(step, StepResult.SUCCESS))
    earlier.record_step(UUID(stale), StepOutcome(RunStep.ASSESS, StepResult.SUCCESS))

    RunRecorder(repositories, FixedClock(NOW)).start(RunTrigger.GITHUB)

    closed = next(row for row in fake_client.tables["run_logs"] if row["id"] == stale)
    assert closed["status"] == RunStatus.SUCCESS.value
    assert all(row["error_code"] is None for row in _steps_of(fake_client, stale))


def test_one_collector_failing_leaves_the_other_step_untouched(
    recorder: RunRecorder,
    repositories: Repositories,
) -> None:
    run = recorder.start(RunTrigger.MANUAL)
    recorder.record_step(
        run.id,
        StepOutcome(RunStep.COLLECT_LINKEDIN, StepResult.SUCCESS, items_found=165, items_new=2),
    )
    recorder.record_step(
        run.id,
        StepOutcome(RunStep.COLLECT_EMAIL, StepResult.FAILED, error_code="source_auth_failed"),
    )

    steps = repositories.run_step_logs.list_for_run(run.id)
    by_step = {step.step: step for step in steps}
    assert by_step[RunStep.COLLECT_LINKEDIN].status is RunStatus.SUCCESS
    assert by_step[RunStep.COLLECT_LINKEDIN].items_found == 165
    assert by_step[RunStep.COLLECT_EMAIL].status is RunStatus.FAILED
    assert by_step[RunStep.COLLECT_EMAIL].error_code == "source_auth_failed"


def test_recording_the_same_step_twice_keeps_one_row(
    recorder: RunRecorder,
    repositories: Repositories,
) -> None:
    run = recorder.start(RunTrigger.MANUAL)
    recorder.record_step(
        run.id,
        StepOutcome(RunStep.COLLECT_EMAIL, StepResult.FAILED, error_code="source_unavailable"),
    )
    recorder.record_step(
        run.id,
        StepOutcome(RunStep.COLLECT_EMAIL, StepResult.SUCCESS, items_found=12, items_new=3),
    )

    steps = repositories.run_step_logs.list_for_run(run.id)
    assert len(steps) == 1
    assert steps[0].status is RunStatus.SUCCESS
    assert steps[0].error_code is None


def test_a_failure_without_a_reason_still_gets_a_stable_code(
    recorder: RunRecorder,
    repositories: Repositories,
) -> None:
    run = recorder.start(RunTrigger.CLOUD)
    recorder.record_step(run.id, StepOutcome(RunStep.ASSESS, StepResult.FAILED))

    assert repositories.run_step_logs.list_for_run(run.id)[0].error_code == DEFAULT_ERROR_CODE


def test_a_long_technical_note_is_trimmed_before_it_is_stored(
    recorder: RunRecorder,
    repositories: Repositories,
) -> None:
    run = recorder.start(RunTrigger.CLOUD)
    recorder.record_step(
        run.id,
        StepOutcome(
            RunStep.COLLECT_EMAIL,
            StepResult.FAILED,
            error_code="source_unavailable",
            error_detail="x" * (MAX_ERROR_DETAIL_LENGTH + 50),
        ),
    )

    detail = repositories.run_step_logs.list_for_run(run.id)[0].error_detail
    assert detail is not None
    assert len(detail) == MAX_ERROR_DETAIL_LENGTH


def test_finishing_a_half_done_run_records_it_as_partial(recorder: RunRecorder) -> None:
    run = recorder.start(RunTrigger.CLOUD)
    recorder.record_step(run.id, StepOutcome(RunStep.COLLECT_LINKEDIN, StepResult.SUCCESS))
    recorder.record_step(
        run.id,
        StepOutcome(RunStep.COLLECT_EMAIL, StepResult.FAILED, error_code="source_auth_failed"),
    )

    finished = recorder.finish(run.id)

    assert finished.status is RunStatus.PARTIAL
    assert finished.finished_at == NOW


def test_finishing_a_run_that_never_recorded_a_step_records_it_as_failed(
    recorder: RunRecorder,
) -> None:
    run = recorder.start(RunTrigger.CLOUD)

    assert recorder.finish(run.id).status is RunStatus.FAILED


def test_finishing_a_run_that_does_not_exist_is_refused(recorder: RunRecorder) -> None:
    with pytest.raises(ValidationFailedError):
        recorder.finish(uuid4())


def test_the_latest_run_is_the_one_a_command_acts_on_by_default(
    repositories: Repositories,
) -> None:
    earlier = RunRecorder(repositories, FixedClock(datetime(2026, 9, 17, 5, 0, tzinfo=UTC)))
    earlier.start(RunTrigger.CLOUD)
    later = RunRecorder(repositories, FixedClock(NOW))
    today = later.start(RunTrigger.MANUAL)

    assert later.resolve(None).id == today.id


def test_a_closed_latest_run_is_not_the_default(repositories: Repositories) -> None:
    yesterday = RunRecorder(repositories, FixedClock(NOW - timedelta(days=1)))
    closed = yesterday.start(RunTrigger.CLOUD)
    yesterday.finish(closed.id)
    today = RunRecorder(repositories, FixedClock(NOW))

    with pytest.raises(ValidationFailedError, match="no run is open"):
        today.resolve(None)


def test_an_abandoned_open_run_is_not_the_default(repositories: Repositories) -> None:
    started = NOW - timedelta(hours=INTERRUPTED_RUN_AFTER_HOURS)
    RunRecorder(repositories, FixedClock(started)).start(RunTrigger.CLOUD)

    with pytest.raises(ValidationFailedError, match="no run is open"):
        RunRecorder(repositories, FixedClock(NOW)).resolve(None)


@pytest.mark.parametrize("earlier_refresh", [False, True], ids=["never", "closed"])
def test_looking_for_a_refresh_beside_a_daily_run_says_what_to_do_instead(
    repositories: Repositories, *, earlier_refresh: bool
) -> None:
    """``tracker run start`` alone opens a daily run, so the refusal names the refresh trigger."""
    if earlier_refresh:
        yesterday = RunRecorder(repositories, FixedClock(NOW - timedelta(days=1)))
        yesterday.finish(yesterday.start(RunTrigger.REFRESH).id)
    recorder = RunRecorder(repositories, FixedClock(NOW))
    recorder.start(RunTrigger.MANUAL)

    with pytest.raises(ValidationFailedError) as refused:
        recorder.resolve(None, refresh=True)

    assert "'tracker run start --trigger refresh'" in refused.value.message
    assert "leave out --refresh to use the daily or manual run that is open" in (
        refused.value.message
    )


def test_a_named_run_is_used_even_when_it_is_closed(repositories: Repositories) -> None:
    yesterday = RunRecorder(repositories, FixedClock(NOW - timedelta(days=1)))
    closed = yesterday.start(RunTrigger.CLOUD)
    yesterday.finish(closed.id)

    assert RunRecorder(repositories, FixedClock(NOW)).resolve(closed.id).id == closed.id


def _recorder_at(repositories: Repositories, minutes_ago: int) -> RunRecorder:
    return RunRecorder(repositories, FixedClock(NOW - timedelta(minutes=minutes_ago)))


@pytest.mark.parametrize("refresh_first", [True, False], ids=["refresh first", "daily first"])
def test_a_daily_run_and_a_refresh_going_together_each_keep_their_own_run(
    repositories: Repositories, *, refresh_first: bool
) -> None:
    """Whichever started last, neither may take, record into or close the other's run."""
    first, second = (RunTrigger.REFRESH, RunTrigger.GITHUB)
    if not refresh_first:
        first, second = second, first
    earlier = _recorder_at(repositories, 20).start(first)
    later = _recorder_at(repositories, 5).start(second)
    runs = {earlier.trigger: earlier.id, later.trigger: later.id}
    recorder = RunRecorder(repositories, FixedClock(NOW))

    assert recorder.resolve(None).id == runs[RunTrigger.GITHUB]
    assert recorder.resolve(None, refresh=True).id == runs[RunTrigger.REFRESH]


def test_closing_the_refresh_leaves_the_daily_run_open(repositories: Repositories) -> None:
    daily = _recorder_at(repositories, 20).start(RunTrigger.GITHUB)
    refresh = _recorder_at(repositories, 5).start(RunTrigger.REFRESH)
    recorder = RunRecorder(repositories, FixedClock(NOW))

    recorder.finish(recorder.resolve(None, refresh=True).id)

    closed = repositories.run_logs.get(refresh.id)
    assert closed is not None
    assert closed.status is not RunStatus.RUNNING
    assert recorder.resolve(None).id == daily.id


def test_a_refresh_alone_is_not_the_open_daily_run(repositories: Repositories) -> None:
    _recorder_at(repositories, 5).start(RunTrigger.REFRESH)

    with pytest.raises(ValidationFailedError, match="no daily run"):
        RunRecorder(repositories, FixedClock(NOW)).resolve(None)


def test_a_daily_run_alone_is_not_the_open_refresh(repositories: Repositories) -> None:
    _recorder_at(repositories, 5).start(RunTrigger.MANUAL)

    with pytest.raises(ValidationFailedError, match="no refresh"):
        RunRecorder(repositories, FixedClock(NOW)).resolve(None, refresh=True)


def test_asking_for_a_run_before_anything_has_run_is_refused(recorder: RunRecorder) -> None:
    with pytest.raises(ValidationFailedError):
        recorder.resolve(None)


def test_asking_for_a_run_that_does_not_exist_is_refused(recorder: RunRecorder) -> None:
    with pytest.raises(ValidationFailedError):
        recorder.resolve(uuid4())


def test_the_recorder_writes_nothing_else_than_runs_and_their_steps(
    fake_client: FakeSupabaseClient,
) -> None:
    recorder = RunRecorder(build_repositories(as_client(fake_client)), FixedClock(NOW))
    run = recorder.start(RunTrigger.CLOUD)
    recorder.record_step(run.id, StepOutcome(RunStep.ASSESS, StepResult.SUCCESS))
    recorder.finish(run.id)

    written = {table for table, operation in fake_client.executed if operation != "select"}
    assert written == {"run_logs", "run_step_logs"}


# --- A source the owner never set up (Plan 18) --------------------------------


def test_linkedin_without_a_key_is_an_unconfigured_step(
    settings_without_linkedin_key: Settings,
) -> None:
    assert unconfigured_steps(settings_without_linkedin_key) == {RunStep.COLLECT_LINKEDIN}


def test_linkedin_with_a_profile_and_a_key_is_configured(settings: Settings) -> None:
    assert unconfigured_steps(settings) == frozenset()


def test_an_unconfigured_step_is_not_recorded(repositories: Repositories) -> None:
    recorder = RunRecorder(repositories, FixedClock(NOW), frozenset({RunStep.COLLECT_LINKEDIN}))
    run = recorder.start(RunTrigger.CLOUD)

    recorded = recorder.record_step(
        run.id,
        StepOutcome(
            RunStep.COLLECT_LINKEDIN, StepResult.FAILED, error_code="configuration_invalid"
        ),
    )

    assert recorded is None
    assert repositories.run_step_logs.list_for_run(run.id) == []


def test_a_run_without_linkedin_set_up_is_a_success_when_the_rest_worked(
    repositories: Repositories,
) -> None:
    recorder = RunRecorder(repositories, FixedClock(NOW), frozenset({RunStep.COLLECT_LINKEDIN}))
    run = recorder.start(RunTrigger.CLOUD)
    for step in (RunStep.COLLECT_LINKEDIN, RunStep.COLLECT_EMAIL, RunStep.ASSESS):
        recorder.record_step(run.id, StepOutcome(step, StepResult.SUCCESS))

    assert recorder.finish(run.id).status is RunStatus.SUCCESS


def test_a_real_failure_still_makes_the_run_partial_when_linkedin_is_not_set_up(
    repositories: Repositories,
) -> None:
    recorder = RunRecorder(repositories, FixedClock(NOW), frozenset({RunStep.COLLECT_LINKEDIN}))
    run = recorder.start(RunTrigger.CLOUD)
    recorder.record_step(run.id, StepOutcome(RunStep.COLLECT_EMAIL, StepResult.SUCCESS))
    recorder.record_step(
        run.id,
        StepOutcome(RunStep.COLLECT_CALENDAR, StepResult.FAILED, error_code="source_unavailable"),
    )

    assert recorder.finish(run.id).status is RunStatus.PARTIAL


def test_a_run_with_only_an_unconfigured_step_is_not_a_success(
    repositories: Repositories,
) -> None:
    """Skipping LinkedIn cannot hide a morning in which nothing else ran."""
    recorder = RunRecorder(repositories, FixedClock(NOW), frozenset({RunStep.COLLECT_LINKEDIN}))
    run = recorder.start(RunTrigger.CLOUD)
    recorder.record_step(run.id, StepOutcome(RunStep.COLLECT_LINKEDIN, StepResult.SUCCESS))

    assert recorder.finish(run.id).status is RunStatus.FAILED
