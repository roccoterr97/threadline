"""Check what the assistant wrote, then save it.

Nothing from a verdict file is trusted. Each file is parsed against a strict
model, checked against the batch it claims to answer, and only then applied —
and it is applied whole or not at all. A file that fails any check is logged,
counted as rejected, and left on disk with its batch; every person it mentions
keeps the state they already had. A file that was applied is removed together
with its batch, so message text never outlives its use.

Two further rules are enforced here rather than by the assistant:

* what the owner corrected by hand is written back over the assessment, so even
  a direct read of ``person_states`` shows his value;
* a person judged not relevant to what the owner tracks loses their stored message
  text and thread subjects in the same pass.
"""

from __future__ import annotations

from calendar import Day
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from tracker.domain.assessment_policy import (
    AssessedState,
    ContactTiming,
    OwnerCalendar,
    OwnerCorrections,
    VerdictValues,
    decide,
)
from tracker.domain.categories import UNKNOWN_CATEGORY_KEY
from tracker.domain.enums import Relevance, RelevanceDecidedBy, ReviewAnswer, ReviewKind
from tracker.domain.models import (
    Conversation,
    Message,
    Organisation,
    Person,
    PersonOverride,
    PersonState,
    ReviewItem,
)
from tracker.domain.profile import Wording
from tracker.repositories import CategoryRepository, OrganisationRepository, Repositories
from tracker.schemas.assessment import PersonVerdict, parse_batch, parse_verdict_file
from tracker.services.assessment.validation import validate_against_batch
from tracker.services.assessment.work_files import remove_work_file
from tracker.shared.clock import Clock
from tracker.shared.constants.assessment import BATCH_DIRECTORY, RESULT_DIRECTORY
from tracker.shared.errors import ValidationFailedError
from tracker.shared.logging import get_logger

#: Suffix of the files the assistant leaves behind.
RESULT_SUFFIX = "*.json"

_log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RejectedFile:
    """A result file that was refused, and why."""

    path: Path
    reason: str


@dataclass(frozen=True, slots=True)
class ImportResult:
    """What one import run changed."""

    assessed: int = 0
    sent_to_review: int = 0
    marked_noise: int = 0
    rejected: tuple[RejectedFile, ...] = ()

    def merged_with(self, other: ImportResult) -> ImportResult:
        """Add another file's outcome to this one.

        Args:
            other: The outcome to add.

        Returns:
            The combined outcome.
        """
        return ImportResult(
            assessed=self.assessed + other.assessed,
            sent_to_review=self.sent_to_review + other.sent_to_review,
            marked_noise=self.marked_noise + other.marked_noise,
            rejected=self.rejected + other.rejected,
        )


@dataclass(slots=True)
class _Writes:
    """Everything one file's verdicts change, collected before anything is sent."""

    people: list[Person] = field(default_factory=list)
    organisations: list[Organisation] = field(default_factory=list)
    states: list[PersonState] = field(default_factory=list)
    conversations: list[Conversation] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)
    review_items: list[ReviewItem] = field(default_factory=list)


class _AllowedCategories:
    """The category keys a verdict may use, read when the first file needs them.

    One import checks every file against the same categories, so they are read
    once for all of them. A run whose files all fail before that check never
    reads them at all.
    """

    def __init__(self, repository: CategoryRepository) -> None:
        """Bind to the categories table; nothing is read yet."""
        self._repository = repository
        self._keys: frozenset[str] | None = None

    def keys(self) -> frozenset[str]:
        """Return the active category keys, plus the one for "not known"."""
        if self._keys is None:
            self._keys = self._repository.active_keys() | {UNKNOWN_CATEGORY_KEY}
        return self._keys


class _StoredOrganisations:
    """The organisations already stored under the names one file mentions.

    Every name in the file is looked up together, the first time one of them
    is needed: a file whose verdicts are all noise names organisations nobody
    will be linked to, and asks nothing.
    """

    def __init__(self, repository: OrganisationRepository, names: Sequence[str]) -> None:
        """Bind to the organisations table and to one file's names; nothing is read yet."""
        self._repository = repository
        self._names = names
        self._by_name: dict[str, Organisation] | None = None

    def named(self, name: str) -> Organisation | None:
        """Return the organisation stored under a name, or ``None`` when there is none."""
        if self._by_name is None:
            self._by_name = self._repository.find_by_names(self._names)
        return self._by_name.get(name)


