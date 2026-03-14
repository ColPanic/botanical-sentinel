from __future__ import annotations

import asyncio
import json
import logging

import aiomqtt
import asyncpg

from mqtt_bridge.config import DB_URL, MQTT_HOST, MQTT_PORT
from mqtt_bridge.db import (
    get_confirmed_node_coords,
    insert_scan_events,
    load_confirmed_node_coords,
    upsert_devices,
    upsert_node,
)
from mqtt_bridge.estimator import run_estimator
from mqtt_bridge.handler import extract_node_id, parse_ble, parse_wifi

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger(__name__)

# Populated from confirmed DB records at startup and refreshed on each status message.
# Only nodes with location_confirmed=true in the DB ever appear here.
_node_coords: dict[str, tuple[float, float]] = {}


async def handle_scan(pool: asyncpg.Pool, topic: str, payload: bytes) -> None:
    node_id = extract_node_id(topic)

    if "/scan/wifi" in topic:
        events = parse_wifi(node_id, payload)
    elif "/scan/bt" in topic:
        events = parse_ble(node_id, payload)
    else:
        return

    if not events:
        return

    coords = _node_coords.get(node_id)
    if coords is None:
        log.debug("node=%s has no confirmed location — scan dropped", node_id)
        return

    for e in events:
        e.node_lat, e.node_lon = coords

    await upsert_devices(pool, events)
    await insert_scan_events(pool, events)
    log.info("node=%s topic=%s count=%d", node_id, topic.split("/")[-1], len(events))


async def handle_status(pool: asyncpg.Pool, topic: str, payload: bytes) -> None:
    node_id = extract_node_id(topic)
    data: dict = json.loads(payload)

    lat: float | None = None
    lon: float | None = None
    location_confirmed = False
    if data.get("gps_fix") and "gps_lat" in data:
        lat, lon = float(data["gps_lat"]), float(data["gps_lon"])
        location_confirmed = True
    # Firmware-reported node_lat/node_lon are intentionally ignored.
    # Location for fixed nodes is only confirmed by the user via PATCH /nodes/{id}.

    await upsert_node(
        pool,
        node_id,
        firmware_ver=data.get("firmware_ver", ""),
        ip=data.get("ip", ""),
        lat=lat,
        lon=lon,
        location_confirmed=location_confirmed,
    )

    # Refresh this node's confirmed coords from DB (picks up API-set locations too).
    coords = await get_confirmed_node_coords(pool, node_id)
    if coords:
        _node_coords[node_id] = coords

    log.info("node=%s status uptime_ms=%s lat=%s lon=%s", node_id, data.get("uptime_ms"), lat, lon)


async def _run_mqtt(pool: asyncpg.Pool) -> None:
    while True:
        try:
            async with aiomqtt.Client(MQTT_HOST, MQTT_PORT) as client:
                log.info("Connected to MQTT broker %s:%d", MQTT_HOST, MQTT_PORT)
                await client.subscribe("nodes/+/scan/#")
                await client.subscribe("nodes/+/status")

                async for message in client.messages:
                    topic = str(message.topic)
                    try:
                        if "/scan/" in topic:
                            await handle_scan(pool, topic, message.payload)
                        elif "/status" in topic:
                            await handle_status(pool, topic, message.payload)
                    except Exception:
                        log.exception("Error handling topic=%s", topic)

        except aiomqtt.MqttError as exc:
            log.warning("MQTT connection lost: %s — reconnecting in 5s", exc)
            await asyncio.sleep(5)


async def run(pool: asyncpg.Pool) -> None:
    await asyncio.gather(
        _run_mqtt(pool),
        run_estimator(pool),
    )


async def main() -> None:
    log.info("Connecting to database")
    pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=5)
    log.info("Database connected")

    confirmed = await load_confirmed_node_coords(pool)
    _node_coords.update(confirmed)
    log.info("Loaded %d confirmed node location(s) from DB", len(confirmed))

    await run(pool)
