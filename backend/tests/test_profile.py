"""The owner's profile: loading, validation, the guide, and applying it to the database."""

from __future__ import annotations

import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from tests.assessment_world import CATEGORIES, make_override, make_person, seed
from tests.conftest import FakeSupabaseClient, as_client
from tracker.cli.main import build_cli
from tracker.domain.categories import UNKNOWN_CATEGORY_KEY, Category, ColourSlot, key_for
from tracker.domain.enums import ContactStatus
from tracker.domain.profile import Profile
from tracker.repositories import Repositories, build_repositories
from tracker.services.profile.applier import ProfileApplier
from tracker.services.profile.guide import render_guide, write_guide
from tracker.services.profile.loader import (
    load_profile,
    preset_names,
    preset_path,
    read_profile,
)
from tracker.shared.clock import FixedClock
from tracker.shared.constants.profile import GUIDE_FILE, GUIDE_TEMPLATE_FILE, MAX_CATEGORIES
from tracker.shared.errors import ConfigurationError

EXPECTED_PRESETS = (
    "freelance_clients",
    "fundraising",
    "job_search",
    "networking",
    "sales_outreach",
)


def _raw(preset: str = "job_search") -> dict[str, Any]:
    """A preset's contents as plain data, ready to be broken on purpose."""
    with preset_path(preset).open("rb") as handle:
        return tomllib.load(handle)


def _write(tmp_path: Path, raw: dict[str, Any]) -> Path:
    """Write profile data as TOML, the small subset the tests need."""
    path = tmp_path / "profile.toml"
    path.write_text(_toml(raw), encoding="utf-8")
    return path


def _toml(raw: dict[str, Any]) -> str:
    """Render nested dictionaries and lists of tables as TOML."""
    lines: list[str] = []
    tables: list[tuple[str, dict[str, Any]]] = []
    for key, value in raw.items():
        if isinstance(value, dict):
            tables.append((key, value))
        elif isinstance(value, list):
            tables.extend((f"[{key}]", item) for item in value)
        else:
            lines.append(f"{key} = {_value(value)}")
    for name, table in tables:
        lines.extend(_table(name, table))
    return "\n".join(lines) + "\n"


def _table(name: str, table: dict[str, Any]) -> list[str]:
    """One table, with sub-tables flattened into dotted names."""
    lines = [f"[{name}]"]
    nested: list[str] = []
    for key, value in table.items():
        if isinstance(value, dict):
            nested.extend(_table(f"{name}.{key}", value))
        else:
            lines.append(f"{key} = {_value(value)}")
    return [*lines, *nested]


def _value(value: object) -> str:
    """A TOML string, or an array of them."""
    if isinstance(value, list):
        return "[" + ", ".join(_value(item) for item in value) + "]"
    text = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{text}"'


def _template() -> str:
    """The real guide template."""
    return GUIDE_TEMPLATE_FILE.read_text(encoding="utf-8")


def _profile(**changes: object) -> Profile:
    """The job-search profile with some top-level values replaced."""
    raw = _raw()
    raw.update(changes)
    return Profile.model_validate(raw)


# --- Presets --------------------------------------------------------------------


def test_the_five_presets_are_shipped() -> None:
    assert preset_names() == EXPECTED_PRESETS


@pytest.mark.parametrize("name", EXPECTED_PRESETS)
def test_every_preset_loads_and_renders_a_guide(name: str) -> None:
    profile = read_profile(preset_path(name))
    guide = _render(_template(), profile)

    assert profile.name == name
    assert profile.all_categories()[-1].key == UNKNOWN_CATEGORY_KEY
    assert "{{" not in guide
    for category in profile.all_categories():
        assert f"| `{category.key}` |" in guide


def test_the_job_search_preset_keeps_todays_categories() -> None:
    profile = read_profile(preset_path("job_search"))

    assert list(profile.all_categories()) == [record.to_category() for record in CATEGORIES]
    assert profile.stage(ContactStatus.IN_PROCESS).label == "In a hiring process"


def test_the_committed_guide_is_the_job_search_rendering() -> None:
    """docs/assessment-guide.md must never drift from its template, preset and seed."""
    profile = read_profile(preset_path("job_search"))
    seeded = [record.to_category() for record in CATEGORIES]

    rendered = render_guide(
        _template(), profile, seeded, template_name=GUIDE_TEMPLATE_FILE.name
    )

    assert GUIDE_FILE.read_text(encoding="utf-8") == rendered


# --- Loading --------------------------------------------------------------------


