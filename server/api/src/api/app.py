from __future__ import annotations

from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, Request

from api.config import DB_URL


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=10)
    yield
    await app.state.pool.close()


app = FastAPI(title="botanical-sentinel API", version="0.1.0", lifespan=lifespan)


async def get_pool(request: Request) -> asyncpg.Pool:
    """FastAPI dependency that returns the connection pool created by lifespan."""
    return request.app.state.pool


@app.get("/health")
async def health():
    return {"status": "ok"}


from api.routers import nodes as nodes_router  # noqa: E402

app.include_router(nodes_router.router)
