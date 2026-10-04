"""The assessment recording its own step of the run, and making its own results directory.

The promise checked here: with ``--record`` the ``assess`` step ends up exactly
as the recipe used to record it by hand — a success, people assessed as found,
people sent to review as new — and without it the two commands record nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner, Result

from tests.assessment_world import verdict_file, verdict_payload
from tests.conftest import FakeSupabaseClient, printed_lines
from tests.test_assessment_importer import talkative_person
from tracker.cli.main import build_cli
from tracker.domain.enums import RunStatus, RunStep, RunTrigger
from tracker.domain.models import Person, RunLog
from tracker.repositories import Repositories
from tracker.services.assessment.run_step import record_assessment
from tracker.services.runs.run_recorder import RunRecorder, StepOutcome, StepResult
from tracker.shared.clock import FixedClock
from tracker.shared.config import REPOSITORY_ROOT, Settings

#: The codes a terminal reads as "switch to this colour".
_COLOUR_CODES = re.compile(r"\x1b\[[0-9;]*m")

STEP_RECORDED = "step recorded"
NOTHING_TO_ASSESS = "0 people in 0 batch files"

#: A verdict the policy turns into a question for the owner.
UNSURE = {"confidence": 0.3}


@dataclass(frozen=True, slots=True)
class Desk:
    """The ``tracker ai`` commands on an in-memory database and two temporary directories."""

    batches: Path
    results: Path

    def export(self, *options: str) -> Result:
        """Run ``tracker ai export``."""
        return self._run("export", *options)

    def bring_in(self, *options: str) -> Result:
        """Run ``tracker ai import``."""
        return self._run("import", *options)

    def answer(self, *verdicts: dict[str, object]) -> None:
        """Write the assistant's verdicts for the one exported batch."""
        [batch] = self.batches.glob("*.json")
        self.results.joinpath(batch.name).write_text(
            verdict_file(batch.stem, *verdicts), encoding="utf-8"
        )

    def answer_badly(self) -> None:
        """Write something that is not a verdict file for the one exported batch."""
        [batch] = self.batches.glob("*.json")
        self.results.joinpath(batch.name).write_text("not a verdict", encoding="utf-8")

    def _run(self, command: str, *options: str) -> Result:
        directories = ["--batches", str(self.batches), "--results", str(self.results)]
        return CliRunner().invoke(build_cli(), ["ai", command, *directories, *options])


@pytest.fixture
def desk(
    monkeypatch: pytest.MonkeyPatch,
    repositories: Repositories,
    settings: Settings,
    clock: FixedClock,
    tmp_path: Path,
) -> Desk:
    assert settings.supabase_url
    monkeypatch.setattr("tracker.cli.commands.ai._repositories", lambda _settings: repositories)
    monkeypatch.setattr("tracker.cli.commands.ai.SystemClock", lambda _zone: clock)
    return Desk(batches=tmp_path / "batches", results=tmp_path / "results")


@pytest.fixture
def recorder(repositories: Repositories, clock: FixedClock) -> RunRecorder:
    return RunRecorder(repositories, clock)


@pytest.fixture
def run(recorder: RunRecorder) -> RunLog:
    """Today's run, open."""
    return recorder.start(RunTrigger.MANUAL)


def assess_steps(client: FakeSupabaseClient) -> list[dict[str, Any]]:
    """Every ``assess`` step the database holds."""
    rows = client.tables.get("run_step_logs", [])
    return [row for row in rows if row["step"] == RunStep.ASSESS.value]


def counts(client: FakeSupabaseClient) -> tuple[str, int | None, int | None, str | None]:
    """The one ``assess`` step: its status, found, new and error code."""
    [step] = assess_steps(client)
    return step["status"], step["items_found"], step["items_new"], step["error_code"]