@dataclass(frozen=True, slots=True)
class _Known:
    """What the database already holds about the people in one file."""

    people: dict[UUID, Person]
    conversations: dict[UUID, list[Conversation]]
    states: dict[UUID, PersonState]
    overrides: dict[UUID, PersonOverride]
    review_items: dict[UUID, list[ReviewItem]]
    organisations: _StoredOrganisations


class AssessmentImporter:
    """Validates verdict files and applies the ones that pass."""

    def __init__(
        self,
        repositories: Repositories,
        clock: Clock,
        weekend: frozenset[Day],
        batch_directory: Path = BATCH_DIRECTORY,
        result_directory: Path = RESULT_DIRECTORY,
        *,
        wording: Wording,
    ) -> None:
        """Bind the importer to its dependencies.

        Args:
            repositories: The repository container.
            clock: The clock that stamps the assessment; its zone decides
                what today is.
            weekend: The owner's days off, skipped when a follow-up date is
                worked out.
            batch_directory: Where the batches this answers were written.
            result_directory: Where the assistant left its verdict files.
            wording: The owner's profile wording; it words the question asked
                about a person the assistant was unsure about.
        """
        self._repositories = repositories
        self._clock = clock
        self._calendar = OwnerCalendar(zone=clock.zone, weekend=weekend)
        self._batch_directory = batch_directory
        self._result_directory = result_directory
        self._wording = wording

    def result_files(self) -> tuple[Path, ...]:
        """List the verdict files waiting to be imported.

        Returns:
            The files, in name order.
        """
        if not self._result_directory.is_dir():
            return ()
        return tuple(sorted(self._result_directory.glob(RESULT_SUFFIX)))

    def import_all(self) -> ImportResult:
        """Import every verdict file, skipping the ones that do not pass.

        Returns:
            The combined outcome, with one entry per rejected file.
        """
        outcome = ImportResult()
        categories = self._allowed_categories()
        for path in self.result_files():
            outcome = outcome.merged_with(self._import_one(path, categories))
        _log.info(
            "assessment_imported",
            assessed=outcome.assessed,
            sent_to_review=outcome.sent_to_review,
            marked_noise=outcome.marked_noise,
            rejected=len(outcome.rejected),
        )
        return outcome

    def import_file(self, path: Path) -> ImportResult:
        """Import one verdict file.

        Args:
            path: The file to import.

        Returns:
            What the file changed.

        Raises:
            ValidationFailedError: If the file does not pass every check. The
                database is left untouched.
        """
        verdicts, _ = self._validated(path, self._allowed_categories())
        return self._apply(verdicts)

    def _allowed_categories(self) -> _AllowedCategories:
        """The categories every file of one import is checked against."""
        return _AllowedCategories(self._repositories.categories)

    def _import_one(self, path: Path, categories: _AllowedCategories) -> ImportResult:
        """Import one file, turning a refusal into a counted rejection."""
        try:
            verdicts, batch_path = self._validated(path, categories)
            outcome = self._apply(verdicts)
        except ValidationFailedError as error:
            _log.warning("verdict_file_rejected", file=path.name, reason=error.message)
            return ImportResult(rejected=(RejectedFile(path=path, reason=error.message),))
        _discard(path, batch_path)
        return outcome

    def _validated(
        self, path: Path, categories: _AllowedCategories
    ) -> tuple[tuple[PersonVerdict, ...], Path]:
        """Parse a result file and check it against the batch it answers.

        Args:
            path: The result file.
            categories: The categories a verdict may use.

        Returns:
            The verdicts that passed, and the batch file they answer.

        Raises:
            ValidationFailedError: If the file cannot be read, does not match
                the agreed shape, or does not answer a batch on disk.
        """
        verdict_file = parse_verdict_file(_read(path))
        batch_path = self._batch_directory / f"{verdict_file.batch_id}.json"
        if not batch_path.is_file():
            message = f"no batch named '{verdict_file.batch_id}' was exported"
            raise ValidationFailedError(message)
        batch = parse_batch(_read(batch_path))
        verdicts = validate_against_batch(
            verdict_file, batch, self._clock.today(), categories.keys()
        )
        return verdicts, batch_path

    def _apply(self, verdicts: Sequence[PersonVerdict]) -> ImportResult:
        """Write one validated file's verdicts, all tables at once."""
        if not verdicts:
            return ImportResult()
        known = self._read_known(verdicts)
        writes = _Writes()
        outcome = ImportResult()
        for verdict in verdicts:
            outcome = outcome.merged_with(self._plan_person(verdict, known, writes))
        self._plan_purge(writes)
        self._flush(writes)
        return outcome

    def _plan_purge(self, writes: _Writes) -> None:
        """Forget the text of every thread this file judged to be noise.

        A thread that is not part of the job search keeps only its identifier,
        its dates and the decision, so it is never processed twice and nothing
        private stays behind.
        """
        noise_ids = [thread.id for thread in writes.conversations]
        if not noise_ids:
            return
        stored = self._repositories.messages.list_for_conversations(noise_ids)
        writes.messages.extend(
            message.model_copy(update={"body": None})
            for message in stored
            if message.body is not None
        )

    def _read_known(self, verdicts: Sequence[PersonVerdict]) -> _Known:
        """Read everything the database already holds about one file's people.

        Raises:
            ValidationFailedError: If a person named by the batch no longer
                exists; the whole file is then refused.
        """
        repositories = self._repositories
        person_ids = [verdict.person_id for verdict in verdicts]
        people = {person.id: person for person in repositories.people.list_by_ids(person_ids)}
        missing = [str(person_id) for person_id in person_ids if person_id not in people]
        if missing:
            message = f"verdict file names {len(missing)} person(s) no longer in the database"
            raise ValidationFailedError(message)
        conversations: dict[UUID, list[Conversation]] = defaultdict(list)
        for conversation in repositories.conversations.list_for_people(person_ids):
            if conversation.person_id is not None:
                conversations[conversation.person_id].append(conversation)
        review_items: dict[UUID, list[ReviewItem]] = defaultdict(list)
        for item in repositories.review_items.list_for_people(person_ids):
            if item.person_id is not None:
                review_items[item.person_id].append(item)
        return _Known(
            people=people,
            conversations=conversations,
            states={
                state.person_id: state
                for state in repositories.person_states.list_for_people(person_ids)
            },
            overrides={
                override.person_id: override
                for override in repositories.person_overrides.list_for_people(person_ids)
            },
            review_items=review_items,
            organisations=_StoredOrganisations(
                repositories.organisations,
                [verdict.organisation_name or "" for verdict in verdicts],
            ),
        )

    def _plan_person(
        self,
        verdict: PersonVerdict,
        known: _Known,
        writes: _Writes,
    ) -> ImportResult:
        """Work out every row one verdict changes, and add it to ``writes``.

        A person the owner ruled out after the batch was exported is left as
        he left them: the verdict was written without knowing his answer.
        """
        if _owner_declined(verdict.person_id, known):
            return ImportResult()
        person = known.people[verdict.person_id]
        threads = known.conversations.get(verdict.person_id, [])
        kept_by_owner = _owner_took_a_position(verdict.person_id, known)
        state = decide(
            _values(verdict),
            _timing(threads),
            _corrections(known.overrides.get(verdict.person_id)),
            self._clock.now(),
            self._calendar,
            kept_by_owner=kept_by_owner,
        )
        if state.is_noise and not kept_by_owner:
            _plan_noise(person, threads, writes)
            return ImportResult(marked_noise=1)
        writes.people.append(self._updated_person(person, verdict, state, known, writes))
        writes.states.append(self._state_row(person, state, threads, known))
        asked = _plan_review_item(person, state, known, writes, self._wording)
        return ImportResult(assessed=1, sent_to_review=int(asked))

    def _updated_person(
        self,
        person: Person,
        verdict: PersonVerdict,
        state: AssessedState,
        known: _Known,
        writes: _Writes,
    ) -> Person:
        """Apply the verdict to the person row, creating the organisation if needed."""
        # A "yes" from the owner settles relevance for good, whatever a later
        # verdict scores. Without this the person would quietly leave the
        # dashboard and no new question would be asked, because one already was.
        # A noise verdict against the owner's own judgement is only a doubt:
        # the person stays on the dashboard while the owner is asked.
        if _owner_confirmed_relevant(verdict.person_id, known) or state.is_noise:
            relevance = Relevance.RELEVANT
        else:
            relevance = Relevance.UNSURE if state.needs_review else Relevance.RELEVANT
        return person.model_copy(
            update={
                "person_type": state.person_type,
                "role_title": verdict.role_title or person.role_title,
                "organisation_id": _organisation_id(person, verdict, known, writes),
                "relevance": relevance,
            }
        )

    def _state_row(
        self,
        person: Person,
        state: AssessedState,
        threads: Sequence[Conversation],
        known: _Known,
    ) -> PersonState:
        """Build the ``person_states`` row, reusing the existing row's identifier."""
        previous = known.states.get(person.id)
        now = self._clock.now()
        return PersonState(
            id=previous.id if previous else uuid4(),
            person_id=person.id,
            status=state.status,
            waiting_on=state.waiting_on,
            next_action=state.next_action,
            due_date=state.due_date,
            summary=state.summary,
            signal=state.signal,
            confidence=state.confidence,
            assessed_at=now,
            assessed_through=_latest(thread.last_message_at for thread in threads) or now,
        )

    def _flush(self, writes: _Writes) -> None:
        """Send every planned row, parents before children."""
        repositories = self._repositories
        repositories.organisations.bulk_upsert(writes.organisations)
        repositories.people.bulk_upsert(writes.people)
        repositories.conversations.bulk_upsert(writes.conversations)
        repositories.messages.bulk_upsert(writes.messages)
        repositories.person_states.bulk_upsert(writes.states)
        repositories.review_items.bulk_upsert(writes.review_items)


