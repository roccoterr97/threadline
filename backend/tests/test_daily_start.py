"""The on-time morning start: the set-up, the doctor's line, the database calls and the contract.

The function's own decisions (when to start, at most once a day) are tested
with the dashboard's Vitest, in ``frontend/src/api/dailyStartFunction.test.ts``.
Here: the steps that keep the database's daily time in step with the
workflow, the Refresh now step that switches the timer on, the doctor, the
service-key calls, and the names the SQL, the function and Python must share.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date, time
from pathlib import Path
from typing import Any, Final
from unittest.mock import MagicMock

import pytest
import yaml
from postgrest import APIError
from pydantic import SecretStr

from tests.setup_world import (
    DAILY_START_KEY,
    GOOD_GITHUB_TOKEN,
    GOOD_TOKEN,
    TEST_SCHEDULE,
    FakeAdmin,
    FakeWorkflow,
    World,
    configured_env,
    make_world,
)
from tracker.cli.setup_wiring import make_daily_start_key, read_refresh_function
from tracker.domain.daily_start import DailyStartStatus
from tracker.infrastructure.github_cli import TextFile
from tracker.infrastructure.supabase_admin import SupabaseAdmin
from tracker.services.database_structure import KNOWN_MIGRATIONS, ColumnsProbe
from tracker.services.doctor.checks import DailyStartCheck, WorkflowTime
from tracker.services.doctor.models import CheckStatus
from tracker.services.doctor.service import DoctorService
from tracker.services.setup.daily_start import daily_start_url
from tracker.services.setup.step_refresh import RefreshStep, function_url
from tracker.services.setup.step_schedule import ScheduleStep
from tracker.services.setup.step_time_zone import TimeZoneStep
from tracker.services.setup.workflow_schedule import Schedule, write_schedule
from tracker.shared.config import REPOSITORY_ROOT
from tracker.shared.constants.github import WORKFLOW_FILE
from tracker.shared.constants.setup import (
    DAILY_START_INTERVAL_MINUTES,
    DAILY_START_KEY_BYTES,
    DAILY_START_PATH,
    DAILY_START_SAVE_FUNCTION,
    DAILY_START_STATUS_FUNCTION,
    REFRESH_FUNCTION_FILES,
    RefreshSetting,
)
from tracker.shared.errors import (
    DatabaseStructureMissingError,
    DatabaseUnavailableError,
    ValidationFailedError,
)

PROJECT: Final[str] = "https://abcdefghijklmnop.supabase.co"
FUNCTION_URL: Final[str] = f"{PROJECT}/functions/v1/refresh-now"
DAILY_URL: Final[str] = f"{FUNCTION_URL}/daily-start"
MIGRATION: Final[str] = "0017_daily_start"
SQL: Final[str] = (REPOSITORY_ROOT / "supabase" / "migrations" / f"{MIGRATION}.sql").read_text(
    encoding="utf-8"
)
FUNCTION_DIRECTORY: Final[Path] = REPOSITORY_ROOT / "supabase" / "functions" / "refresh-now"
DAILY_TS: Final[str] = (FUNCTION_DIRECTORY / "daily.ts").read_text(encoding="utf-8")
REFRESH_TS: Final[str] = (FUNCTION_DIRECTORY / "refresh.ts").read_text(encoding="utf-8")
INDEX_TS: Final[str] = (FUNCTION_DIRECTORY / "index.ts").read_text(encoding="utf-8")
WORKFLOW: Final[dict[Any, Any]] = yaml.safe_load(WORKFLOW_FILE.read_text(encoding="utf-8"))


def _ts_string(source: str, name: str) -> str:
    """The value of ``export const NAME = '…';`` in a TypeScript file."""
    found = re.search(rf"export const {name} = '([^']*)';", source)
    assert found is not None, name
    return found.group(1)


def _ts_number(source: str, name: str) -> int:
    """The value of ``export const NAME = 123;`` in a TypeScript file."""
    found = re.search(rf"export const {name} = ([\d_]+);", source)
    assert found is not None, name
    return int(found.group(1).replace("_", ""))


# --- Switching it on with "tracker setup refresh" ------------------------------------


def refresh_world(answers: list[str | bool] | None = None) -> World:
    """A world ready for the Refresh now step, whose helper deploys and guards."""
    env = configured_env() | {"DASHBOARD_BASE_URL": "https://you.vercel.app"}
    world = make_world(answers or [True, GOOD_GITHUB_TOKEN, GOOD_TOKEN], env)
    world.function_statuses = [404, 401]
    return world


@pytest.mark.asyncio
async def test_switching_on_refresh_now_also_switches_on_the_on_time_start() -> None:
    world = refresh_world()

    await RefreshStep().run(world.context())

    assert world.admin.daily_start == (DAILY_URL, DAILY_START_KEY)
    assert world.platform.secrets[RefreshSetting.DAILY_START_KEY] == DAILY_START_KEY
    assert world.admin.job_scheduled
    assert world.admin.schedule == (TEST_SCHEDULE.at, TEST_SCHEDULE.zone)
    text = world.io.text()
    assert (
        "On-time morning start is switched on: Supabase starts the daily run at 07:00 (UTC),"
        in (text)
    )
    assert DAILY_START_KEY not in text


@pytest.mark.asyncio
async def test_running_the_step_again_replaces_the_key_in_both_places() -> None:
    world = refresh_world(
        [True, GOOD_GITHUB_TOKEN, GOOD_TOKEN, True, GOOD_GITHUB_TOKEN, GOOD_TOKEN]
    )
    world.function_statuses = [401]
    keys = iter(
        ["first-key-0123456789abcdefghijklmnopqrstuv", "second-key-0123456789abcdefghijklmnopqrs"]
    )
    context = world.context()
    context = replace(
        context, gateways=replace(context.gateways, make_daily_start_key=lambda: next(keys))
    )

    await RefreshStep().run(context)
    await RefreshStep().run(context)

    second = "second-key-0123456789abcdefghijklmnopqrs"
    assert world.platform.secrets[RefreshSetting.DAILY_START_KEY] == second
    assert world.admin.daily_start == (DAILY_URL, second)


@pytest.mark.asyncio
async def test_a_database_without_the_structure_file_stops_with_the_fix() -> None:
    world = refresh_world()
    world.admin.present.discard(MIGRATION)

    with pytest.raises(ValidationFailedError, match="tracker setup database"):
        await RefreshStep().run(world.context())

    # Refresh now itself is in place; only the timer waits for the database.
    assert world.platform.deployed
    assert world.admin.daily_start is None


@dataclass
class _JoblessAdmin(FakeAdmin):
    """A database that saves the settings but whose timer never appears."""

    def save_daily_start(self, function_url: str, key: SecretStr) -> None:
        super().save_daily_start(function_url, key)
        self.job_scheduled = False


@pytest.mark.asyncio
async def test_a_timer_that_is_still_missing_afterwards_stops_the_step() -> None:
    world = refresh_world()
    world.admin = _JoblessAdmin()

    with pytest.raises(ValidationFailedError, match="timer is not in place"):
        await RefreshStep().run(world.context())


@pytest.mark.asyncio
async def test_an_unreadable_workflow_time_leaves_the_database_time_alone() -> None:
    world = refresh_world()
    world.workflow = FakeWorkflow("name: no schedule here\n")

    await RefreshStep().run(world.context())

    assert world.admin.schedule is None
    assert world.admin.daily_start == (DAILY_URL, DAILY_START_KEY)
    assert "The workflow's daily time could not be read" in world.io.text()


def test_the_key_is_long_and_new_every_time() -> None:
    first, second = make_daily_start_key(), make_daily_start_key()

    assert first != second
    assert len(first) >= _ts_number(DAILY_TS, "MIN_DAILY_START_KEY_LENGTH")
    assert _ts_number(DAILY_TS, "MIN_DAILY_START_KEY_LENGTH") <= DAILY_START_KEY_BYTES


def test_the_scheduled_path_is_below_the_refresh_function() -> None:
    assert daily_start_url(function_url(f"{PROJECT}/")) == DAILY_URL


# --- Keeping the database's time in step with the workflow --------------------------


def schedule_env(zone: str = "Europe/Rome") -> dict[str, str]:
    """A local set-up with the database in place and a saved zone."""
    return configured_env() | {"OWNER_TIME_ZONE": zone}


@pytest.mark.asyncio
async def test_a_new_daily_time_is_copied_into_the_database() -> None:
    world = make_world(["08:15", False], schedule_env())

    await ScheduleStep().run(world.context())

    assert world.admin.schedule == (time(8, 15), "Europe/Rome")
    assert "Saved the daily time in your database too: 08:15 (Europe/Rome)." in world.io.said


@pytest.mark.asyncio
async def test_an_unchanged_daily_time_is_still_put_right_in_the_database() -> None:
    world = make_world([""], schedule_env("UTC"))
    world.admin.schedule = (time(6, 0), "UTC")

    await ScheduleStep().run(world.context())

    assert world.workflow.writes == 0
    assert world.admin.schedule == (time(7, 0), "UTC")


@pytest.mark.asyncio
async def test_a_database_without_the_structure_file_names_the_fix_and_carries_on() -> None:
    world = make_world(["08:15", False], schedule_env())
    world.admin.present.discard(MIGRATION)

    await ScheduleStep().run(world.context())

    assert world.workflow.writes == 1
    assert world.admin.schedule is None
    assert any("uv run tracker setup database" in line for line in world.io.said)


@pytest.mark.asyncio
async def test_a_database_that_does_not_answer_names_the_fix_and_carries_on() -> None:
    world = make_world(["08:15", False], schedule_env())
    world.admin.daily_start_down = True

    await ScheduleStep().run(world.context())

    assert world.workflow.writes == 1
    assert "Your database did not answer, so it still has the old daily time." in world.io.said


@pytest.mark.asyncio
async def test_without_a_database_yet_only_the_workflow_changes() -> None:
    world = make_world(["08:15", False], {"OWNER_TIME_ZONE": "Europe/Rome"})

    await ScheduleStep().run(world.context())

    assert world.workflow.writes == 1
    assert world.admin.schedule is None
    assert not any("database" in line for line in world.io.said)


@pytest.mark.asyncio
async def test_a_new_time_zone_reaches_the_database_with_the_workflow(tmp_path: Path) -> None:
    workflow = tmp_path / "threadline-run.yml"
    workflow.write_text(
        write_schedule(
            WORKFLOW_FILE.read_text(encoding="utf-8"), Schedule(time(6, 30), "Europe/Rome")
        ),
        encoding="utf-8",
    )
    world = make_world(["America/New_York", True, ""], schedule_env())
    context = world.context()
    context = replace(context, gateways=replace(context.gateways, workflow=TextFile(workflow)))

    await TimeZoneStep().run(context)

    assert world.admin.schedule == (time(6, 30), "America/New_York")


# --- The doctor's line ----------------------------------------------------------------


def _status(**changes: Any) -> DailyStartStatus:
    """A switched-on timer at 07:00 Paris time, changed as asked."""
    base = DailyStartStatus(
        job_scheduled=True,
        switched_on=True,
        run_at=time(7, 0),
        time_zone="Europe/Paris",
        last_started_on=date(2026, 10, 5),
    )
    return replace(base, **changes)


def _check(
    status: DailyStartStatus | Exception,
    answer: int = 401,
    workflow: WorkflowTime | None = None,
) -> DailyStartCheck:
    def read_status() -> DailyStartStatus:
        if isinstance(status, Exception):
            raise status
        return status

    async def status_of_post(url: str) -> int:
        assert url == DAILY_URL
        return answer

    wanted = workflow or WorkflowTime(time(7, 0), "Europe/Paris")
    return DailyStartCheck(read_status, status_of_post, DAILY_URL, wanted)


@pytest.mark.asyncio
async def test_the_doctor_says_ok_with_the_time_and_the_last_start() -> None:
    result = await _check(_status()).run()

    assert result.status is CheckStatus.OK
    assert result.name == "On-time morning start"
    assert result.detail == (
        "on: Supabase starts the daily run at 07:00 (Europe/Paris); "
        "last started a run on 2026-10-05"
    )


@pytest.mark.asyncio
async def test_the_doctor_calls_a_timer_never_switched_on_optional() -> None:
    result = await _check(_status(switched_on=False, job_scheduled=False)).run()

    assert result.status is CheckStatus.WARNING
    assert result.detail.startswith("not switched on (optional)")
    assert result.fix == "run 'uv run tracker setup refresh'"


@pytest.mark.asyncio
async def test_the_doctor_points_a_database_without_the_file_to_the_database_step() -> None:
    result = await _check(DatabaseStructureMissingError("missing")).run()

    assert result.status is CheckStatus.WARNING
    assert result.fix.startswith("run 'uv run tracker setup database', then")


@pytest.mark.asyncio
async def test_the_doctor_finds_a_missing_timer_a_problem() -> None:
    result = await _check(_status(job_scheduled=False)).run()

    assert result.status is CheckStatus.PROBLEM
    assert "timer is missing or paused" in result.detail


@pytest.mark.parametrize("answer", [404, 500])
@pytest.mark.asyncio
async def test_the_doctor_finds_a_helper_that_does_not_guard_a_problem(answer: int) -> None:
    result = await _check(_status(), answer=answer).run()

    assert result.status is CheckStatus.PROBLEM
    assert result.detail == f"the helper answered status {answer}"


@pytest.mark.asyncio
async def test_the_doctor_warns_when_the_database_and_the_workflow_disagree() -> None:
    result = await _check(_status(), workflow=WorkflowTime(time(8, 30), "Europe/Paris")).run()

    assert result.status is CheckStatus.WARNING
    assert result.detail == (
        "the database starts it at 07:00 (Europe/Paris), the workflow at 08:30 (Europe/Paris)"
    )
    assert result.fix == "run 'uv run tracker setup schedule'"


@pytest.mark.asyncio
async def test_an_unreachable_database_is_one_problem_line_with_the_outage_advice() -> None:
    report = await DoctorService([_check(DatabaseUnavailableError("down"))]).run()

    [result] = report.results
    assert result.status is CheckStatus.PROBLEM
    assert "try again in a few minutes" in result.fix


# --- The service-key calls ------------------------------------------------------------


def test_the_daily_time_is_saved_with_its_zone_in_the_one_settings_row() -> None:
    client = MagicMock()

    SupabaseAdmin(client).save_daily_schedule(time(7, 5), "Europe/Paris")

    client.table.assert_called_once_with("app_settings")
    client.table.return_value.upsert.assert_called_once_with(
        [{"singleton": True, "time_zone": "Europe/Paris", "daily_run_time": "07:05"}],
        on_conflict="singleton",
    )


def test_the_address_and_key_go_to_the_database_function_only() -> None:
    client = MagicMock()

    SupabaseAdmin(client).save_daily_start(DAILY_URL, SecretStr(DAILY_START_KEY))

    client.rpc.assert_called_once_with(
        DAILY_START_SAVE_FUNCTION, {"function_url": DAILY_URL, "shared_key": DAILY_START_KEY}
    )


@pytest.mark.parametrize("code", ["PGRST202", "PGRST204", "42883"])
def test_a_missing_database_function_or_column_is_named_as_such(code: str) -> None:
    client = MagicMock()
    client.rpc.return_value.execute.side_effect = APIError({"code": code, "message": "x"})

    with pytest.raises(DatabaseStructureMissingError):
        SupabaseAdmin(client).daily_start_status()


def test_any_other_database_error_is_an_outage() -> None:
    client = MagicMock()
    client.rpc.return_value.execute.side_effect = APIError({"code": "57014", "message": "x"})

    with pytest.raises(DatabaseUnavailableError):
        SupabaseAdmin(client).save_daily_start(DAILY_URL, SecretStr(DAILY_START_KEY))


def test_the_status_is_read_from_the_database_function() -> None:
    client = MagicMock()
    client.rpc.return_value.execute.return_value.data = {
        "job_scheduled": True,
        "switched_on": True,
        "daily_run_time": "07:00",
        "time_zone": "Europe/Paris",
        "last_started_on": "2026-10-05",
    }

    status = SupabaseAdmin(client).daily_start_status()

    client.rpc.assert_called_once_with(DAILY_START_STATUS_FUNCTION, {})
    assert status == _status()
    assert status.ready


def test_a_status_of_another_shape_is_an_outage() -> None:
    client = MagicMock()
    client.rpc.return_value.execute.return_value.data = [1, 2]

    with pytest.raises(DatabaseUnavailableError):
        SupabaseAdmin(client).daily_start_status()


# --- The migration, read as text --------------------------------------------------------


def test_0016_is_seen_by_its_claim_table() -> None:
    assert KNOWN_MIGRATIONS[MIGRATION] == ColumnsProbe("daily_starts", "owner_date,requested_at")


def test_0016_is_safe_to_run_twice() -> None:
    assert SQL.count("create extension if not exists") == 3
    assert "add column if not exists daily_run_time time not null default '07:00'" in SQL
    assert "create table if not exists public.daily_starts" in SQL
    assert "drop trigger if exists daily_starts_set_updated_at" in SQL
    assert re.search(r"create (table|function|trigger) (?!if not exists)public", SQL) is None
    assert len(re.findall(r"create function", SQL)) == 0
    # Scheduling under a name that exists replaces that job.
    assert "cron.schedule(\n    'threadline-daily-start'," in SQL


def test_one_claim_per_owner_day_is_a_database_rule() -> None:
    assert "owner_date date not null unique" in SQL
    assert "'23505'" in INDEX_TS


def test_only_the_service_key_touches_the_claims() -> None:
    assert "alter table public.daily_starts enable row level security;" in SQL
    assert "revoke all on public.daily_starts from anon, authenticated;" in SQL
    assert re.search(r"grant [^;]* on public\.daily_starts to (anon|authenticated)", SQL) is None


def test_every_new_function_is_closed_to_the_public_key() -> None:
    functions = re.findall(r"create or replace function (public\.\w+)\(", SQL)

    assert len(functions) == 5
    for name in functions:
        assert re.search(
            rf"revoke execute on function {re.escape(name)}\([^)]*\)\s+from public, anon", SQL
        )


def test_only_saving_and_reading_the_state_are_open_to_the_service_key() -> None:
    granted = re.findall(r"grant execute on function (public\.\w+)\([^)]*\) to (\w+);", SQL)

    assert sorted(granted) == [
        ("public.daily_start_status", "service_role"),
        ("public.save_daily_start_settings", "service_role"),
    ]
    assert "public.request_daily_start()\n  from public, anon, authenticated, service_role;" in SQL


def test_the_key_only_ever_goes_to_the_functions_scheduled_path() -> None:
    pattern = re.search(r"function_url !~ '([^']+)'", SQL)

    assert pattern is not None
    assert re.fullmatch(pattern.group(1), DAILY_URL)
    assert not re.fullmatch(pattern.group(1), "https://evil.example/collect")
    assert not re.fullmatch(pattern.group(1), FUNCTION_URL)


def test_the_database_and_the_function_share_the_header_path_and_key_length() -> None:
    header = _ts_string(DAILY_TS, "DAILY_START_KEY_HEADER")
    minimum = _ts_number(DAILY_TS, "MIN_DAILY_START_KEY_LENGTH")

    assert f"'{header}', shared_key" in SQL
    assert f"char_length(shared_key) < {minimum}" in SQL
    assert _ts_string(DAILY_TS, "DAILY_START_PATH") == DAILY_START_PATH
    assert f"refresh-now{DAILY_START_PATH}$" in SQL
    assert "Deno.env.get('DAILY_START_KEY')" in INDEX_TS
    assert RefreshSetting.DAILY_START_KEY == "DAILY_START_KEY"


def test_the_timer_looks_as_often_as_the_set_up_says() -> None:
    assert f"'*/{DAILY_START_INTERVAL_MINUTES} * * * *'" in SQL


def test_the_function_starts_the_workflow_by_its_daily_title_and_mode() -> None:
    title = WORKFLOW["run-name"]
    triggers = WORKFLOW.get("on") or WORKFLOW[True]

    assert f"|| '{_ts_string(DAILY_TS, 'DAILY_RUN_TITLE')}' }}}}" in title
    assert (
        _ts_string(REFRESH_TS, "WORKFLOW_DAILY_MODE")
        in (triggers["workflow_dispatch"]["inputs"]["mode"]["options"])
    )


def test_the_deployed_files_are_the_functions_own_entry_point_first() -> None:
    files = read_refresh_function()

    assert tuple(files) == REFRESH_FUNCTION_FILES
    assert next(iter(files)) == "index.ts"
    assert "from './daily.ts';" in INDEX_TS
    # Flat files, as the deploy uploads them: nothing reaches outside the folder.
    for source in (INDEX_TS, DAILY_TS, REFRESH_TS):
        assert "from '../" not in source
