"""Work run side by side keeps its order, and a failure stays one clean error."""

from __future__ import annotations

import asyncio

import pytest

from tracker.shared.concurrency import gather_all
from tracker.shared.errors import SourceUnavailableError


@pytest.mark.asyncio
async def test_results_come_back_in_the_order_given_not_the_order_finished() -> None:
    first_may_finish = asyncio.Event()
    finished: list[str] = []

    async def slow() -> str:
        await first_may_finish.wait()
        finished.append("slow")
        return "slow"

    async def quick() -> str:
        finished.append("quick")
        first_may_finish.set()
        return "quick"

    results = await gather_all([slow(), quick()])

    assert finished == ["quick", "slow"]
    assert results == ["slow", "quick"]


@pytest.mark.asyncio
async def test_nothing_to_run_gives_nothing_back() -> None:
    assert await gather_all([]) == []


@pytest.mark.asyncio
async def test_the_first_failure_is_raised_as_itself_and_the_rest_is_stopped() -> None:
    never = asyncio.Event()
    stopped: list[str] = []

    async def waits_forever() -> str:
        try:
            await never.wait()
        except asyncio.CancelledError:
            stopped.append("cancelled")
            raise
        return "unreachable"

    async def fails() -> str:
        message = "the mailbox answered status 403"
        raise SourceUnavailableError(message)

    with pytest.raises(SourceUnavailableError, match="403"):
        await gather_all([waits_forever(), fails(), waits_forever()])

    assert stopped == ["cancelled", "cancelled"]
