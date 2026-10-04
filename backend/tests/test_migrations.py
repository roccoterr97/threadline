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
from tests.setup_world import FakeAdmin
from tracker.domain.categories import UNKNOWN_CATEGORY, ColourSlot
from tracker.domain.enums import ContactStatus, RunTrigger
from tracker.services.database_structure import (
    KNOWN_MIGRATIONS,
    ColumnsProbe,
    EnumColumnProbe,
    MigrationFile,
    RowProbe,
    inspect_structure,
)
from tracker.shared.config import REPOSITORY_ROOT

MIGRATIONS: Final = REPOSITORY_ROOT / "supabase" / "migrations"
CATEGORIES_SQL: Final[str] = (MIGRATIONS / "0009_categories.sql").read_text(encoding="utf-8")
STATUS_SQL: Final[str] = (MIGRATIONS / "0010_status_in_process.sql").read_text(encoding="utf-8")
NAMES_SQL: Final[str] = (MIGRATIONS / "0015_category_names.sql").read_text(encoding="utf-8")
CATEGORY_SETTINGS: Final[str] = (
    REPOSITORY_ROOT / "frontend" / "src" / "domain" / "categorySettings.ts"
).read_text(encoding="utf-8")

#: The reserved category's group name as 0009 seeded it, before 0015.
SEEDED_UNKNOWN_GROUP: Final[str] = "Unknown"


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
        # 0015 renames the reserved row's group; the seed keeps the old word.
        seeded_group = SEEDED_UNKNOWN_GROUP if record.key == "unknown" else record.group_label
        assert f"'{record.key}', '{record.label}', '{seeded_group}'" in seed
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
    assert KNOWN_MIGRATIONS["0012_refresh_trigger"] == EnumColumnProbe("run_logs", "trigger")


def test_the_refresh_trigger_is_missing_while_the_column_is_still_text() -> None:
    admin = FakeAdmin(present=set(KNOWN_MIGRATIONS) - {"0012_refresh_trigger"})
    files = (MigrationFile("0012_refresh_trigger", MIGRATIONS / "0012_refresh_trigger.sql"),)

    report = inspect_structure(files, admin)

    # Filtering a text column by 'refresh' raises nothing, which is why the
    # probe must ask whether the column refuses an unlisted value instead.
    assert admin.accepts_value("run_logs", "trigger", RunTrigger.REFRESH.value) is True
    assert report.missing == ("0012_refresh_trigger",)


def test_the_refresh_trigger_is_present_once_the_column_is_an_enum() -> None:
    files = (MigrationFile("0012_refresh_trigger", MIGRATIONS / "0012_refresh_trigger.sql"),)

    report = inspect_structure(files, FakeAdmin())

    assert report.present == ("0012_refresh_trigger",)


COOLDOWN_SQL: Final[str] = (MIGRATIONS / "0014_refresh_cooldown.sql").read_text(encoding="utf-8")
REFRESH_FUNCTION: Final[str] = (
    REPOSITORY_ROOT / "supabase" / "functions" / "refresh-now" / "refresh.ts"
).read_text(encoding="utf-8")


def test_the_database_and_the_function_agree_on_the_cool_down() -> None:
    in_function = re.search(r"REFRESH_COOLDOWN_MINUTES = (\d+);", REFRESH_FUNCTION)
    in_database = re.search(r"set default \(now\(\) \+ interval '(\d+) minutes'\)", COOLDOWN_SQL)

    assert in_function is not None
    assert in_database is not None
    assert in_function.group(1) == in_database.group(1)


def test_only_one_request_can_hold_the_cool_down() -> None:
    constraint = _statement(COOLDOWN_SQL, "add constraint refresh_requests_one_per_cooldown")

    exclusion = "exclude using gist (tstzrange(requested_at, cooldown_until, '[)') with &&)"
    assert exclusion in constraint


def test_the_owner_may_withdraw_a_request_but_never_set_its_cool_down() -> None:
    assert "for delete to authenticated using (public.is_app_owner());" in COOLDOWN_SQL
    grants = [line for line in COOLDOWN_SQL.splitlines() if line.startswith("grant ")]
    assert grants == ["grant delete on public.refresh_requests to authenticated;"]


def test_the_function_claims_the_cool_down_before_it_asks_the_runner() -> None:
    handler = REFRESH_FUNCTION[REFRESH_FUNCTION.index("export async function handleRefresh") :]

    assert handler.index("await claimTurn(") < handler.index("await dispatch(")
    assert "'23P01'" in REFRESH_FUNCTION


def test_the_cool_down_column_shows_whether_0014_is_applied() -> None:
    assert KNOWN_MIGRATIONS["0014_refresh_cooldown"] == ColumnsProbe(
        "refresh_requests", "cooldown_until"
    )


@pytest.mark.parametrize("column", ["label", "group_label"])
def test_names_are_unique_ignoring_capitals_and_spaces(column: str) -> None:
    index = _statement(NAMES_SQL, f"create unique index if not exists categories_{column}_unique")

    assert f"on public.categories (lower(btrim({column})))" in index


