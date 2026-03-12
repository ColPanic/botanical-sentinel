from __future__ import annotations

import asyncio
import json
import logging

import aiomqtt
import asyncpg

from mqtt_bridge.config import DB_URL, MQTT_HOST, MQTT_PORT
from mqtt_bridge.db import insert_scan_events, upsert_devices, upsert_node
from mqtt_bridge.estimator import run_estimator
from mqtt_bridge.handler import extract_node_id, parse_ble, parse_wifi

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger(__name__)

# Populated by handle_status; used by handle_scan to stamp node position onto events.
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
    if coords:
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
    if data.get("gps_fix") and "gps_lat" in data:
        lat, lon = float(data["gps_lat"]), float(data["gps_lon"])
    elif "node_lat" in data and "node_lon" in data:
        lat, lon = float(data["node_lat"]), float(data["node_lon"])

    if lat is not None and lon is not None:
        _node_coords[node_id] = (lat, lon)

    await upsert_node(
        pool,
        node_id,
        firmware_ver=data.get("firmware_ver", ""),
        ip=data.get("ip", ""),
        lat=lat,
        lon=lon,
    )
    log.info("node=%s status uptime_ms=%s lat=%s lon=%s",
             node_id, data.get("uptime_ms"), lat, lon)


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
    await run(pool)
