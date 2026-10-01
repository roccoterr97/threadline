"""The gate a verdict file has to pass before anything reaches the database.

The shape is checked by the models in :mod:`tracker.schemas.assessment`. What is
left is what only the surrounding facts can answer: does this file belong to
this batch, does it talk about people the batch actually asked about, is each
person answered once, is each category one of the owner's, and is the due date
a date a human could have meant.

The owner's categories are read from the database by the caller. They never
travel inside the batch file: the helper treats that file as untrusted
material, and a list it could see there is a list a message could imitate.

A file that fails any of these is rejected whole. Nothing in it is applied, so a
verdict written to mislead — for example one produced by a message demanding
that "everyone" be closed — cannot take part of the file through.
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from tracker.schemas.assessment import AssessmentBatch, PersonVerdict, VerdictFile
from tracker.shared.constants.assessment import (
    DUE_DATE_FUTURE_LIMIT_DAYS,
    DUE_DATE_PAST_LIMIT_DAYS,
)
from tracker.shared.errors import ValidationFailedError


def validate_against_batch(
    verdict_file: VerdictFile,
    batch: AssessmentBatch,
    today: date,
    category_keys: frozenset[str],
) -> tuple[PersonVerdict, ...]:
    """Check a verdict file against the batch it answers.

    Args:
        verdict_file: The verdicts the assistant wrote.
        batch: The batch those verdicts should answer.
        today: The current date, against which due dates are judged.
        category_keys: The keys of the owner's categories still in use; a
            verdict may name only one of these.

    Returns:
        The verdicts, in the order the batch listed the people.

    Raises:
        ValidationFailedError: If the file answers another batch, names someone
            the batch did not ask about, answers a person twice, names a
            category the owner does not have, or carries a due date outside
            the sane range.
    """
    if verdict_file.batch_id != batch.batch_id:
        message = f"verdict file answers batch '{verdict_file.batch_id}', not '{batch.batch_id}'"
        raise ValidationFailedError(message)
    expected = [person.person_id for person in batch.people]
    by_person = _one_verdict_per_person(verdict_file, set(expected))
    for verdict in by_person.values():
        _check_category(verdict, category_keys)
        _check_due_date(verdict, today)
    return tuple(by_person[person_id] for person_id in expected if person_id in by_person)


def _one_verdict_per_person(
    verdict_file: VerdictFile,
    expected: set[UUID],
) -> dict[UUID, PersonVerdict]:
    """Index the verdicts by person, refusing strangers and duplicates.

    Raises:
        ValidationFailedError: If a person is unknown to the batch or answered
            more than once.
    """
    by_person: dict[UUID, PersonVerdict] = {}
    for verdict in verdict_file.verdicts:
        if verdict.person_id not in expected:
            message = f"verdict names person {verdict.person_id}, who is not in the batch"
            raise ValidationFailedError(message)
        if verdict.person_id in by_person:
            message = f"verdict file answers person {verdict.person_id} twice"
            raise ValidationFailedError(message)
        by_person[verdict.person_id] = verdict
    return by_person


def _check_category(verdict: PersonVerdict, category_keys: frozenset[str]) -> None:
    """Refuse a category the owner has not defined.

    The key itself is left out of the message: it was written by the helper,
    possibly under the influence of message text.

    Raises:
        ValidationFailedError: If the verdict's category is not one of the keys.
    """
    if verdict.person_type in category_keys:
        return
    message = f"person_type for person {verdict.person_id} is not one of the owner's categories"
    raise ValidationFailedError(message)


def _check_due_date(verdict: PersonVerdict, today: date) -> None:
    """Refuse a due date no human could have meant.

    Raises:
        ValidationFailedError: If the date sits outside the accepted window.
    """
    if verdict.due_date is None:
        return
    earliest = today - timedelta(days=DUE_DATE_PAST_LIMIT_DAYS)
    latest = today + timedelta(days=DUE_DATE_FUTURE_LIMIT_DAYS)
    if earliest <= verdict.due_date <= latest:
        return
    message = (
        f"due date for person {verdict.person_id} is outside {earliest.isoformat()}"
        f"–{latest.isoformat()}"
    )
    raise ValidationFailedError(message)