@pytest.mark.parametrize("column", ["label", "group_label"])
def test_the_dashboard_knows_which_name_an_index_guards(column: str) -> None:
    assert f"'categories_{column}_unique'" in CATEGORY_SETTINGS


def test_clashing_names_are_told_apart_before_the_indexes_exist() -> None:
    assert NAMES_SQL.index("array['label', 'group_label']") < NAMES_SQL.index("create unique index")


def test_only_the_seeded_group_name_of_the_reserved_row_is_replaced() -> None:
    update = _statement(NAMES_SQL, "update public.categories\n       set group_label")

    assert f"set group_label = '{UNKNOWN_CATEGORY.group_label}'" in update
    assert f"and group_label = '{SEEDED_UNKNOWN_GROUP}'" in update


def test_the_guard_is_back_on_in_the_same_statement_that_turned_it_off() -> None:
    block = NAMES_SQL[NAMES_SQL.index("do $$") : NAMES_SQL.index("$$;") + 3]

    assert block.count("disable trigger categories_guard") == 1
    assert block.index("disable trigger categories_guard") < block.index(
        "enable trigger categories_guard"
    )


def test_0015_is_seen_by_the_group_name_it_gives_the_reserved_row() -> None:
    """The indexes cannot be seen from outside; the renamed group can."""
    marker = KNOWN_MIGRATIONS["0015_category_names"]

    assert marker == RowProbe(
        "categories",
        (("key", UNKNOWN_CATEGORY.key), ("group_label", UNKNOWN_CATEGORY.group_label)),
    )
    assert f"('unknown', 'Not known', '{SEEDED_UNKNOWN_GROUP}'," in CATEGORIES_SQL
    assert UNKNOWN_CATEGORY.group_label != SEEDED_UNKNOWN_GROUP


def test_nothing_but_0015_may_change_the_reserved_row() -> None:
    guard = CATEGORIES_SQL[
        CATEGORIES_SQL.index("create or replace function public.categories_guard") :
    ]

    assert "if tg_op = 'UPDATE' and old.key = 'unknown'" in guard
    assert 'the category "unknown" is reserved and cannot be changed' in guard


NOTES_SQL: Final[str] = (MIGRATIONS / "0016_person_notes.sql").read_text(encoding="utf-8")
NOTES_CONSTANTS: Final[str] = (
    REPOSITORY_ROOT / "frontend" / "src" / "constants" / "notes.ts"
).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("action", "clause"),
    [
        ("insert", "with check (public.is_app_owner())"),
        ("update", "using (public.is_app_owner()) with check (public.is_app_owner())"),
        ("delete", "using (public.is_app_owner())"),
        ("select", "using (public.is_app_owner())"),
    ],
)
def test_only_the_owner_may_touch_the_notes(action: str, clause: str) -> None:
    policies = re.findall(
        r"create policy \"[^\"]+\" on public\.person_notes\s+for (\w+) to (\w+) ([^;]+);",
        NOTES_SQL,
    )

    matching = [policy for policy in policies if policy[0] == action]
    assert len(matching) == 1
    assert matching[0][1] == "authenticated"
    assert " ".join(matching[0][2].split()) == clause


def test_the_public_key_gets_no_notes() -> None:
    assert "alter table public.person_notes enable row level security;" in NOTES_SQL
    assert "revoke all on public.person_notes from anon, authenticated;" in NOTES_SQL
    assert re.search(r"grant [^;]* to [^;]*\banon\b", NOTES_SQL) is None


def test_the_dashboard_can_only_write_a_notes_text_and_person() -> None:
    """A note can never be moved to another person or given another date from the dashboard."""
    grants = re.findall(r"grant ([^;]+) on public\.person_notes to authenticated;", NOTES_SQL)

    assert grants == ["select", "insert (person_id, body)", "update (body)", "delete"]


def test_a_note_goes_with_its_person() -> None:
    assert "references public.people (id) on delete cascade" in NOTES_SQL


def test_a_note_cannot_be_blank_and_the_dashboard_holds_the_same_limit() -> None:
    check = re.search(r"body text not null check \((.+)\)", NOTES_SQL)
    limit = re.search(r"MAX_NOTE_LENGTH = (\d+);", NOTES_CONSTANTS)

    assert check is not None
    assert limit is not None
    assert check.group(1) == rf"body ~ '\S' and char_length(body) <= {limit.group(1)}"


def test_moving_a_note_to_the_surviving_record_does_not_count_as_an_edit() -> None:
    trigger = _statement(NOTES_SQL, "create trigger person_notes_set_updated_at")

    assert "when (old.body is distinct from new.body)" in trigger
    assert "execute function public.set_updated_at()" in trigger


def test_0016_is_seen_by_the_notes_table_without_reading_a_note() -> None:
    marker = ColumnsProbe("person_notes", "id,person_id")

    assert KNOWN_MIGRATIONS["0016_person_notes"] == marker
    assert "body" not in marker.columns
