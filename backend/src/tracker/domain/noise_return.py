"""Rules for when something the assistant threw away as noise comes back.

The owner's answers always win over the assistant's. The assistant calling a
thread or a person noise is a judgement about what it has read so far; the owner
writing to the person, or the person starting a new conversation, is news the
judgement never saw. What the owner decided himself is a different matter and
is never undone here: the dashboard's "Not relevant", a "no" or a "yes" to a
question, a correction by hand.

The data has no flag saying who hid a person, so the rules read it from what the
assistant leaves behind. When it rules a person out it marks *every* thread it
knows of as noise with itself as the decider, and nothing else. A person the
owner hid keeps the threads they had, which are not noise. So a hidden person
whose threads are all the assistant's noise (or who has none left on file) was
the assistant's doing, unless the owner has answered or corrected something
about them.

Every function here is pure: no clock, no database, no configuration.
"""

from __future__ import annotations

from dataclasses import dataclass

from tracker.domain.enums import Relevance, RelevanceDecidedBy


@dataclass(frozen=True, slots=True)
class ThreadRuling:
    """What a stored thread says about who decided its relevance.

    Attributes:
        relevance: The thread's stored relevance.
        decided_by: Who decided it, when anybody did.
    """

    relevance: Relevance
    decided_by: RelevanceDecidedBy | None = None

    @property
    def is_assistant_noise(self) -> bool:
        """Whether the assistant, and nobody else, threw this thread away."""
        return self.relevance is Relevance.NOISE and self.decided_by is RelevanceDecidedBy.AI


@dataclass(frozen=True, slots=True)
class PersonRuling:
    """What is stored about a hidden person that shows who hid them.

    Attributes:
        relevance: The person's stored relevance.
        threads: The threads still filed under the person.
        owner_answered: The owner answered a relevance question about them,
            yes or no.
        owner_corrected: The owner corrected their assessment by hand.
    """

    relevance: Relevance
    threads: tuple[ThreadRuling, ...] = ()
    owner_answered: bool = False
    owner_corrected: bool = False


def thread_comes_back(ruling: ThreadRuling, *, owner_wrote_again: bool) -> bool:
    """Decide whether a thread the assistant dropped is worth judging again.

    Only a new message *from the owner* counts. A reply is the strongest hint
    that a conversation is real, and it is new since the assistant read the
    thread; another message from the other side is what a newsletter does.

    Args:
        ruling: Who decided the thread's stored relevance.
        owner_wrote_again: Whether the owner sent a message that was not stored.

    Returns:
        ``True`` when the thread should go back to "unsure".
    """
    return owner_wrote_again and ruling.is_assistant_noise


def person_ruled_out_by_assistant(ruling: PersonRuling) -> bool:
    """Say whether the assistant, not the owner, is the reason a person is hidden.

    Args:
        ruling: What is stored about the person.

    Returns:
        ``True`` when the person may go back to "unsure" because of news.
    """
    if ruling.relevance is not Relevance.NOISE:
        return False
    if ruling.owner_answered or ruling.owner_corrected:
        return False
    return all(thread.is_assistant_noise for thread in ruling.threads)