def two_people(repositories: Repositories) -> tuple[Person, Person]:
    """Two people with something to judge."""
    return (
        talkative_person(repositories, "Anna Vermeer", source="thread-1"),
        talkative_person(repositories, "Bram Peeters", source="thread-2"),
    )


# --- the results directory --------------------------------------------------------


def test_export_makes_the_results_directory_the_verdicts_go_in(
    desk: Desk, repositories: Repositories
) -> None:
    talkative_person(repositories)

    result = desk.export()

    assert result.exit_code == 0
    assert printed_lines(result)[-1] == "1 people in 1 batch files"
    assert desk.results.is_dir()
    assert list(desk.results.iterdir()) == []


def test_export_with_nothing_to_assess_makes_no_directory(desk: Desk) -> None:
    result = desk.export()

    assert result.exit_code == 0
    assert printed_lines(result) == [NOTHING_TO_ASSESS]
    assert not desk.results.exists()
    assert not desk.batches.exists()


# --- export --record ----------------------------------------------------------------


def test_export_with_record_and_nothing_to_assess_records_a_success_of_nought(
    desk: Desk, run: RunLog, fake_client: FakeSupabaseClient
) -> None:
    result = desk.export("--record")

    assert result.exit_code == 0
    assert printed_lines(result) == [NOTHING_TO_ASSESS, STEP_RECORDED]
    assert counts(fake_client) == (RunStatus.SUCCESS.value, 0, 0, None)
    assert assess_steps(fake_client)[0]["run_id"] == str(run.id)


def test_export_with_record_and_people_to_assess_leaves_the_step_to_the_import(
    desk: Desk, run: RunLog, repositories: Repositories, fake_client: FakeSupabaseClient
) -> None:
    assert run.status is RunStatus.RUNNING
    talkative_person(repositories)

    result = desk.export("--record")

    assert result.exit_code == 0
    assert STEP_RECORDED not in printed_lines(result)
    assert assess_steps(fake_client) == []


# --- import --record ----------------------------------------------------------------


def test_import_with_record_records_what_the_recipe_recorded_by_hand(
    desk: Desk, run: RunLog, repositories: Repositories, fake_client: FakeSupabaseClient
) -> None:
    anna, bram = two_people(repositories)
    by_hand = desk.export()
    desk.answer(verdict_payload(anna.id), verdict_payload(bram.id, **UNSURE))

    result = desk.bring_in("--record")

    assert by_hand.exit_code == 0
    assert result.exit_code == 0
    assert printed_lines(result) == [
        "2 people assessed, 1 sent to review, 0 marked noise, 0 rejected files",
        STEP_RECORDED,
    ]
    assert counts(fake_client) == (RunStatus.SUCCESS.value, 2, 1, None)
    assert assess_steps(fake_client)[0]["run_id"] == str(run.id)


def test_recording_the_import_lists_the_steps_of_the_run_once(
    desk: Desk, run: RunLog, repositories: Repositories, fake_client: FakeSupabaseClient
) -> None:
    """The step is found once, to add to its counts, and written over what was found."""
    assert run.status is RunStatus.RUNNING
    anna, bram = two_people(repositories)
    desk.export("--record")
    desk.answer(verdict_payload(anna.id))
    desk.bring_in("--record")
    desk.export("--record")
    desk.answer(verdict_payload(bram.id))
    fake_client.executed.clear()

    result = desk.bring_in("--record")

    assert printed_lines(result) == [
        "1 people assessed, 0 sent to review, 0 marked noise, 0 rejected files",
        STEP_RECORDED,
    ]
    assert fake_client.executed.count(("run_step_logs", "select")) == 1
    assert counts(fake_client) == (RunStatus.SUCCESS.value, 2, 0, None)


