from unittest.mock import AsyncMock, MagicMock


def make_mock_pool(rows: list[dict] | None = None) -> tuple:
    """Return (pool, conn) where conn.fetch / fetchrow / execute are mocked."""
    pool = MagicMock()
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=rows or [])
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock(return_value="UPDATE 1")
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=cm)
    return pool, conn
