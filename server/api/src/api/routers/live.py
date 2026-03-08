from __future__ import annotations

import asyncio
import logging

import asyncpg
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.config import DB_URL

log = logging.getLogger(__name__)
router = APIRouter(tags=["live"])

# Active WebSocket connections
_connections: set[WebSocket] = set()


async def _broadcast(message: str) -> None:
    """Send message to all connected WebSocket clients, removing dead connections."""
    dead = set()
    for ws in _connections:
        try:
            await ws.send_text(message)
        except Exception as exc:
            log.debug("WebSocket send failed, removing dead connection: %s", exc)
            dead.add(ws)
    _connections.difference_update(dead)


async def _listen_loop() -> None:
    """Background task: LISTEN for pg_notify and broadcast to WebSocket clients."""
    while True:
        try:
            conn = await asyncpg.connect(DB_URL)
            log.info("WebSocket LISTEN task connected to DB")

            async def on_notify(connection, pid, channel, payload):
                await _broadcast(payload)

            await conn.add_listener("scan_events", on_notify)

            # Poll for connection loss — notifications arrive via asyncpg's callback,
            # not via this loop.
            while not conn.is_closed():
                await asyncio.sleep(5)
        except Exception as exc:
            log.warning("LISTEN loop error: %s — reconnecting in 5s", exc)
            await asyncio.sleep(5)


@router.websocket("/live")
async def live(ws: WebSocket):
    """Accept WebSocket connections and keep them alive to receive scan event broadcasts."""
    await ws.accept()
    _connections.add(ws)
    try:
        while True:
            await ws.receive_text()  # keep connection open; client sends nothing
    except WebSocketDisconnect:
        _connections.discard(ws)