def test_a_second_import_adds_to_what_the_first_one_recorded(
    desk: Desk, run: RunLog, repositories: Repositories, fake_client: FakeSupabaseClient
) -> None:
    assert run.status is RunStatus.RUNNING
    anna = talkative_person(repositories, "Anna Vermeer", source="thread-1")
    desk.export("--record")
    desk.answer(verdict_payload(anna.id, **UNSURE))
    desk.bring_in("--record")
    bram = talkative_person(repositories, "Bram Peeters", source="thread-2")
    desk.export("--record")
    desk.answer(verdict_payload(bram.id))

    result = desk.bring_in("--record")

    assert printed_lines(result)[0].startswith("1 people assessed, 0 sent to review")
    assert counts(fake_client) == (RunStatus.SUCCESS.value, 2, 1, None)


def test_a_rejected_file_answered_again_is_counted_once_it_passes(
    desk: Desk, run: RunLog, repositories: Repositories, fake_client: FakeSupabaseClient
) -> None:
    assert run.status is RunStatus.RUNNING
    anna = talkative_person(repositories)
    desk.export("--record")
    desk.answer_badly()

    refused = desk.bring_in("--record")
    after_refusal = counts(fake_client)
    desk.answer(verdict_payload(anna.id))
    accepted = desk.bring_in("--record")

    assert printed_lines(refused)[-2:] == [
        "0 people assessed, 0 sent to review, 0 marked noise, 1 rejected files",
        STEP_RECORDED,
    ]
    assert after_refusal == (RunStatus.SUCCESS.value, 0, 0, None)
    assert accepted.exit_code == 0
    assert counts(fake_client) == (RunStatus.SUCCESS.value, 1, 0, None)


def test_an_import_or_export_with_nothing_left_never_wipes_the_count(
    desk: Desk, run: RunLog, repositories: Repositories, fake_client: FakeSupabaseClient
) -> None:
    assert run.status is RunStatus.RUNNING
    anna = talkative_person(repositories)
    desk.export("--record")
    desk.answer(verdict_payload(anna.id))
    desk.bring_in("--record")

    again = desk.bring_in("--record")
    exported = desk.export("--record")

    assert printed_lines(again)[0].startswith("0 people assessed")
    assert printed_lines(exported) == [NOTHING_TO_ASSESS, STEP_RECORDED]
    assert counts(fake_client) == (RunStatus.SUCCESS.value, 1, 0, None)


def test_the_step_goes_into_the_run_that_was_named(
    desk: Desk, run: RunLog, recorder: RunRecorder, fake_client: FakeSupabaseClient
) -> None:
    later = recorder.start(RunTrigger.REFRESH)

    result = desk.export("--record", "--run", str(run.id))

    assert later.id != run.id
    assert result.exit_code == 0
    assert [step["run_id"] for step in assess_steps(fake_client)] == [str(run.id)]


def test_a_refresh_records_its_assessment_into_its_own_run(
    desk: Desk,
    run: RunLog,
    recorder: RunRecorder,
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
) -> None:
    """The daily run stays open beside the refresh and keeps its own steps."""
    refresh = recorder.start(RunTrigger.REFRESH)
    anna = talkative_person(repositories)
    desk.export("--record", "--refresh")
    desk.answer(verdict_payload(anna.id))

    result = desk.bring_in("--record", "--refresh")

    assert printed_lines(result)[-1] == STEP_RECORDED
    assert [step["run_id"] for step in assess_steps(fake_client)] == [str(refresh.id)]
    assert run.id != refresh.id


# --- without --record, and with no run to record into ------------------------------


def test_without_record_neither_command_records_a_step(
    desk: Desk, run: RunLog, repositories: Repositories, fake_client: FakeSupabaseClient
) -> None:
    assert run.status is RunStatus.RUNNING
    anna = talkative_person(repositories)

    exported = desk.export()
    desk.answer(verdict_payload(anna.id))
    imported = desk.bring_in()

    assert printed_lines(exported)[-1] == "1 people in 1 batch files"
    assert printed_lines(imported) == [
        "1 people assessed, 0 sent to review, 0 marked noise, 0 rejected files"
    ]
    assert assess_steps(fake_client) == []