def test_without_a_profile_file_the_job_search_preset_is_used(tmp_path: Path) -> None:
    loaded = load_profile(tmp_path / "profile.toml")

    assert loaded.is_default
    assert loaded.profile.name == "job_search"


def test_the_owners_own_profile_wins(tmp_path: Path) -> None:
    path = _write(tmp_path, _raw("sales_outreach"))

    loaded = load_profile(path)

    assert not loaded.is_default
    assert loaded.source == path
    assert [c.key for c in loaded.profile.all_categories()] == [
        "prospect",
        "customer",
        "partner",
        "referrer",
        UNKNOWN_CATEGORY_KEY,
    ]


def test_categories_are_ordered_as_written_with_unknown_last() -> None:
    orders = [c.sort_order for c in read_profile(preset_path("job_search")).all_categories()]

    assert orders == [10, 20, 30, 1000]


def _broken(tmp_path: Path, mutate: Any) -> str:
    """Break the job-search profile one way and return the error message."""
    raw = _raw()
    mutate(raw)
    with pytest.raises(ConfigurationError) as caught:
        read_profile(_write(tmp_path, raw))
    return caught.value.message


def test_a_key_with_capitals_or_spaces_is_refused(tmp_path: Path) -> None:
    message = _broken(tmp_path, lambda raw: raw["categories"][0].update(key="Big Startup"))

    assert "categories.0.key" in message


def test_a_duplicate_key_is_refused(tmp_path: Path) -> None:
    message = _broken(tmp_path, lambda raw: raw["categories"][1].update(key="startup"))

    assert "unique" in message
    assert "startup" in message


def test_a_colour_outside_the_palette_is_refused(tmp_path: Path) -> None:
    message = _broken(tmp_path, lambda raw: raw["categories"][0].update(colour="gold"))

    assert "categories.0.colour" in message


def test_listing_unknown_is_refused_because_it_is_reserved(tmp_path: Path) -> None:
    def add_unknown(raw: dict[str, Any]) -> None:
        raw["categories"].append(
            {
                "key": "unknown",
                "label": "Unknown",
                "group_label": "Unknown",
                "colour": "grey",
                "description": "Not clear.",
            }
        )

    assert "reserved" in _broken(tmp_path, add_unknown)


def test_all_is_refused_because_the_dashboard_filters_use_it(tmp_path: Path) -> None:
    message = _broken(tmp_path, lambda raw: raw["categories"][0].update(key="all"))

    assert "reserved" in message


def test_a_profile_without_unknown_still_gets_it() -> None:
    keys = [c.key for c in read_profile(preset_path("networking")).all_categories()]

    assert keys.count(UNKNOWN_CATEGORY_KEY) == 1


def test_a_missing_stage_is_refused(tmp_path: Path) -> None:
    message = _broken(tmp_path, lambda raw: raw["stages"].pop("gone_quiet"))

    assert "gone_quiet" in message


def test_a_question_that_does_not_name_the_person_is_refused(tmp_path: Path) -> None:
    message = _broken(
        tmp_path, lambda raw: raw["wording"].update(relevance_question="Is this relevant?")
    )

    assert "{name}" in message


def test_too_many_categories_are_refused(tmp_path: Path) -> None:
    def overfill(raw: dict[str, Any]) -> None:
        template = raw["categories"][0]
        raw["categories"] = [
            {**template, "key": f"kind_{index}"} for index in range(MAX_CATEGORIES + 1)
        ]

    assert "categories" in _broken(tmp_path, overfill)


def test_a_file_that_is_not_toml_is_one_clean_error(tmp_path: Path) -> None:
    path = tmp_path / "profile.toml"
    path.write_text("name = [unclosed", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="not valid TOML"):
        read_profile(path)


def test_an_unknown_preset_names_the_real_ones() -> None:
    with pytest.raises(ConfigurationError, match="sales_outreach"):
        preset_path("../secrets")


# --- The guide ------------------------------------------------------------------


def _render(template: str, profile: Profile) -> str:
    """Render with the profile's own suggestions as the owner's categories."""
    return render_guide(template, profile, profile.all_categories(), template_name="t")


def test_renaming_a_stage_renames_it_in_the_guidance_too() -> None:
    raw = _raw()
    raw["stages"]["in_process"]["label"] = "Interviewing"

    guide = _render(_template(), Profile.model_validate(raw))

    assert "In a hiring process" not in guide
    assert "| `in_process` | Interviewing |" in guide
    assert "**Interviewing**" in guide


