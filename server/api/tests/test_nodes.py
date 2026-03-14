from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.app import app, get_pool
from tests.conftest import make_mock_pool

NOW = datetime(2026, 3, 13, 12, 0, 0, tzinfo=UTC)

NODE_ROW = {
    "node_id": "scanner-01",
    "node_type": "wifi",
    "location": "garage",
    "last_seen": NOW,
    "firmware_ver": "1.0.0",
    "lat": 51.5,
    "lon": -0.1,
    "name": None,
}

UPDATED_ROW = {**NODE_ROW, "name": "Garage Scanner", "lat": 51.6, "lon": -0.2}


@pytest.fixture
def client_nodes_list():
    pool, conn = make_mock_pool(rows=[NODE_ROW])
    app.dependency_overrides[get_pool] = lambda: pool
    try:
        with patch("api.app.asyncpg.create_pool", new=AsyncMock(return_value=pool)):
            with TestClient(app) as c:
                yield c, conn
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def client_nodes_patch():
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value=UPDATED_ROW)
    app.dependency_overrides[get_pool] = lambda: pool
    try:
        with patch("api.app.asyncpg.create_pool", new=AsyncMock(return_value=pool)):
            with TestClient(app) as c:
                yield c, conn
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def client_nodes_patch_404():
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value=None)
    app.dependency_overrides[get_pool] = lambda: pool
    try:
        with patch("api.app.asyncpg.create_pool", new=AsyncMock(return_value=pool)):
            with TestClient(app) as c:
                yield c, conn
    finally:
        app.dependency_overrides.clear()


def test_list_nodes_includes_name(client_nodes_list):
    client, _ = client_nodes_list
    resp = client.get("/nodes")
    assert resp.status_code == 200
    assert resp.json()[0]["name"] is None


def test_patch_node_updates_name_and_coords(client_nodes_patch):
    client, conn = client_nodes_patch
    resp = client.patch(
        "/nodes/scanner-01",
        json={"name": "Garage Scanner", "lat": 51.6, "lon": -0.2},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Garage Scanner"
    assert data["lat"] == pytest.approx(51.6)
    assert data["lon"] == pytest.approx(-0.2)


def test_patch_node_partial_coords_rejected(client_nodes_patch):
    # lat without lon must be rejected (coords must come in pairs)
    client, _ = client_nodes_patch
    resp = client.patch("/nodes/scanner-01", json={"name": "X", "lat": 1.0})
    assert resp.status_code == 422


def test_patch_node_name_only_rejected(client_nodes_patch):
    # Coordinates are always required — name-only patch is not supported
    client, _ = client_nodes_patch
    resp = client.patch("/nodes/scanner-01", json={"name": "X"})
    assert resp.status_code == 422


def test_patch_node_trims_and_nulls_whitespace_name(client_nodes_patch):
    client, conn = client_nodes_patch
    resp = client.patch("/nodes/scanner-01", json={"name": "  ", "lat": 51.5, "lon": -0.1})
    assert resp.status_code == 200
    call_args = conn.fetchrow.call_args
    # args[0] = SQL string, args[1] = $1 = name
    assert call_args.args[1] is None


def test_patch_node_404_when_not_found(client_nodes_patch_404):
    client, _ = client_nodes_patch_404
    resp = client.patch(
        "/nodes/nonexistent",
        json={"name": "X", "lat": 1.0, "lon": 2.0},
    )
    assert resp.status_code == 404