def test_with_record_and_no_run_open_nothing_is_exported(
    desk: Desk, repositories: Repositories
) -> None:
    talkative_person(repositories)

    result = desk.export("--record")

    assert result.exit_code != 0
    assert printed_lines(result) == []
    assert not desk.batches.exists()


def test_with_record_and_no_run_open_the_verdicts_are_still_saved(
    desk: Desk, repositories: Repositories, fake_client: FakeSupabaseClient
) -> None:
    anna = talkative_person(repositories)
    desk.export()
    desk.answer(verdict_payload(anna.id))

    result = desk.bring_in("--record")

    assert result.exit_code == 0
    assert printed_lines(result) == [
        "1 people assessed, 0 sent to review, 0 marked noise, 0 rejected files",
        "verdicts saved, step not recorded · there is no daily run to work with — "
        "start one with 'tracker run start' · code=validation_failed",
    ]
    assert repositories.person_states.find_for_person(anna.id) is not None
    assert list(desk.results.glob("*.json")) == []
    assert assess_steps(fake_client) == []


def test_a_run_too_old_to_record_into_still_gets_its_verdicts_saved(
    desk: Desk,
    repositories: Repositories,
    fake_client: FakeSupabaseClient,
    clock: FixedClock,
) -> None:
    """A Mac that slept part-way through: the run counts as abandoned, the verdicts do not."""
    old = RunRecorder(repositories, FixedClock(clock.now() - timedelta(hours=4)))
    old.start(RunTrigger.MAC)
    anna = talkative_person(repositories)
    desk.export()
    desk.answer(verdict_payload(anna.id))

    result = desk.bring_in("--record")

    assert result.exit_code == 0
    last = printed_lines(result)[-1]
    assert last.startswith("verdicts saved, step not recorded · no run is open")
    assert last.endswith("code=validation_failed")
    assert repositories.person_states.find_for_person(anna.id) is not None
    assert assess_steps(fake_client) == []


@pytest.mark.parametrize("command", ["export", "import"])
def test_the_help_offers_to_record_the_step(command: str) -> None:
    result = CliRunner().invoke(build_cli(), ["ai", command, "--help"])

    assert result.exit_code == 0
    # On GitHub Actions the help is printed in colour, and the colour codes sit
    # between the two dashes and the option's name.
    assert "--record" in _COLOUR_CODES.sub("", result.output)


@pytest.mark.parametrize("command", ["export", "import", "status"])
def test_the_help_names_the_default_folders_from_the_project(command: str) -> None:
    result = CliRunner().invoke(build_cli(), ["ai", command, "--help"])

    output = _COLOUR_CODES.sub("", result.output)
    assert "work/batches" in output
    assert "work/results" in output
    assert str(REPOSITORY_ROOT) not in output


# --- the service --------------------------------------------------------------------


def test_recording_an_assessment_after_a_failure_recorded_by_hand_makes_it_a_success(
    recorder: RunRecorder, run: RunLog, fake_client: FakeSupabaseClient
) -> None:
    recorder.record_step(
        run.id,
        StepOutcome(step=RunStep.ASSESS, result=StepResult.FAILED, error_code="validation_failed"),
    )

    record_assessment(recorder, run.id, assessed=3, sent_to_review=1)

    assert counts(fake_client) == (RunStatus.SUCCESS.value, 3, 1, None)


def test_an_assessment_is_counted_per_run(
    recorder: RunRecorder, run: RunLog, fake_client: FakeSupabaseClient
) -> None:
    record_assessment(recorder, run.id, assessed=3, sent_to_review=1)
    later = recorder.start(RunTrigger.REFRESH)

    record_assessment(recorder, later.id, assessed=2, sent_to_review=0)

    found = {step["run_id"]: step["items_found"] for step in assess_steps(fake_client)}
    assert found == {str(run.id): 3, str(later.id): 2}
