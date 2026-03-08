from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from api.app import app
from tests.conftest import make_mock_pool


def test_health_returns_ok():
    pool, _ = make_mock_pool()
    with patch("api.app.asyncpg.create_pool", new=AsyncMock(return_value=pool)):
        with TestClient(app) as client:
            response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