def _discard(verdict_path: Path, batch_path: Path) -> None:
    """Remove a verdict file and the batch it answered once they have been applied.

    A verdict is a snapshot of one moment. Applying it again later stamps the
    person as assessed up to *today's* newest message, which makes them
    permanently ineligible for re-assessment: their status would freeze while
    the real conversation moved on. The verdict file therefore goes first. The
    batch goes with it because it holds message text that has no further use.
    Rejected files stay where they are, for the assistant to answer again.

    Args:
        verdict_path: The verdict file that was just applied.
        batch_path: The batch file it answered.

    Raises:
        WorkFileError: If either file could not be removed.
    """
    remove_work_file(verdict_path)
    remove_work_file(batch_path)


def _organisation_id(
    person: Person,
    verdict: PersonVerdict,
    known: _Known,
    writes: _Writes,
) -> UUID | None:
    """Find or create the organisation the verdict named."""
    name = (verdict.organisation_name or "").strip()
    if not name:
        return person.organisation_id
    planned = next((row for row in writes.organisations if row.name == name), None)
    if planned is not None:
        return planned.id
    existing = known.organisations.named(name)
    if existing is not None:
        return existing.id
    created = Organisation(name=name)
    writes.organisations.append(created)
    return created.id


def _owner_declined(person_id: UUID, known: _Known) -> bool:
    """Whether the owner has answered "no" to a relevance question about them.

    Any "no" counts, as it does when the exporter picks who to send: a person
    ruled out there must not be brought back here.

    Args:
        person_id: The person to check.
        known: What the database already holds.

    Returns:
        True when the owner has ruled this person out.
    """
    return any(
        item.kind is ReviewKind.RELEVANCE and item.answer is ReviewAnswer.NO
        for item in known.review_items.get(person_id, [])
    )


