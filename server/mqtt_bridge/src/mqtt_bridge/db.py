from __future__ import annotations

import json

import asyncpg
from mac_vendor_lookup import MacLookup, VendorNotFoundError

from mqtt_bridge.handler import ScanEvent

_mac_lookup = MacLookup()


async def lookup_vendor(mac: str) -> str | None:
    """Return OUI vendor string or None if not found."""
    try:
        return await _mac_lookup.async_lookup.lookup(mac)
    except (VendorNotFoundError, KeyError, ValueError):
        return None


async def upsert_node(
    pool: asyncpg.Pool,
    node_id: str,
    firmware_ver: str,
    ip: str,
    lat: float | None = None,
    lon: float | None = None,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO nodes (node_id, node_type, last_seen, firmware_ver, lat, lon)
            VALUES ($1, 'esp32_scanner', now(), $2, $3, $4)
            ON CONFLICT (node_id) DO UPDATE SET
                last_seen    = now(),
                firmware_ver = EXCLUDED.firmware_ver,
                lat = CASE WHEN $3 IS NOT NULL THEN $3 ELSE nodes.lat END,
                lon = CASE WHEN $4 IS NOT NULL THEN $4 ELSE nodes.lon END
            """,
            node_id,
            firmware_ver,
            lat,
            lon,
        )


async def upsert_devices(pool: asyncpg.Pool, events: list[ScanEvent]) -> None:
    async with pool.acquire() as conn:
        for event in events:
            vendor = await lookup_vendor(event.mac)
            await conn.execute(
                """
                INSERT INTO devices (mac, device_type, first_seen, last_seen, tag, vendor, ssid)
                VALUES ($1, $2, now(), now(), 'unknown', $3, $4)
                ON CONFLICT (mac) DO UPDATE
                    SET last_seen = now(),
                        vendor    = COALESCE(devices.vendor, EXCLUDED.vendor),
                        ssid      = COALESCE(EXCLUDED.ssid, devices.ssid)
                """,
                event.mac,
                event.scan_type,
                vendor,
                event.ssid or None,
            )


async def insert_scan_events(pool: asyncpg.Pool, events: list[ScanEvent]) -> None:
    if not events:
        return
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO scan_events (time, node_id, mac, rssi, scan_type, ssid)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            [(e.time, e.node_id, e.mac, e.rssi, e.scan_type, e.ssid) for e in events],
        )
        payload = json.dumps(
            {
                "node_id": events[0].node_id,
                "scan_type": events[0].scan_type,
                "count": len(events),
            }
        )
        await conn.execute("SELECT pg_notify('scan_events', $1)", payload)
