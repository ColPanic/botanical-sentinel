import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from mqtt_bridge.handler import ScanEvent


@pytest.fixture
def mock_pool():
    conn = AsyncMock()
    conn.execute = AsyncMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=cm)
    return pool, conn


async def test_upsert_node_with_coords(mock_pool):
    pool, conn = mock_pool
    from mqtt_bridge.db import upsert_node

    await upsert_node(
        pool, "scanner-01", firmware_ver="0.2.0", ip="10.0.0.1", lat=38.123, lon=-122.456
    )
    call_args = conn.execute.call_args[0]
    sql = call_args[0]
    params = call_args[1:]
    assert "lat" in sql.lower()
    assert 38.123 in params
    assert -122.456 in params


async def test_upsert_node_without_coords_does_not_overwrite(mock_pool):
    pool, conn = mock_pool
    from mqtt_bridge.db import upsert_node

    await upsert_node(pool, "scanner-01", firmware_ver="0.2.0", ip="10.0.0.1", lat=None, lon=None)
    sql = conn.execute.call_args[0][0]
    assert "CASE WHEN" in sql


async def test_insert_scan_events_includes_node_coords(mock_pool):
    pool, conn = mock_pool
    conn.executemany = AsyncMock()
    conn.execute = AsyncMock()
    from mqtt_bridge.db import insert_scan_events

    events = [
        ScanEvent(
            node_id="scanner-01",
            mac="AA:BB:CC:DD:EE:FF",
            rssi=-60,
            scan_type="wifi",
            ssid="Net",
            time=datetime(2026, 3, 12, tzinfo=UTC),
            node_lat=38.123,
            node_lon=-122.456,
        )
    ]
    await insert_scan_events(pool, events)
    rows = conn.executemany.call_args[0][1]
    assert rows[0][6] == 38.123  # node_lat is 7th element (index 6)
    assert rows[0][7] == -122.456  # node_lon is 8th element (index 7)


async def test_insert_scan_events_notify_payload_includes_devices(mock_pool):
    pool, conn = mock_pool
    conn.executemany = AsyncMock()
    conn.execute = AsyncMock()
    from mqtt_bridge.db import insert_scan_events

    events = [
        ScanEvent(
            node_id="scanner-01",
            mac="AA:BB:CC:DD:EE:FF",
            rssi=-65,
            scan_type="wifi",
            ssid="TestNet",
            time=datetime(2026, 3, 12, tzinfo=UTC),
            node_lat=None,
            node_lon=None,
        ),
        ScanEvent(
            node_id="scanner-01",
            mac="11:22:33:44:55:66",
            rssi=-80,
            scan_type="ble",
            ssid=None,
            time=datetime(2026, 3, 12, tzinfo=UTC),
            node_lat=None,
            node_lon=None,
        ),
    ]
    await insert_scan_events(pool, events)

    notify_call = conn.execute.call_args[0]
    payload = json.loads(notify_call[1])

    assert payload["node_id"] == "scanner-01"
    assert payload["scan_type"] == "wifi"
    assert "devices" in payload
    assert len(payload["devices"]) == 2
    assert payload["devices"][0]["mac"] == "AA:BB:CC:DD:EE:FF"
    assert payload["devices"][0]["rssi"] == -65
    assert payload["devices"][0]["ssid"] == "TestNet"
    assert payload["devices"][1]["mac"] == "11:22:33:44:55:66"
    assert payload["devices"][1]["ssid"] is None
    assert "count" not in payload


async def test_upsert_node_with_location_confirmed(mock_pool):
    pool, conn = mock_pool
    from mqtt_bridge.db import upsert_node

    await upsert_node(
        pool,
        "scanner-01",
        firmware_ver="0.2.0",
        ip="10.0.0.1",
        lat=38.123,
        lon=-122.456,
        location_confirmed=True,
    )
    call_args = conn.execute.call_args[0]
    sql = call_args[0]
    params = call_args[1:]
    assert "location_confirmed" in sql.lower()
    assert True in params


async def test_load_confirmed_node_coords(mock_pool):
    pool, conn = mock_pool
    conn.fetch = AsyncMock(
        return_value=[
            {"node_id": "scanner-01", "lat": 38.123, "lon": -122.456},
            {"node_id": "scanner-02", "lat": 51.500, "lon": -0.100},
        ]
    )
    from mqtt_bridge.db import load_confirmed_node_coords

    result = await load_confirmed_node_coords(pool)

    assert result == {
        "scanner-01": (38.123, -122.456),
        "scanner-02": (51.500, -0.100),
    }
    sql = conn.fetch.call_args[0][0]
    assert "location_confirmed" in sql.lower()


async def test_get_confirmed_node_coords_returns_none_when_not_confirmed(mock_pool):
    pool, conn = mock_pool
    conn.fetchrow = AsyncMock(return_value=None)
    from mqtt_bridge.db import get_confirmed_node_coords

    result = await get_confirmed_node_coords(pool, "scanner-01")
    assert result is None


async def test_get_confirmed_node_coords_returns_tuple_when_confirmed(mock_pool):
    pool, conn = mock_pool
    conn.fetchrow = AsyncMock(return_value={"lat": 38.123, "lon": -122.456})
    from mqtt_bridge.db import get_confirmed_node_coords

    result = await get_confirmed_node_coords(pool, "scanner-01")
    assert result == (38.123, -122.456)
