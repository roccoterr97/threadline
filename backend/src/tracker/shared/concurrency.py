"""Running several waits side by side.

A collector spends nearly all its time waiting for a source to answer. Asking
for several things at once shortens that wait without changing what is read.
How many requests a source accepts at once is that source's client's business;
this module only runs the work and keeps a failure clean.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Iterable
from typing import Any


async def gather_all[ResultT](
    coroutines: Iterable[Coroutine[Any, Any, ResultT]],
) -> list[ResultT]:
    """Run coroutines side by side and return their results in the order given.

    Unlike a bare :func:`asyncio.gather`, a failure does not leave the others
    running against a connection that is about to be closed: they are cancelled
    and waited for before the error is passed on.

    Args:
        coroutines: The work to run. Every one is started.

    Returns:
        One result per coroutine, in the order they were given.

    Raises:
        Exception: The first failure, exactly as it was raised.
    """
    tasks = [asyncio.ensure_future(coroutine) for coroutine in coroutines]
    try:
        return list(await asyncio.gather(*tasks))
    finally:
        unfinished = [task for task in tasks if not task.done()]
        for task in unfinished:
            task.cancel()
        await asyncio.gather(*unfinished, return_exceptions=True)
