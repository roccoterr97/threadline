"""The Plan 19 migrations, read as text.

SQL cannot run in these tests (there is no database), so the rules that keep
the owner's data safe are checked where they are written: who may write the
categories, what the owner may never change, and that the seed matches what
the Python side and the job-search preset expect.
"""

from __future__ import annotations

import re
from typing import Final

import pytest

from tests.assessment_world import CATEGORIES
from tracker.domain.categories import ColourSlot
from tracker.domain.enums import ContactStatus, RunTrigger
from tracker.services.database_structure import KNOWN_MIGRATIONS, EnumValueProbe
from tracker.shared.config import REPOSITORY_ROOT

MIGRATIONS: Final = REPOSITORY_ROOT / "supabase" / "migrations"
CATEGORIES_SQL: Final[str] = (MIGRATIONS / "0009_categories.sql").read_text(encoding="utf-8")
STATUS_SQL: Final[str] = (MIGRATIONS / "0010_status_in_process.sql").read_text(encoding="utf-8")


def _statement(sql: str, start: str) -> str:
    """The one statement that begins with ``start``, up to its semicolon."""
    begin = sql.index(start)
    return sql[begin : sql.index(";", begin) + 1]


@pytest.mark.parametrize(
    ("action", "clause"),
    [
        ("insert", "with check (public.is_app_owner())"),
        ("update", "using (public.is_app_owner()) with check (public.is_app_owner())"),
        ("delete", "using (public.is_app_owner())"),
        ("select", "using (public.is_app_owner())"),
    ],
)
def test_only_the_owner_may_touch_the_categories(action: str, clause: str) -> None:
    policies = re.findall(
        r"create policy \"[^\"]+\" on public\.categories\s+for (\w+) to (\w+) ([^;]+);",
        CATEGORIES_SQL,
    )

    matching = [policy for policy in policies if policy[0] == action]
    assert len(matching) == 1
    assert matching[0][1] == "authenticated"
    assert " ".join(matching[0][2].split()) == clause


def test_the_public_key_gets_nothing() -> None:
    assert "revoke all on public.categories from anon, authenticated;" in CATEGORIES_SQL
    assert "revoke all on public.category_suggestions from anon, authenticated;" in CATEGORIES_SQL
    assert "revoke all on public.status_labels from anon, authenticated;" in STATUS_SQL
    assert re.search(r"grant [^;]* to [^;]*\banon\b", CATEGORIES_SQL + STATUS_SQL) is None


def test_an_edit_on_the_dashboard_can_never_change_a_key() -> None:
    update = _statement(CATEGORIES_SQL, "grant update (")

    assert "key" not in update.split("(")[1].split(")")[0].split(", ")
    assert "on public.categories to authenticated" in update


def test_the_owner_cannot_write_suggestions_or_stage_labels() -> None:
    owner_grants = re.findall(r"grant ([^;]+) on public\.(\w+) to authenticated;", CATEGORIES_SQL)
    owner_grants += re.findall(r"grant ([^;]+) on public\.(\w+) to authenticated;", STATUS_SQL)

    assert ("select", "category_suggestions") in owner_grants
    assert ("select", "status_labels") in owner_grants
    writes = [grant for grant in owner_grants if grant[0] != "select"]
    assert {table for _, table in writes} == {"categories"}


def test_unknown_and_the_limit_are_guarded_by_the_database() -> None:
    assert "before insert or update or delete on public.categories" in CATEGORIES_SQL
    assert 'the category "unknown" is reserved and cannot be removed' in CATEGORIES_SQL
    assert 'the category "unknown" is reserved and cannot be changed' in CATEGORIES_SQL
    assert ") >= 8 then" in CATEGORIES_SQL
    assert "check (key <> 'unknown' or archived_at is null)" in CATEGORIES_SQL


def test_every_new_function_is_closed_to_the_public_key() -> None:
    functions = re.findall(r"create or replace function (public\.\w+\(\))", CATEGORIES_SQL)

    for function in functions:
        assert f"revoke execute on function {function} from public, anon;" in CATEGORIES_SQL


def test_the_colour_check_lists_exactly_the_palette() -> None:
    listed = re.findall(r"colour in \(([^)]+)\)", CATEGORIES_SQL)
    expected = {slot.value for slot in ColourSlot}

    assert listed
    for slots in listed:
        assert {slot.strip().strip("'") for slot in slots.split(",")} == expected


def test_the_seed_is_the_job_search_list_the_code_expects() -> None:
    seed = _statement(CATEGORIES_SQL, "insert into public.categories")

    for record in CATEGORIES:
        assert f"'{record.key}', '{record.label}', '{record.group_label}'" in seed
        assert f"'{record.description}'" in seed
        assert f"'{record.colour.value}', {record.sort_order})" in seed


def test_every_stage_gets_a_seeded_label() -> None:
    seed = _statement(STATUS_SQL, "insert into public.status_labels")

    for status in ContactStatus:
        assert f"('{status.value}', '" in seed


def test_the_run_trigger_type_lists_every_trigger_python_records() -> None:
    sql = (MIGRATIONS / "0012_refresh_trigger.sql").read_text(encoding="utf-8")
    created = re.search(r"create type public\.run_trigger as enum \(([^)]*)\)", sql)

    assert created is not None
    listed = [value.strip().strip("'") for value in created.group(1).split(",")]
    assert listed == [trigger.value for trigger in RunTrigger]


def test_the_refresh_trigger_can_be_seen_from_outside() -> None:
    assert KNOWN_MIGRATIONS["0012_refresh_trigger"] == EnumValueProbe(
        "run_logs", "trigger", RunTrigger.REFRESH.value
    )
