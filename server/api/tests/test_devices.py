from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.app import app, get_pool
from tests.conftest import make_mock_pool

NOW = datetime(2026, 3, 8, 12, 0, 0, tzinfo=UTC)

DEVICE_ROW = {
    "mac": "AA:BB:CC:DD:EE:FF",
    "device_type": "wifi",
    "label": None,
    "tag": "unknown",
    "first_seen": NOW,
    "last_seen": NOW,
    "vendor": "Apple, Inc.",
}


@pytest.fixture
def client_devices():
    pool, conn = make_mock_pool(rows=[DEVICE_ROW])
    app.dependency_overrides[get_pool] = lambda: pool
    try:
        with patch("api.app.asyncpg.create_pool", new=AsyncMock(return_value=pool)):
            with TestClient(app) as c:
                yield c, conn
    finally:
        app.dependency_overrides.clear()


def test_get_devices_no_filter(client_devices):
    client, _ = client_devices
    response = client.get("/devices")
    assert response.status_code == 200
    assert response.json()[0]["mac"] == "AA:BB:CC:DD:EE:FF"


def test_get_devices_tag_filter(client_devices):
    client, conn = client_devices
    conn.fetch = AsyncMock(return_value=[])
    response = client.get("/devices?tag=known_resident")
    assert response.status_code == 200
    assert response.json() == []


def test_put_label(client_devices):
    client, conn = client_devices
    conn.execute = AsyncMock(return_value="UPDATE 1")
    response = client.put(
        "/devices/AA:BB:CC:DD:EE:FF/label",
        json={"label": "John's iPhone"},
    )
    assert response.status_code == 200
    conn.execute.assert_awaited_once()


def test_put_label_not_found(client_devices):
    client, conn = client_devices
    conn.execute = AsyncMock(return_value="UPDATE 0")
    response = client.put(
        "/devices/00:00:00:00:00:00/label",
        json={"label": "nobody"},
    )
    assert response.status_code == 404


def test_put_tag(client_devices):
    client, conn = client_devices
    conn.execute = AsyncMock(return_value="UPDATE 1")
    response = client.put(
        "/devices/AA:BB:CC:DD:EE:FF/tag",
        json={"tag": "known_resident"},
    )
    assert response.status_code == 200


def test_put_tag_invalid_value(client_devices):
    client, _ = client_devices
    response = client.put(
        "/devices/AA:BB:CC:DD:EE:FF/tag",
        json={"tag": "garbage"},
    )
    assert response.status_code == 422
