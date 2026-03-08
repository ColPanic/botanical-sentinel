from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from api.app import get_pool
from api.models import DeviceResponse, LabelUpdate, TagUpdate

router = APIRouter(prefix="/devices", tags=["devices"])

VALID_TAGS = {"known_resident", "known_vehicle", "unknown", "ignored"}


@router.get("", response_model=list[DeviceResponse])
async def list_devices(
    tag: str | None = None,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """List all devices, optionally filtered by tag."""
    async with pool.acquire() as conn:
        if tag:
            rows = await conn.fetch(
                "SELECT mac, device_type, label, tag, first_seen, last_seen, vendor "
                "FROM devices WHERE tag = $1 ORDER BY last_seen DESC",
                tag,
            )
        else:
            rows = await conn.fetch(
                "SELECT mac, device_type, label, tag, first_seen, last_seen, vendor "
                "FROM devices ORDER BY tag = 'unknown' DESC, last_seen DESC"
            )
    return [dict(r) for r in rows]


@router.put("/{mac}/label")
async def set_label(
    mac: str,
    body: LabelUpdate,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Set a human-readable label on a device."""
    async with pool.acquire() as conn:
        status = await conn.execute(
            "UPDATE devices SET label = $1 WHERE mac = $2",
            body.label,
            mac.upper(),
        )
    if status == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Device not found")
    return {"mac": mac, "label": body.label}


@router.put("/{mac}/tag")
async def set_tag(
    mac: str,
    body: TagUpdate,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Set the classification tag on a device."""
    if body.tag not in VALID_TAGS:
        raise HTTPException(
            status_code=422,
            detail=f"tag must be one of: {', '.join(sorted(VALID_TAGS))}",
        )
    async with pool.acquire() as conn:
        status = await conn.execute(
            "UPDATE devices SET tag = $1 WHERE mac = $2",
            body.tag,
            mac.upper(),
        )
    if status == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Device not found")
    return {"mac": mac, "tag": body.tag}
