"""The contract between Python and the Claude Code assistant.

Two file shapes travel between them, and both are strict:

* a **batch** — what Python asks about: a few people, each with the threads that
  matter and everything already known about them;
* a **verdict file** — what the assistant answers: one verdict per person.

Every model forbids unknown fields, every text field has a length limit and
every closed set of values is taken from :mod:`tracker.domain.enums`. A
person's category is checked for its shape here and against the owner's list
of categories in :mod:`tracker.services.assessment.validation`. Message
text inside a batch is *material to judge*, never an instruction: nothing in
this module, and nothing downstream of it, acts on what a message says.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tracker.domain.categories import CategoryKey
from tracker.domain.enums import (
    Channel,
    ContactStatus,
    Direction,
    Relevance,
    Signal,
    WaitingOn,
)
from tracker.shared.constants.assessment import (
    MAX_NAME_LENGTH,
    MAX_NEXT_ACTION_LENGTH,
    MAX_SUMMARY_LENGTH,
    MAX_VERDICTS_PER_FILE,
)
from tracker.shared.errors import ValidationFailedError

#: Shape a batch identifier must have. It also becomes a file name, so anything
#: that could escape the working directory is refused here.
BATCH_ID_PATTERN: Final[str] = r"^[a-z0-9][a-z0-9-]{3,63}$"

_STRICT: Final[ConfigDict] = ConfigDict(extra="forbid", frozen=True)


class DossierMessage(BaseModel):
    """One message, as the assistant sees it."""

    model_config = _STRICT

    sent_at: datetime
    direction: Direction
    text: str | None = None


class DossierThread(BaseModel):
    """One thread on one channel, with the evidence the rules already gathered.

    A calendar thread also says when the meeting starts.
    """

    model_config = _STRICT

    conversation_id: UUID
    channel: Channel
    subject: str | None = None
    relevance: Relevance
    owner_has_replied: bool
    exchange_count: int = Field(ge=0)
    meeting_at: datetime | None = None
    messages: tuple[DossierMessage, ...] = ()


class DossierAssessment(BaseModel):
    """What the last assessment concluded about a person."""

    model_config = _STRICT

    status: ContactStatus
    waiting_on: WaitingOn
    next_action: str | None = None
    due_date: date | None = None
    summary: str | None = None
    signal: Signal
    confidence: Decimal = Field(ge=Decimal(0), le=Decimal(1))
    assessed_at: datetime


class DossierOverride(BaseModel):
    """What the owner corrected by hand. These values are facts, not guesses."""

    model_config = _STRICT

    status: ContactStatus | None = None
    waiting_on: WaitingOn | None = None
    next_action: str | None = None
    due_date: date | None = None
    person_type: CategoryKey | None = None
    note: str | None = None


class PersonDossier(BaseModel):
    """Everything the assistant is given about one person.

    ``newest_message_at`` is the newest message the dossier covers. The import
    stamps the person as assessed up to this moment, not up to whatever the
    database holds by then, so a message stored while the assistant was working
    is still judged next time. A batch written before this field existed omits
    it; the import then falls back to the batch's own ``generated_at``.
    """

    model_config = _STRICT

    person_id: UUID
    full_name: str
    newest_message_at: datetime | None = None
    known_person_type: CategoryKey
    known_role_title: str | None = None
    known_organisation_name: str | None = None
    owner_answers: tuple[str, ...] = ()
    owner_override: DossierOverride | None = None
    previous_assessment: DossierAssessment | None = None
    threads: tuple[DossierThread, ...] = ()


class AssessmentBatch(BaseModel):
    """One batch file: the people the assistant is asked to judge in one go."""

    model_config = _STRICT

    batch_id: str = Field(pattern=BATCH_ID_PATTERN)
    generated_at: datetime
    people: tuple[PersonDossier, ...]


class PersonVerdict(BaseModel):
    """The assistant's answer about one person."""

    model_config = _STRICT

    person_id: UUID
    relevance: Relevance
    person_type: CategoryKey
    organisation_name: str | None = Field(default=None, max_length=MAX_NAME_LENGTH)
    role_title: str | None = Field(default=None, max_length=MAX_NAME_LENGTH)
    status: ContactStatus
    waiting_on: WaitingOn
    next_action: str | None = Field(default=None, max_length=MAX_NEXT_ACTION_LENGTH)
    due_date: date | None = None
    summary: str | None = Field(default=None, max_length=MAX_SUMMARY_LENGTH)
    signal: Signal
    confidence: Decimal = Field(ge=Decimal(0), le=Decimal(1))


class VerdictFile(BaseModel):
    """One result file: the verdicts for exactly one batch."""

    model_config = _STRICT

    batch_id: str = Field(pattern=BATCH_ID_PATTERN)
    verdicts: tuple[PersonVerdict, ...] = Field(max_length=MAX_VERDICTS_PER_FILE)


def parse_batch(raw: str) -> AssessmentBatch:
    """Read a batch file's text into a validated batch.

    Args:
        raw: The file's contents.

    Returns:
        The validated batch.

    Raises:
        ValidationFailedError: If the text is not JSON or not a batch.
    """
    return _parse(AssessmentBatch, raw, "batch file")


def parse_verdict_file(raw: str) -> VerdictFile:
    """Read a result file's text into validated verdicts.

    Args:
        raw: The file's contents.

    Returns:
        The validated verdict file.

    Raises:
        ValidationFailedError: If the text is not JSON or not a verdict file.
            The message names the offending fields, never their values, because
            those values come from message text Threadline does not trust.
    """
    return _parse(VerdictFile, raw, "verdict file")


def _parse[ModelT: BaseModel](model: type[ModelT], raw: str, what: str) -> ModelT:
    """Validate raw JSON text into one strict model.

    Args:
        model: The model to validate against.
        raw: The file's contents.
        what: How the file is named in the error message.

    Returns:
        The validated model.

    Raises:
        ValidationFailedError: If the text is not JSON or does not match.
    """
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        message = f"{what} is not valid JSON"
        raise ValidationFailedError(message) from error
    try:
        return model.model_validate(payload)
    except ValidationError as error:
        message = f"{what} does not match the agreed shape: {describe_fields(error)}"
        raise ValidationFailedError(message) from error


def describe_fields(error: ValidationError) -> str:
    """Name the fields a validation failure complained about.

    The values themselves are left out on purpose: they may come from message
    text, which is never echoed into a log line or an operator message.

    Args:
        error: The failure Pydantic raised.

    Returns:
        A comma-separated list of ``field (reason)`` pairs, alphabetically.
    """
    problems = sorted(
        f"{'.'.join(str(part) for part in item['loc']) or '(root)'} ({item['type']})"
        for item in error.errors()
    )
    return ", ".join(problems)
