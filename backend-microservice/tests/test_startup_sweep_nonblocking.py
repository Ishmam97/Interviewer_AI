"""
Regression test: the startup stale-analysis sweep must never block the event
loop.

Business rule: Cloud Run's startup probe hits /health to decide when to route
traffic to a new instance. FirebaseManager's sweep methods are synchronous
network I/O — if _sweep_stale_analyses_once ran them directly on the event
loop (even via a "fire and forget" asyncio.create_task, which does NOT make
blocking code non-blocking), a slow or unreachable Firestore at boot would
freeze every other coroutine, including the health handler, until the call
finished or errored. Caught via manual Docker testing: /health returned
nothing for 20-30s until an ADC-lookup failure timed out. asyncio.to_thread is
what actually decouples the sweep from the loop.
"""

import asyncio
import time
from unittest.mock import patch

from app.server import _sweep_stale_analyses_once


def _slow_sweep():
    time.sleep(0.2)  # simulates a slow/unreachable Firestore call


async def test_sweep_does_not_block_event_loop():
    counter = {"ticks": 0}

    async def _ticker():
        while True:
            counter["ticks"] += 1
            await asyncio.sleep(0.01)

    with patch("app.server._sweep_stale_analyses_sync", side_effect=_slow_sweep):
        ticker_task = asyncio.create_task(_ticker())
        await _sweep_stale_analyses_once()
        ticker_task.cancel()

    # If the sweep had blocked the loop for its ~0.2s duration, the ticker
    # (which yields every 10ms) would have accumulated far fewer ticks.
    assert counter["ticks"] >= 5, (
        "the event loop was blocked during the sweep — other coroutines "
        "(including /health) could not run"
    )


async def test_sweep_swallows_errors_without_raising():
    with patch("app.server._sweep_stale_analyses_sync", side_effect=RuntimeError("Firestore down")):
        await _sweep_stale_analyses_once()  # must not raise
