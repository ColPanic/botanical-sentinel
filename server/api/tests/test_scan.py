from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.app import app, get_pool
from tests.conftest import make_mock_pool

NOW = datetime(2026, 3, 8, 12, 0, 0, tzinfo=UTC)

EVENT_ROW = {
    "time": NOW,
    "node_id": "scanner-01",
    "mac": "AA:BB:CC:DD:EE:FF",
    "rssi": -55,
    "scan_type": "wifi",
    "ssid": "MyNet",
}


@pytest.fixture
def client_scan():
    pool, conn = make_mock_pool(rows=[EVENT_ROW])
    app.dependency_overrides[get_pool] = lambda: pool
    try:
        with patch("api.app.asyncpg.create_pool", new=AsyncMock(return_value=pool)):
            with TestClient(app) as c:
                yield c, conn
    finally:
        app.dependency_overrides.clear()


def test_get_recent_all_nodes(client_scan):
    client, _ = client_scan
    response = client.get("/scan/recent")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["mac"] == "AA:BB:CC:DD:EE:FF"


def test_get_recent_default_limit_is_100(client_scan):
    client, conn = client_scan
    client.get("/scan/recent")
    call_args = conn.fetch.call_args
    kwargs_vals = (call_args.kwargs or {}).values()
    assert "100" in str(call_args) or 100 in call_args.args or 100 in kwargs_vals


def test_get_recent_for_node(client_scan):
    client, _ = client_scan
    response = client.get("/scan/scanner-01/recent")
    assert response.status_code == 200
    assert response.json()[0]["node_id"] == "scanner-01"


def test_get_recent_custom_limit(client_scan):
    client, _ = client_scan
    response = client.get("/scan/recent?limit=50")
    assert response.status_code == 200