def _owner_confirmed_relevant(person_id: UUID, known: _Known) -> bool:
    """Whether the owner has answered "yes" to a relevance question about them.

    Args:
        person_id: The person to check.
        known: What the database already holds.

    Returns:
        True when the owner has settled that this person belongs in the search.
    """
    return any(
        item.kind is ReviewKind.RELEVANCE and item.answer is ReviewAnswer.YES
        for item in known.review_items.get(person_id, [])
    )


def _owner_took_a_position(person_id: UUID, known: _Known) -> bool:
    """Whether the owner has already judged this person themselves.

    A correction by hand, or a "yes" in the review list, means the owner has
    looked at this person and taken a view. A later noise verdict must not
    silently undo that, nor erase the message text behind it, so the person is
    kept and the disagreement is put to the owner instead.

    Args:
        person_id: The person to check.
        known: What the database already holds.

    Returns:
        True when the owner's own judgement is on record.
    """
    return person_id in known.overrides or _owner_confirmed_relevant(person_id, known)


def _plan_noise(person: Person, threads: Sequence[Conversation], writes: _Writes) -> None:
    """Mark a person and their threads as noise. The text goes in the purge pass."""
    writes.people.append(person.model_copy(update={"relevance": Relevance.NOISE}))
    writes.conversations.extend(
        thread.model_copy(
            update={
                "relevance": Relevance.NOISE,
                "relevance_decided_by": RelevanceDecidedBy.AI,
                "subject": None,
            }
        )
        for thread in threads
    )


