import pytest
from unittest.mock import AsyncMock, MagicMock


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
    await upsert_node(pool, "scanner-01", firmware_ver="0.2.0", ip="10.0.0.1",
                      lat=38.123, lon=-122.456)
    call_args = conn.execute.call_args[0]
    sql = call_args[0]
    params = call_args[1:]
    assert "lat" in sql.lower()
    assert 38.123 in params
    assert -122.456 in params


async def test_upsert_node_without_coords_does_not_overwrite(mock_pool):
    pool, conn = mock_pool
    from mqtt_bridge.db import upsert_node
    await upsert_node(pool, "scanner-01", firmware_ver="0.2.0", ip="10.0.0.1",
                      lat=None, lon=None)
    sql = conn.execute.call_args[0][0]
    assert "CASE WHEN" in sql
