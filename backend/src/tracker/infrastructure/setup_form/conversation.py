"""What the page and the wizard share: the lines said, the open question, the answer.

The wizard runs in the main thread and blocks on :meth:`Conversation.ask`;
the web server answers the page from other threads. Everything they share
sits behind one lock, and the answer travels through a queue.
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from tracker.shared.constants.setup import FORM_IDLE_LIMIT_SECONDS, FORM_WAIT_SLICE_SECONDS
from tracker.shared.errors import SetupStoppedError

#: What the page shows in place of an answer that must stay hidden.
HIDDEN_ANSWER: Final[str] = "(hidden)"

#: The answers the page sends to a yes/no question.
YES: Final[str] = "yes"
NO: Final[str] = "no"


class QuestionKind(StrEnum):
    """How the page should ask."""

    TEXT = "text"
    SECRET = "secret"
    CONFIRM = "confirm"
    CONTINUE = "continue"


class EntryKind(StrEnum):
    """What one line of the transcript is."""

    SAID = "said"
    LINK = "link"
    ANSWER = "answer"


@dataclass(frozen=True, slots=True)
class Question:
    """One question waiting for the person at the page.

    Attributes:
        id: Grows with every question, so a late answer to an old one is ignored.
        kind: How to ask.
        prompt: The question itself.
        default: The answer offered: text to prefill, or ``yes``/``no``.
    """

    id: int
    kind: QuestionKind
    prompt: str
    default: str | None


@dataclass(frozen=True, slots=True)
class Entry:
    """One line of the transcript shown on the page."""

    kind: EntryKind
    text: str
    detail: str = ""


@dataclass(frozen=True, slots=True)
class Outcome:
    """How the set-up ended."""

    ok: bool
    message: str


@dataclass(slots=True)
class Conversation:
    """The shared state of one set-up session on the page.

    Attributes:
        clock: Seconds, monotonic; replaced in tests.
    """

    clock: Callable[[], float] = time.monotonic
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _entries: list[Entry] = field(default_factory=list)
    _question: Question | None = None
    _answers: queue.Queue[tuple[int, str]] = field(default_factory=queue.Queue)
    _next_id: int = 1
    _stopped: bool = False
    _outcome: Outcome | None = None
    _farewell_seen: bool = False
    _last_seen: float = 0.0

    def __post_init__(self) -> None:
        """Count the page as present from the start, so it has time to open."""
        self._last_seen = self.clock()

    # --- What the wizard does ------------------------------------------------

    def say(self, text: str) -> None:
        """Add one line to the transcript."""
        self._add(Entry(EntryKind.SAID, text))

    def link(self, url: str) -> None:
        """Add a page the person should open."""
        self._add(Entry(EntryKind.LINK, url))

    def ask(self, kind: QuestionKind, prompt: str, default: str | None = None) -> str:
        """Put one question to the page and wait for its answer.

        Args:
            kind: How to ask.
            prompt: The question.
            default: The answer offered.

        Returns:
            The answer as the page sent it.

        Raises:
            SetupStoppedError: If the person stopped from the page, or the page
                has not been seen for :data:`FORM_IDLE_LIMIT_SECONDS`.
        """
        with self._lock:
            question = Question(self._next_id, kind, prompt, default)
            self._next_id += 1
            self._question = question
        try:
            answer = self._wait_for(question.id)
        finally:
            with self._lock:
                self._question = None
        shown = HIDDEN_ANSWER if kind is QuestionKind.SECRET else answer
        self._add(Entry(EntryKind.ANSWER, prompt, shown))
        return answer

    def finish(self, outcome: Outcome) -> None:
        """Record how it ended, for the page to show."""
        with self._lock:
            self._outcome = outcome

    def farewell_seen(self) -> bool:
        """Tell whether the page has fetched the ending."""
        with self._lock:
            return self._farewell_seen

    # --- What the page does --------------------------------------------------

    def snapshot(self, after: int) -> dict[str, object]:
        """Describe the state for the page, with the entries it has not seen.

        Args:
            after: How many entries the page already has.

        Returns:
            Plain values ready to be sent as JSON.
        """
        with self._lock:
            self._last_seen = self.clock()
            if self._outcome is not None:
                self._farewell_seen = True
            entries = self._entries[max(after, 0) :]
            question = self._question
            outcome = self._outcome
        return {
            "entries": [
                {"kind": entry.kind.value, "text": entry.text, "detail": entry.detail}
                for entry in entries
            ],
            "next": max(after, 0) + len(entries),
            "question": None
            if question is None
            else {
                "id": question.id,
                "kind": question.kind.value,
                "prompt": question.prompt,
                "default": question.default,
            },
            "finished": None if outcome is None else {"ok": outcome.ok, "message": outcome.message},
        }

    def answer(self, question_id: int, value: str) -> bool:
        """Take the page's answer to the open question.

        Args:
            question_id: The question it answers.
            value: The answer.

        Returns:
            ``False`` when no question with that id is open any more.
        """
        with self._lock:
            if self._question is None or self._question.id != question_id:
                return False
        self._answers.put((question_id, value))
        return True

    def stop(self) -> None:
        """Note that the person wants to stop; the open question raises."""
        with self._lock:
            self._stopped = True

    # --- Inside ---------------------------------------------------------------

    def _add(self, entry: Entry) -> None:
        with self._lock:
            self._entries.append(entry)

    def _wait_for(self, question_id: int) -> str:
        """Block until the page answers this question, stopping when it is gone."""
        while True:
            try:
                answered_id, value = self._answers.get(timeout=FORM_WAIT_SLICE_SECONDS)
            except queue.Empty:
                self._raise_if_gone()
                continue
            if answered_id == question_id:
                return value

    def _raise_if_gone(self) -> None:
        with self._lock:
            stopped = self._stopped
            idle = self.clock() - self._last_seen
        if stopped:
            message = "you stopped the set-up from the page"
            raise SetupStoppedError(message)
        if idle > FORM_IDLE_LIMIT_SECONDS:
            message = "the set-up page was closed, or left alone for too long"
            raise SetupStoppedError(message)