def test_gone_quiet_always_says_the_tracker_sets_it() -> None:
    assert "Threadline sets this one by date" in _render("{{stage_table}}", _profile())


def test_an_unknown_placeholder_is_refused() -> None:
    with pytest.raises(ConfigurationError, match="placeholder"):
        _render("{{nonsense}}", _profile())


def test_an_unknown_placeholder_in_the_guidance_is_refused() -> None:
    raw = _raw()
    raw["guidance"]["relevance"] = "See {{category_table}}"

    with pytest.raises(ConfigurationError, match="placeholder"):
        _render("{{relevance_guidance}}", Profile.model_validate(raw))


def test_a_pipe_in_a_label_cannot_break_the_table() -> None:
    raw = _raw()
    raw["categories"][0]["label"] = "Start|up"

    guide = _render("{{category_table}}", Profile.model_validate(raw))

    assert "| `startup` | Start\\|up |" in guide


def test_the_guide_lists_the_owners_categories_not_the_presets() -> None:
    own = [
        Category(
            key="supplier",
            label="Supplier",
            group_label="Suppliers",
            description="Sells to you.",
            colour=ColourSlot.BROWN,
            sort_order=10,
        )
    ]

    guide = render_guide("{{category_table}}", _profile(), own, template_name="t")

    assert "| `supplier` | Supplier | Sells to you. |" in guide
    assert "`startup`" not in guide


# --- Keys for new categories ------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "taken", "expected"),
    [
        ("Press contacts", set(), "press_contacts"),
        ("  Big -- Clients! ", set(), "big_clients"),
        ("2nd degree", set(), "c_2nd_degree"),
        ("Supplier", {"supplier"}, "supplier_2"),
        ("Supplier", {"supplier", "supplier_2"}, "supplier_3"),
        ("All", set(), "all_2"),
        ("Unknown", set(), "unknown_2"),
        ("???", set(), "category"),
        ("x" * 50, set(), "x" * 31),
    ],
)
def test_a_new_categorys_key_is_made_from_its_label(
    label: str, taken: set[str], expected: str
) -> None:
    assert key_for(label, taken) == expected


# --- Applying -------------------------------------------------------------------


@pytest.fixture
def applier(repositories: Repositories, clock: FixedClock) -> ProfileApplier:
    return ProfileApplier(repositories, clock)


def _preset(name: str) -> Profile:
    return read_profile(preset_path(name))


def test_applying_writes_stage_labels_and_suggestions_but_not_categories(
    applier: ProfileApplier,
    repositories: Repositories,
) -> None:
    seed(repositories)

    report = applier.apply(_preset("sales_outreach"))

    assert report.stages == len(ContactStatus)
    labels = {row.status: row.label for row in repositories.status_labels.list()}
    assert labels[ContactStatus.IN_PROCESS] == "In a deal"
    suggested = [row.key for row in repositories.category_suggestions.list_all()]
    assert suggested == ["prospect", "customer", "partner", "referrer"]
    assert [row.key for row in repositories.categories.list_all()] == [
        record.key for record in CATEGORIES
    ]


def test_suggestions_of_another_preset_replace_the_old_ones(
    applier: ProfileApplier,
    repositories: Repositories,
) -> None:
    applier.apply(_preset("sales_outreach"))

    applier.apply(_preset("networking"))

    suggested = [row.key for row in repositories.category_suggestions.list_all()]
    assert suggested == ["contact", "mentor", "peer"]


def test_a_category_nobody_uses_is_deleted(
    applier: ProfileApplier,
    repositories: Repositories,
) -> None:
    seed(repositories)

    changes = applier.replace_categories(_preset("networking").all_categories())

    assert set(changes.deleted) == {"startup", "vc", "network"}
    assert changes.archived == ()
    assert {row.key for row in repositories.categories.list_all()} == {
        "contact",
        "mentor",
        "peer",
        UNKNOWN_CATEGORY_KEY,
    }


def test_a_category_a_person_has_is_archived_not_deleted(
    applier: ProfileApplier,
    repositories: Repositories,
    clock: FixedClock,
) -> None:
    seed(repositories, people=[make_person(person_type="vc")])

    changes = applier.replace_categories(_preset("networking").all_categories())

    assert changes.archived == ("vc",)
    investors = next(row for row in repositories.categories.list_all() if row.key == "vc")
    assert investors.archived_at == clock.now()
    assert repositories.categories.active_keys() == {"contact", "mentor", "peer", "unknown"}


