import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import mqtt_bridge.main as main_module


@pytest.fixture(autouse=True)
def reset_node_coords():
    main_module._node_coords.clear()
    yield
    main_module._node_coords.clear()


@pytest.fixture
def mock_pool():
    conn = AsyncMock()
    conn.execute = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=cm)
    return pool


@pytest.mark.asyncio
async def test_handle_status_tbeam_gps_fix_caches_coords(mock_pool):
    payload = json.dumps(
        {
            "firmware_ver": "0.1.0",
            "ip": "10.0.0.2",
            "gps_fix": True,
            "gps_lat": 38.123,
            "gps_lon": -122.456,
            "uptime_ms": 1000,
        }
    ).encode()
    with (
        patch("mqtt_bridge.main.upsert_node", new=AsyncMock()) as mock_upsert,
        patch(
            "mqtt_bridge.main.get_confirmed_node_coords",
            new=AsyncMock(return_value=(38.123, -122.456)),
        ),
    ):
        await main_module.handle_status(mock_pool, "nodes/tbeam-01/status", payload)
    assert main_module._node_coords["tbeam-01"] == (38.123, -122.456)
    _, kwargs = mock_upsert.call_args
    assert kwargs["lat"] == 38.123
    assert kwargs["location_confirmed"] is True


@pytest.mark.asyncio
async def test_handle_status_firmware_static_coords_not_cached(mock_pool):
    """Firmware-reported node_lat/node_lon must not populate _node_coords."""
    payload = json.dumps(
        {
            "firmware_ver": "0.2.0",
            "ip": "10.0.0.3",
            "node_lat": 38.500,
            "node_lon": -122.900,
            "uptime_ms": 2000,
        }
    ).encode()
    with (
        patch("mqtt_bridge.main.upsert_node", new=AsyncMock()),
        patch("mqtt_bridge.main.get_confirmed_node_coords", new=AsyncMock(return_value=None)),
    ):
        await main_module.handle_status(mock_pool, "nodes/scanner-01/status", payload)
    assert "scanner-01" not in main_module._node_coords


@pytest.mark.asyncio
async def test_handle_status_confirmed_db_coords_are_cached(mock_pool):
    """After a status message, confirmed coords from DB are loaded into _node_coords."""
    payload = json.dumps({"firmware_ver": "0.2.0", "ip": "10.0.0.3", "uptime_ms": 2000}).encode()
    with (
        patch("mqtt_bridge.main.upsert_node", new=AsyncMock()),
        patch(
            "mqtt_bridge.main.get_confirmed_node_coords",
            new=AsyncMock(return_value=(51.500, -0.100)),
        ),
    ):
        await main_module.handle_status(mock_pool, "nodes/scanner-02/status", payload)
    assert main_module._node_coords["scanner-02"] == (51.500, -0.100)


@pytest.mark.asyncio
async def test_handle_status_no_gps_fix_does_not_cache(mock_pool):
    payload = json.dumps(
        {"firmware_ver": "0.1.0", "ip": "10.0.0.2", "gps_fix": False, "uptime_ms": 500}
    ).encode()
    with (
        patch("mqtt_bridge.main.upsert_node", new=AsyncMock()),
        patch("mqtt_bridge.main.get_confirmed_node_coords", new=AsyncMock(return_value=None)),
    ):
        await main_module.handle_status(mock_pool, "nodes/tbeam-01/status", payload)
    assert "tbeam-01" not in main_module._node_coords


@pytest.mark.asyncio
async def test_handle_scan_stamps_coords_from_cache(mock_pool):
    main_module._node_coords["scanner-01"] = (38.123, -122.456)
    payload = json.dumps(
        [{"ssid": "Net", "bssid": "aa:bb:cc:dd:ee:ff", "rssi": -60, "channel": 6}]
    ).encode()
    stamped_events = []

    async def capture_events(pool, events):
        stamped_events.extend(events)

    with (
        patch("mqtt_bridge.main.upsert_devices", new=AsyncMock()),
        patch("mqtt_bridge.main.insert_scan_events", new=capture_events),
    ):
        await main_module.handle_scan(mock_pool, "nodes/scanner-01/scan/wifi", payload)

    assert len(stamped_events) == 1
    assert stamped_events[0].node_lat == 38.123
    assert stamped_events[0].node_lon == -122.456


@pytest.mark.asyncio
async def test_handle_scan_unconfirmed_node_drops_scan(mock_pool):
    """Scans from nodes with no confirmed location are dropped entirely."""
    # scanner-99 has no entry in _node_coords
    payload = json.dumps(
        [{"ssid": "Net", "bssid": "bb:cc:dd:ee:ff:00", "rssi": -70, "channel": 1}]
    ).encode()
    mock_upsert_devices = AsyncMock()
    mock_insert_events = AsyncMock()
    with (
        patch("mqtt_bridge.main.upsert_devices", new=mock_upsert_devices),
        patch("mqtt_bridge.main.insert_scan_events", new=mock_insert_events),
    ):
        await main_module.handle_scan(mock_pool, "nodes/scanner-99/scan/wifi", payload)
    mock_upsert_devices.assert_not_called()
    mock_insert_events.assert_not_called()
