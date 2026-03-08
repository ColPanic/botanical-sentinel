from __future__ import annotations

import asyncio
import json
import logging

import aiomqtt
import asyncpg

from mqtt_bridge.config import DB_URL, MQTT_HOST, MQTT_PORT
from mqtt_bridge.db import insert_scan_events, upsert_devices, upsert_node
from mqtt_bridge.handler import extract_node_id, parse_ble, parse_wifi

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger(__name__)


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

    await upsert_devices(pool, events)
    await insert_scan_events(pool, events)
    log.info("node=%s topic=%s count=%d", node_id, topic.split("/")[-1], len(events))


async def handle_status(pool: asyncpg.Pool, topic: str, payload: bytes) -> None:
    node_id = extract_node_id(topic)
    data: dict = json.loads(payload)
    await upsert_node(
        pool,
        node_id,
        firmware_ver=data.get("firmware_ver", ""),
        ip=data.get("ip", ""),
    )
    log.info("node=%s status uptime_ms=%s", node_id, data.get("uptime_ms"))


async def run(pool: asyncpg.Pool) -> None:
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


async def main() -> None:
    log.info("Connecting to database")
    pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=5)
    log.info("Database connected")
    await run(pool)