def test_a_category_only_an_override_names_is_archived_too(
    applier: ProfileApplier,
    repositories: Repositories,
) -> None:
    person = make_person()
    seed(repositories, people=[person], overrides=[make_override(person, person_type="network")])

    changes = applier.replace_categories(_preset("networking").all_categories())

    assert changes.archived == ("network",)


def test_unknown_is_kept_even_when_the_new_list_leaves_it_out(
    applier: ProfileApplier,
    repositories: Repositories,
) -> None:
    seed(repositories)

    changes = applier.replace_categories(_preset("networking").suggestions())

    assert UNKNOWN_CATEGORY_KEY in changes.saved
    assert UNKNOWN_CATEGORY_KEY not in changes.deleted
    assert UNKNOWN_CATEGORY_KEY in repositories.categories.active_keys()


def test_replacing_twice_keeps_the_first_archive_date_and_the_row_ids(
    repositories: Repositories,
) -> None:
    seed(repositories, people=[make_person(person_type="vc")])
    first_moment = FixedClock(datetime(2026, 9, 1, tzinfo=UTC))
    networking = _preset("networking").all_categories()
    ProfileApplier(repositories, first_moment).replace_categories(networking)
    ids = {row.key: row.id for row in repositories.categories.list_all()}

    later = FixedClock(datetime(2026, 9, 20, tzinfo=UTC))
    ProfileApplier(repositories, later).replace_categories(networking)

    rows = repositories.categories.list_all()
    assert {row.key: row.id for row in rows} == ids
    assert next(row for row in rows if row.key == "vc").archived_at == first_moment.now()


def test_listing_an_archived_category_again_brings_it_back(
    applier: ProfileApplier,
    repositories: Repositories,
) -> None:
    seed(repositories, people=[make_person(person_type="vc")])
    applier.replace_categories(_preset("networking").all_categories())

    applier.replace_categories(_preset("job_search").all_categories())

    assert "vc" in repositories.categories.active_keys()


def test_a_change_made_on_the_dashboard_reaches_the_guide(
    applier: ProfileApplier,
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    tmp_path: Path,
) -> None:
    """The dashboard writes the table directly; the next render must follow it."""
    seed(repositories)
    rows = fake_client.tables["categories"]
    next(row for row in rows if row["key"] == "vc")["label"] = "Fund partner"
    rows.append(
        {
            "key": "press",
            "label": "Press contact",
            "group_label": "Press contacts",
            "description": "A journalist or editor.",
            "colour": "pink",
            "sort_order": 40,
            "archived_at": None,
        }
    )
    next(row for row in rows if row["key"] == "network")["archived_at"] = "2026-09-20T00:00:00Z"
    guide = tmp_path / "guide.md"

    write_guide(_preset("job_search"), applier.current_categories(), GUIDE_TEMPLATE_FILE, guide)

    text = guide.read_text(encoding="utf-8")
    assert "| `vc` | Fund partner |" in text
    assert "| `press` | Press contact | A journalist or editor. |" in text
    assert "`network`" not in text


# --- The commands ---------------------------------------------------------------


def test_profile_check_prints_the_categories_without_a_database() -> None:
    result = CliRunner().invoke(build_cli(), ["profile", "check", "--preset", "fundraising"])

    assert result.exit_code == 0, result.output
    assert "investor: Investor (Investors) · cyan" in result.output
    assert "unknown: Not known (Unknown) · grey · always there" in result.output
    assert "in_process: In due diligence" in result.output


def test_profile_check_says_when_the_default_preset_stands_in(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        build_cli(), ["profile", "check", "--file", str(tmp_path / "missing.toml")]
    )

    assert result.exit_code == 0, result.output
    assert "notice:" in result.output
    assert "job_search" in result.output


@pytest.fixture
def database(monkeypatch: pytest.MonkeyPatch) -> FakeSupabaseClient:
    """An in-memory database behind the profile commands, seeded like 0009."""
    client = FakeSupabaseClient({"app_settings": [{"singleton": True, "time_zone": "UTC"}]})
    build_repositories(as_client(client)).categories.save(CATEGORIES)
    monkeypatch.setattr(
        "tracker.cli.commands.profile.create_database_client",
        lambda _settings: as_client(client),
    )
    return client


