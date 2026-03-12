from __future__ import annotations

from datetime import datetime

import asyncpg
from fastapi import APIRouter, Depends, Query

from api.app import get_pool
from api.models import PositionResponse

router = APIRouter(prefix="/positions", tags=["positions"])

_HISTORY_SQL = """
    SELECT p.time, p.mac, p.lat, p.lon, p.accuracy_m, p.node_count, p.method,
           d.label, d.tag, d.vendor, d.device_type
    FROM position_estimates p
    JOIN devices d USING (mac)
    WHERE p.mac = $1
      AND ($2::timestamptz IS NULL OR p.time >= $2)
    ORDER BY p.time ASC
    LIMIT $3
"""


@router.get("/current", response_model=list[PositionResponse])
async def current_positions(
    tag: str | None = None,
    pool: asyncpg.Pool = Depends(get_pool),
):
    # Use uniform parameterisation — $1::text IS NULL safely handles the no-filter case
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (p.mac)
                p.time, p.mac, p.lat, p.lon, p.accuracy_m, p.node_count, p.method,
                d.label, d.tag, d.vendor, d.device_type
            FROM position_estimates p
            JOIN devices d USING (mac)
            WHERE ($1::text IS NULL OR d.tag = $1)
            ORDER BY p.mac, p.time DESC
            """,
            tag,
        )
    return [dict(r) for r in rows]


@router.get("/active", response_model=list[PositionResponse])
async def active_positions(
    window_minutes: int = Query(default=5, ge=1, le=1440),
    pool: asyncpg.Pool = Depends(get_pool),
):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (p.mac)
                p.time, p.mac, p.lat, p.lon, p.accuracy_m, p.node_count, p.method,
                d.label, d.tag, d.vendor, d.device_type
            FROM position_estimates p
            JOIN devices d USING (mac)
            WHERE p.time > now() - ($1 * INTERVAL '1 minute')
            ORDER BY p.mac, p.time DESC
            """,
            window_minutes,
        )
    return [dict(r) for r in rows]


@router.get("/{mac}/history", response_model=list[PositionResponse])
async def position_history(
    mac: str,
    since: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    pool: asyncpg.Pool = Depends(get_pool),
):
    async with pool.acquire() as conn:
        rows = await conn.fetch(_HISTORY_SQL, mac.upper(), since, limit)
    return [dict(r) for r in rows]
