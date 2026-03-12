from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, Request

from api.config import DB_URL
from api.routers.live import _listen_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=10)
    task = asyncio.create_task(_listen_loop())
    yield
    task.cancel()
    await app.state.pool.close()


app = FastAPI(title="botanical-sentinel API", version="0.1.0", lifespan=lifespan)


async def get_pool(request: Request) -> asyncpg.Pool:
    """FastAPI dependency that returns the connection pool created by lifespan."""
    return request.app.state.pool


@app.get("/health")
async def health():
    return {"status": "ok"}


from api.routers import devices as devices_router  # noqa: E402
from api.routers import live as live_router  # noqa: E402
from api.routers import nodes as nodes_router  # noqa: E402
from api.routers import positions as positions_router  # noqa: E402
from api.routers import scan as scan_router  # noqa: E402

app.include_router(nodes_router.router)
app.include_router(devices_router.router)
app.include_router(scan_router.router)
app.include_router(live_router.router)
app.include_router(positions_router.router)
