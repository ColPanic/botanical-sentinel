from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.app import app, get_pool
from tests.conftest import make_mock_pool

NOW = datetime(2026, 3, 12, 10, 0, 0, tzinfo=UTC)

POSITION_ROW = {
    "time": NOW,
    "mac": "AA:BB:CC:DD:EE:FF",
    "lat": 38.123,
    "lon": -122.456,
    "accuracy_m": 12.5,
    "node_count": 3,
    "method": "centroid",
    "label": "iPhone",
    "tag": "known_resident",
    "vendor": "Apple",
    "device_type": "wifi",
}


@pytest.fixture
def client_with_positions():
    pool, conn = make_mock_pool(rows=[POSITION_ROW])
    app.dependency_overrides[get_pool] = lambda: pool
    with patch("api.app.asyncpg.create_pool", new=AsyncMock(return_value=pool)):
        with TestClient(app) as c:
            yield c, conn
    app.dependency_overrides.clear()


def test_get_positions_current(client_with_positions):
    client, _ = client_with_positions
    response = client.get("/positions/current")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["mac"] == "AA:BB:CC:DD:EE:FF"
    assert data[0]["lat"] == 38.123
    assert data[0]["method"] == "centroid"


def test_get_positions_active(client_with_positions):
    client, _ = client_with_positions
    response = client.get("/positions/active?window_minutes=5")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_position_history(client_with_positions):
    client, _ = client_with_positions
    response = client.get("/positions/AA:BB:CC:DD:EE:FF/history?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["mac"] == "AA:BB:CC:DD:EE:FF"


def test_get_positions_current_tag_filter_passes_param(client_with_positions):
    client, conn = client_with_positions
    conn.fetch = AsyncMock(return_value=[])
    response = client.get("/positions/current?tag=unknown")
    assert response.status_code == 200
    # Verify the tag value was passed as a query parameter (not None)
    args = conn.fetch.call_args[0]
    assert "unknown" in args  # tag="unknown" must be passed to conn.fetch


def test_get_positions_current_no_tag_passes_none(client_with_positions):
    client, conn = client_with_positions
    conn.fetch = AsyncMock(return_value=[])
    response = client.get("/positions/current")
    assert response.status_code == 200
    args = conn.fetch.call_args[0]
    assert None in args  # tag=None must be passed for the IS NULL check
