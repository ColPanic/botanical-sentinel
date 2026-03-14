from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.app import app, get_pool
from tests.conftest import make_mock_pool

NOW = datetime(2026, 3, 8, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def client_with_nodes():
    pool, conn = make_mock_pool(
        rows=[
            {
                "node_id": "scanner-01",
                "node_type": "esp32_scanner",
                "location": None,
                "last_seen": NOW,
                "firmware_ver": "0.2.0",
                "lat": 38.123,
                "lon": -122.456,
                "name": None,
            }
        ]
    )
    app.dependency_overrides[get_pool] = lambda: pool
    with patch("api.app.asyncpg.create_pool", new=AsyncMock(return_value=pool)):
        with TestClient(app) as c:
            yield c, conn
    app.dependency_overrides.clear()


def test_get_nodes_returns_list(client_with_nodes):
    client, _ = client_with_nodes
    response = client.get("/nodes")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["node_id"] == "scanner-01"
    assert data[0]["firmware_ver"] == "0.2.0"


def test_get_nodes_empty(client_with_nodes):
    client, conn = client_with_nodes
    conn.fetch = AsyncMock(return_value=[])
    response = client.get("/nodes")
    assert response.status_code == 200
    assert response.json() == []


def test_get_nodes_includes_coordinates(client_with_nodes):
    client, _ = client_with_nodes
    response = client.get("/nodes")
    data = response.json()
    assert data[0]["lat"] == 38.123
    assert data[0]["lon"] == -122.456
