from __future__ import annotations

import asyncio
import logging

import asyncpg

log = logging.getLogger(__name__)


async def run_estimator(pool: asyncpg.Pool) -> None:
    """Stub — full implementation in next task."""
    while True:
        await asyncio.sleep(30)
