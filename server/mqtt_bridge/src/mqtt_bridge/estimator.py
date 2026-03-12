from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import UTC, datetime

import asyncpg

log = logging.getLogger(__name__)

EARTH_RADIUS_M = 6_371_000.0
# Log-distance path loss constants
_TX_POWER_DBM = -59    # reference RSSI at 1 m (reasonable default for WiFi/BLE)
_PATH_LOSS_EXP = 2.7   # outdoor path loss exponent


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in metres between two GPS coordinates."""
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return EARTH_RADIUS_M * 2 * math.asin(math.sqrt(a))


def rssi_to_distance(rssi: int) -> float:
    """Estimate distance in metres from RSSI using log-distance path loss model."""
    return 10 ** ((_TX_POWER_DBM - rssi) / (10 * _PATH_LOSS_EXP))


def weighted_centroid(nodes: list[tuple[float, float, int]]) -> tuple[float, float]:
    """
    Compute weighted centroid of node positions.

    Args:
        nodes: list of (lat, lon, rssi) tuples

    Returns:
        (lat, lon) estimate
    """
    weights = [10 ** (rssi / 10) for _, _, rssi in nodes]
    total = sum(weights)
    lat = sum(w * n[0] for w, n in zip(weights, nodes)) / total
    lon = sum(w * n[1] for w, n in zip(weights, nodes)) / total
    return lat, lon


def _accuracy_single(rssi: int) -> float:
    """Rough accuracy estimate for a single-node observation."""
    return rssi_to_distance(rssi)


def _accuracy_centroid(
    nodes: list[tuple[float, float, int]],
    est_lat: float,
    est_lon: float,
) -> float:
    """Weighted stddev of great-circle distances from estimate to each node."""
    weights = [10 ** (rssi / 10) for _, _, rssi in nodes]
    total = sum(weights)
    variance = sum(
        w * haversine(est_lat, est_lon, lat, lon) ** 2
        for w, (lat, lon, _) in zip(weights, nodes)
    ) / total
    return math.sqrt(variance)


async def _estimate_once(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT mac, node_lat, node_lon, MAX(rssi) AS rssi
            FROM scan_events
            WHERE time > now() - INTERVAL '90 seconds'
              AND node_lat IS NOT NULL
            GROUP BY mac, node_lat, node_lon
            """
        )

    # Group rows by mac
    by_mac: dict[str, list[tuple[float, float, int]]] = {}
    for row in rows:
        by_mac.setdefault(row["mac"], []).append(
            (row["node_lat"], row["node_lon"], row["rssi"])
        )

    if not by_mac:
        return

    now = datetime.now(UTC)
    inserts: list[tuple] = []
    notifications: list[str] = []

    for mac, node_readings in by_mac.items():
        node_count = len(node_readings)

        if node_count == 1:
            lat, lon, rssi = node_readings[0]
            accuracy_m = _accuracy_single(rssi)
            method = "single"
        else:
            lat, lon = weighted_centroid(node_readings)
            accuracy_m = _accuracy_centroid(node_readings, lat, lon)
            method = "centroid"

        inserts.append((now, mac, lat, lon, accuracy_m, node_count, method))
        notifications.append(
            json.dumps({
                "type": "position_update",
                "mac": mac,
                "lat": lat,
                "lon": lon,
                "accuracy_m": accuracy_m,
                "node_count": node_count,
                "method": method,
                "time": now.isoformat(),
            })
        )

    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO position_estimates
                (time, mac, lat, lon, accuracy_m, node_count, method)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            inserts,
        )
        for payload in notifications:
            await conn.execute("SELECT pg_notify('position_estimates', $1)", payload)

    log.info("estimator: updated %d device positions", len(inserts))


async def run_estimator(pool: asyncpg.Pool) -> None:
    """Run position estimation every 30 seconds."""
    while True:
        try:
            await _estimate_once(pool)
        except Exception:
            log.exception("Estimator error — will retry next cycle")
        await asyncio.sleep(30)
