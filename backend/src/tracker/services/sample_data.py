"""Load and clear the made-up sample data.

The sample set lets the dashboard, the assessment and the morning e-mail be
built and demonstrated before any real message has been collected. Every record
carries a fixed identifier, so loading it twice changes nothing and clearing it
removes exactly what it added — no real data is ever touched.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, ValidationError

from tracker.domain.models import (
    Conversation,
    Message,
    Organisation,
    Person,
    PersonIdentity,
    PersonOverride,
    PersonState,
    Record,
    ReviewItem,
    RunLog,
    RunStepLog,
)
from tracker.repositories import Repositories
from tracker.shared.errors import ValidationFailedError
from tracker.shared.logging import get_logger

#: Default location of the sample set inside the repository.
SAMPLE_DATA_FILE: Final[Path] = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "sample_data.json"
)

_log = get_logger(__name__)


class SampleDataSet(BaseModel):
    """Every record of the sample set, already validated."""

    model_config = ConfigDict(extra="forbid")

    organisations: tuple[Organisation, ...] = ()
    people: tuple[Person, ...] = ()
    person_identities: tuple[PersonIdentity, ...] = ()
    conversations: tuple[Conversation, ...] = ()
    messages: tuple[Message, ...] = ()
    person_states: tuple[PersonState, ...] = ()
    person_overrides: tuple[PersonOverride, ...] = ()
    review_items: tuple[ReviewItem, ...] = ()
    run_logs: tuple[RunLog, ...] = ()
    run_step_logs: tuple[RunStepLog, ...] = ()


@dataclass(frozen=True, slots=True)
class TableCount:
    """How many rows one table gained or lost."""

    table: str
    rows: int


class WritableRepository(Protocol):
    """The part of a repository the sample loader uses."""

    def bulk_upsert(self, records: Sequence[Any]) -> list[Any]:
        """Write records, replacing any row with the same natural key."""
        ...

    def delete_by_ids(self, record_ids: Sequence[UUID]) -> int:
        """Delete records by primary key."""
        ...


@dataclass(frozen=True, slots=True)
class _TableLoad:
    """One table's share of the sample set."""

    name: str
    repository: WritableRepository
    records: Sequence[Record]


def read_sample_data(path: Path = SAMPLE_DATA_FILE) -> SampleDataSet:
    """Read and validate the sample set from disk.

    Args:
        path: Where the JSON file lives.

    Returns:
        The validated sample set.

    Raises:
        ValidationFailedError: If the file is missing, is not JSON, or does not
            match the database contract.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as error:
        message = f"sample data file could not be read: {path}"
        raise ValidationFailedError(message) from error
    try:
        return SampleDataSet.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError) as error:
        message = f"sample data file is not a valid sample set: {path}"
        raise ValidationFailedError(message) from error


class SampleDataService:
    """Writes the sample set into the database and takes it out again."""

    def __init__(self, repositories: Repositories) -> None:
        """Bind the service to the repositories it writes through.

        Args:
            repositories: The repository container.
        """
        self._repositories = repositories

    def load(self, dataset: SampleDataSet) -> tuple[TableCount, ...]:
        """Write every record, parents before children.

        Writes are upserts on fixed identifiers, so running this twice leaves
        the same rows behind.

        Args:
            dataset: The sample set to write.

        Returns:
            How many rows each table received, in write order.
        """
        written = tuple(
            TableCount(table.name, len(table.repository.bulk_upsert(table.records)))
            for table in self._plan(dataset)
        )
        _log.info("sample_data_loaded", rows=sum(count.rows for count in written))
        return written

    def clear(self, dataset: SampleDataSet) -> tuple[TableCount, ...]:
        """Delete every record of the sample set, children before parents.

        Args:
            dataset: The sample set whose identifiers are removed.

        Returns:
            How many rows each table lost, in delete order.
        """
        removed = tuple(
            TableCount(
                table.name,
                table.repository.delete_by_ids([record.id for record in table.records]),
            )
            for table in reversed(self._plan(dataset))
        )
        _log.info("sample_data_cleared", rows=sum(count.rows for count in removed))
        return removed

    def _plan(self, dataset: SampleDataSet) -> tuple[_TableLoad, ...]:
        """List the tables in the order foreign keys require them to be written."""
        repositories = self._repositories
        return (
            _TableLoad("organisations", repositories.organisations, dataset.organisations),
            _TableLoad("people", repositories.people, dataset.people),
            _TableLoad(
                "person_identities", repositories.person_identities, dataset.person_identities
            ),
            _TableLoad("conversations", repositories.conversations, dataset.conversations),
            _TableLoad("messages", repositories.messages, dataset.messages),
            _TableLoad("person_states", repositories.person_states, dataset.person_states),
            _TableLoad("person_overrides", repositories.person_overrides, dataset.person_overrides),
            _TableLoad("review_items", repositories.review_items, dataset.review_items),
            _TableLoad("run_logs", repositories.run_logs, dataset.run_logs),
            _TableLoad("run_step_logs", repositories.run_step_logs, dataset.run_step_logs),
        )
