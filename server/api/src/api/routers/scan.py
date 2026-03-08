from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends

from api.app import get_pool
from api.models import ScanEventResponse

router = APIRouter(prefix="/scan", tags=["scan"])

_SCAN_SELECT = "SELECT time, node_id, mac, rssi, scan_type, ssid FROM scan_events"


@router.get("/recent", response_model=list[ScanEventResponse])
async def recent_all(
    limit: int = 100,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Return the most recent scan events across all nodes."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"{_SCAN_SELECT} ORDER BY time DESC LIMIT $1",
            limit,
        )
    return [dict(r) for r in rows]


@router.get("/{node_id}/recent", response_model=list[ScanEventResponse])
async def recent_for_node(
    node_id: str,
    limit: int = 100,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Return the most recent scan events for a specific node."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"{_SCAN_SELECT} WHERE node_id = $1 ORDER BY time DESC LIMIT $2",
            node_id,
            limit,
        )
    return [dict(r) for r in rows]