@pytest.mark.usefixtures("valid_environment")
def test_profile_apply_leaves_the_categories_and_writes_the_guide(
    database: FakeSupabaseClient,
    tmp_path: Path,
) -> None:
    guide = tmp_path / "guide.md"
    profile = _write(tmp_path, _raw("freelance_clients"))

    result = CliRunner().invoke(
        build_cli(), ["profile", "apply", "--file", str(profile), "--guide", str(guide)]
    )

    assert result.exit_code == 0, result.output
    assert "stage labels saved: 6" in result.output
    assert "suggestions saved: 4" in result.output
    text = guide.read_text(encoding="utf-8")
    assert "| `startup` | Startup |" in text
    assert "Proposal sent" in text
    assert len(database.tables["categories"]) == len(CATEGORIES)


@pytest.mark.usefixtures("valid_environment")
def test_profile_apply_with_categories_takes_the_files_list(
    database: FakeSupabaseClient,
    tmp_path: Path,
) -> None:
    profile = _write(tmp_path, _raw("freelance_clients"))
    guide = tmp_path / "guide.md"

    result = CliRunner().invoke(
        build_cli(),
        ["profile", "apply", "--file", str(profile), "--guide", str(guide), "--categories"],
    )

    assert result.exit_code == 0, result.output
    assert "categories saved: 5 · archived: none · deleted: startup, vc, network" in result.output
    assert "| `past_client` | Past client |" in guide.read_text(encoding="utf-8")


@pytest.mark.usefixtures("valid_environment")
def test_profile_choose_keeps_some_suggestions_adds_one_and_remembers_the_preset(
    database: FakeSupabaseClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "tracker.cli.commands.profile.PROFILE_FILE", tmp_path / "no-profile.toml"
    )
    guide = tmp_path / "guide.md"
    answers = "\n".join(
        [
            "5",  # Sales outreach
            "n",  # not all of them, I will pick
            "y",  # keep Prospect
            "y",  # keep Customer
            "n",  # drop Partner
            "n",  # drop Referrer
            "y",  # add one of my own
            "Press contact",
            "",  # accept "Press contacts"
            "A journalist or editor who writes about us.",
            "pink",
            "n",  # no more
            "y",  # save
        ]
    )

    result = CliRunner().invoke(
        build_cli(), ["profile", "choose", "--guide", str(guide)], input=answers + "\n"
    )

    assert result.exit_code == 0, result.output
    stored = build_repositories(as_client(database))
    assert stored.categories.active_keys() == {
        "prospect",
        "customer",
        "press_contact",
        UNKNOWN_CATEGORY_KEY,
    }
    assert stored.app_settings.read_preset() == "sales_outreach"
    assert "| `press_contact` | Press contact |" in guide.read_text(encoding="utf-8")
    assert "In a deal" in guide.read_text(encoding="utf-8")


@pytest.mark.usefixtures("valid_environment")
def test_profile_choose_saves_nothing_when_the_owner_says_no(
    database: FakeSupabaseClient,
) -> None:
    answers = "\n".join(["3", "n", "y", "y", "y", "n", "n"])

    result = CliRunner().invoke(build_cli(), ["profile", "choose"], input=answers + "\n")

    assert result.exit_code == 0, result.output
    assert "nothing saved" in result.output
    assert build_repositories(as_client(database)).app_settings.read_preset() is None


@pytest.mark.usefixtures("valid_environment")
def test_a_bad_colour_is_asked_again(
    database: FakeSupabaseClient,
    tmp_path: Path,
) -> None:
    answers = "\n".join(
        ["3", "n", "n", "n", "n", "y", "Supplier", "", "Sells to us.", "gold", "Supplier", "",
         "Sells to us.", "brown", "n", "y"]
    )

    result = CliRunner().invoke(
        build_cli(),
        ["profile", "choose", "--guide", str(tmp_path / "g.md")],
        input=answers + "\n",
    )

    assert result.exit_code == 0, result.output
    assert "That did not work" in result.output
    stored = build_repositories(as_client(database)).categories.active_keys()
    assert stored == {"supplier", UNKNOWN_CATEGORY_KEY}


@pytest.mark.usefixtures("valid_environment")
def test_profile_choose_keeps_every_suggestion_on_one_yes(
    database: FakeSupabaseClient,
    tmp_path: Path,
) -> None:
    answers = "\n".join(
        [
            "3",  # Job search
            "y",  # use all of them
            "n",  # nothing of my own
            "y",  # save
        ]
    )

    result = CliRunner().invoke(
        build_cli(),
        ["profile", "choose", "--guide", str(tmp_path / "g.md")],
        input=answers + "\n",
    )

    assert result.exit_code == 0, result.output
    assert "Keep the ones you use" not in result.output
    stored = build_repositories(as_client(database)).categories.active_keys()
    assert stored == {"startup", "vc", "network", UNKNOWN_CATEGORY_KEY}
