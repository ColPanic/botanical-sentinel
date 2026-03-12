from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends

from api.app import get_pool
from api.models import NodeResponse

router = APIRouter(prefix="/nodes", tags=["nodes"])


@router.get("", response_model=list[NodeResponse])
async def list_nodes(pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT node_id, node_type, location, last_seen, firmware_ver, lat, lon "
            "FROM nodes ORDER BY last_seen DESC"
        )
    return [dict(r) for r in rows]
