"""Tuning values for the daily run and the morning summary.

Nothing here is a secret and nothing here is chosen by a session at run time.
The address the summary goes to, the product name and the subject prefix are the
owner's settings, read through :func:`tracker.shared.config.get_settings` and
written into the summary file by Python, so a session can never send the
owner's day to somebody else.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from tracker.shared.constants.assessment import WORK_DIRECTORY

#: Days before the LinkedIn key expires at which the reminder starts appearing
#: in the summary, repeated every morning until the key is renewed.
KEY_REMINDER_DAYS: Final[int] = 7

#: Page holding the open yes/no questions.
DASHBOARD_REVIEW_PATH: Final[str] = "/review"

#: Page holding the run history.
DASHBOARD_RUNS_PATH: Final[str] = "/runs"

#: Where ``tracker summary build`` writes the summary by default. It sits in the
#: shared working directory, which git ignores.
SUMMARY_FILE: Final[Path] = WORK_DIRECTORY / "summary.json"

#: People listed in one section of the summary before it says "and N more".
#: A morning e-mail nobody finishes reading is a morning e-mail nobody reads,
#: and the session sending it types the whole body out, so a shorter one is
#: also one it copies without mistakes.
MAX_PEOPLE_PER_SECTION: Final[int] = 10

#: How far back "replied since yesterday" looks when there is no earlier run to
#: measure from — the first run, or a run after a long pause.
REPLY_WINDOW_FALLBACK_HOURS: Final[int] = 24

#: How many days before the start of "replied since yesterday" a message may
#: have been sent and still count as a reply, when it was only stored after
#: that start (a source was down for a morning). Without this limit a first
#: import of old mail, which is all stored at once, would list everyone.
REPLY_LATE_COLLECTION_DAYS: Final[int] = 3

#: Recent daily runs read when looking for the last one whose summary went out.
#: Refreshes are not counted, so however many there were, ten is a week and a
#: half of mornings, which is more than enough to find yesterday's.
RECENT_RUNS_SCANNED: Final[int] = 10

#: Longest note stored next to a failed step. It holds a short technical hint
#: for the run page — never message text, never a secret, never a stack trace.
MAX_ERROR_DETAIL_LENGTH: Final[int] = 200