def _plan_review_item(
    person: Person,
    state: AssessedState,
    known: _Known,
    writes: _Writes,
    wording: Wording,
) -> bool:
    """Ask the owner about a person the assistant was not sure about.

    Returns:
        True when a new question was added; False when none was needed or one
        had already been asked.
    """
    if not state.needs_review:
        return False
    asked = any(
        item.kind is ReviewKind.RELEVANCE for item in known.review_items.get(person.id, [])
    )
    if asked:
        return False
    writes.review_items.append(
        ReviewItem(
            kind=ReviewKind.RELEVANCE,
            person_id=person.id,
            question=wording.question_about(person.full_name),
        )
    )
    return True


def _values(verdict: PersonVerdict) -> VerdictValues:
    """Copy a verdict into the plain shape the policy works with."""
    return VerdictValues(
        relevance=verdict.relevance,
        person_type=verdict.person_type,
        status=verdict.status,
        waiting_on=verdict.waiting_on,
        signal=verdict.signal,
        confidence=verdict.confidence,
        next_action=verdict.next_action,
        due_date=verdict.due_date,
        summary=verdict.summary,
        organisation_name=verdict.organisation_name,
        role_title=verdict.role_title,
    )


def _timing(threads: Iterable[Conversation]) -> ContactTiming:
    """Collapse a person's threads into when each side last wrote."""
    live = [thread for thread in threads if thread.relevance is not Relevance.NOISE]
    return ContactTiming(
        last_message_at=_latest(thread.last_message_at for thread in live),
        last_inbound_at=_latest(thread.last_inbound_at for thread in live),
        last_outbound_at=_latest(thread.last_outbound_at for thread in live),
    )


def _corrections(override: PersonOverride | None) -> OwnerCorrections:
    """Copy an override into the plain shape the policy works with."""
    if override is None:
        return OwnerCorrections()
    return OwnerCorrections(
        status=override.status,
        waiting_on=override.waiting_on,
        next_action=override.next_action,
        due_date=override.due_date,
        person_type=override.person_type,
    )


def _latest(moments: Iterable[datetime | None]) -> datetime | None:
    """Return the most recent moment, or ``None`` when there is none."""
    known = [moment for moment in moments if moment is not None]
    return max(known) if known else None


def _read(path: Path) -> str:
    """Read a file the assistant or the exporter wrote.

    Raises:
        ValidationFailedError: If the file cannot be read.
    """
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        message = f"file could not be read: {path.name}"
        raise ValidationFailedError(message) from error
