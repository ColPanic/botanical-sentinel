from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from api.app import get_pool
from api.models import NodeResponse, NodeUpdate

router = APIRouter(prefix="/nodes", tags=["nodes"])

_NODE_SELECT = (
    "SELECT node_id, node_type, location, last_seen, firmware_ver, lat, lon, name FROM nodes"
)


@router.get("", response_model=list[NodeResponse])
async def list_nodes(pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        rows = await conn.fetch(f"{_NODE_SELECT} ORDER BY last_seen DESC")
    return [dict(r) for r in rows]


@router.patch("/{node_id}", response_model=NodeResponse)
async def update_node(
    node_id: str,
    body: NodeUpdate,
    pool: asyncpg.Pool = Depends(get_pool),
):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE nodes SET name=$1, lat=$2, lon=$3 WHERE node_id=$4 RETURNING *",
            body.name,
            body.lat,
            body.lon,
            node_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Node not found")
    return dict(row)
