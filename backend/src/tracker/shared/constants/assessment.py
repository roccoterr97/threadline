"""Tuning values for the AI assessment.

These numbers decide how patient Threadline is, how much text it shows the
assistant, and how strict it is with what comes back. They are operational
tuning, not deployment settings, so they live here and never in ``.env``. The
code that *interprets* them lives in :mod:`tracker.domain.assessment_policy`.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Final

from tracker.shared.config import REPOSITORY_ROOT

#: Days of silence after the owner's own last message before a person counts as
#: having gone quiet.
GONE_QUIET_AFTER_DAYS: Final[int] = 10

#: Working days after the last contact to chase someone the owner is waiting on.
FOLLOW_UP_AFTER_WORKING_DAYS: Final[int] = 5

#: Confidence at or above which a verdict is accepted without a question to the
#: owner. Anything below becomes a review item.
REVIEW_THRESHOLD: Final[Decimal] = Decimal("0.6")

#: People described in one batch file.
BATCH_SIZE: Final[int] = 10

#: Most recent messages of one thread written into a dossier.
MESSAGES_PER_THREAD: Final[int] = 30

#: Characters of one message body written into a dossier.
MAX_MESSAGE_CHARACTERS: Final[int] = 4000

#: Longest accepted ``next_action``.
MAX_NEXT_ACTION_LENGTH: Final[int] = 120

#: Longest accepted ``summary``.
MAX_SUMMARY_LENGTH: Final[int] = 400

#: Longest accepted organisation name or role title.
MAX_NAME_LENGTH: Final[int] = 200

#: Verdicts accepted in one result file: one batch, never more.
MAX_VERDICTS_PER_FILE: Final[int] = BATCH_SIZE

#: How far in the past a due date may sit before it is rejected as nonsense.
DUE_DATE_PAST_LIMIT_DAYS: Final[int] = 365

#: How far in the future a due date may sit before it is rejected as nonsense.
DUE_DATE_FUTURE_LIMIT_DAYS: Final[int] = 365

#: Working directory for the files Python and the assistant exchange. It is
#: ignored by git: dossiers hold message text and never belong in the history.
WORK_DIRECTORY: Final[Path] = REPOSITORY_ROOT / "work"

#: Where ``tracker ai export`` writes the dossiers.
BATCH_DIRECTORY: Final[Path] = WORK_DIRECTORY / "batches"

#: Where the assistant writes its verdicts and ``tracker ai import`` reads them.
RESULT_DIRECTORY: Final[Path] = WORK_DIRECTORY / "results"
