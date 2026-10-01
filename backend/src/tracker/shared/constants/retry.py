"""Retry policy for reaching external dependencies.

Retries are bounded and linear: a fixed number of attempts, a fixed delay
between them. Exhaustion fails fast with one clean error line.
"""

from __future__ import annotations

from typing import Final

#: How many times a connection attempt is made before giving up.
CONNECT_ATTEMPTS: Final[int] = 10

#: Seconds to wait between two connection attempts.
CONNECT_DELAY_SECONDS: Final[float] = 5.0

#: Attempts the health check makes; it reports a problem rather than waiting it out.
HEALTHCHECK_ATTEMPTS: Final[int] = 2

#: Seconds the health check waits between its two attempts.
HEALTHCHECK_DELAY_SECONDS: Final[float] = 1.0

#: Attempts made for one request to an outside source (LinkedIn, the mailbox).
#: A daily run makes hundreds of them in a row, so a single dropped connection
#: must not end the whole collection.
SOURCE_REQUEST_ATTEMPTS: Final[int] = 4

#: Seconds between two attempts at the same request.
SOURCE_REQUEST_DELAY_SECONDS: Final[float] = 2.0

#: Longest wait honoured from a "Retry-After" header, so a source cannot park
#: the daily run for an unreasonable length of time.
SOURCE_RETRY_AFTER_CAP_SECONDS: Final[float] = 60.0

#: Attempts made for one database request. A dropped connection mid-run would
#: otherwise end a whole collection; every write is idempotent, so repeating
#: one is safe. A refusal from the database itself is never retried.
REQUEST_ATTEMPTS: Final[int] = 3

#: Seconds between two attempts at the same database request.
REQUEST_DELAY_SECONDS: Final[float] = 1.0
