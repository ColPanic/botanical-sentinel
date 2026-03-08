# Milestone 3: FastAPI REST API + SvelteKit Device Registry Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a FastAPI REST service and SvelteKit web UI so the device registry can be
browsed, and devices tagged as known/unknown, from a browser.

**Architecture:** FastAPI service (`server/api/`) exposes REST endpoints backed by asyncpg
queries against TimescaleDB. A WebSocket endpoint (`/live`) receives real-time scan events
via PostgreSQL LISTEN/NOTIFY — mqtt_bridge fires `NOTIFY` after each batch insert. SvelteKit
(`web/`) fetches from FastAPI and renders /nodes, /devices, and /scan pages. OUI vendor
lookup is added to mqtt_bridge so `devices.vendor` is populated on first sight.

**Tech Stack:** FastAPI 0.135.1, uvicorn 0.41.0, asyncpg 0.31.0, Pydantic v2, httpx 0.28.1,
pytest-asyncio 1.3.0, mac-vendor-lookup 0.1.15, SvelteKit (latest), TypeScript, Tailwind CSS,
Docker Compose.

**Note on TDD:** FastAPI endpoints are tested with `TestClient` + mocked asyncpg pool
(unit tests — no DB required). mqtt_bridge changes have pytest unit tests. SvelteKit pages
are verified by running `vite build` cleanly (no browser test runner in M3).

---

### Task 1: commands table + FastAPI service scaffold

**Files:**
- Modify: `server/sql/init.sql`
- Create: `server/api/pyproject.toml`
- Create: `server/api/src/api/__init__.py`
- Create: `server/api/src/api/config.py`

**Step 1: Add commands table to init.sql**

Append to the end of `server/sql/init.sql` (after the retention policy):

```sql
CREATE TABLE IF NOT EXISTS commands (
    id           SERIAL      PRIMARY KEY,
    node_id      TEXT        NOT NULL,
    command_type TEXT        NOT NULL,
    payload      JSONB       NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    executed_at  TIMESTAMPTZ
);
```

**Step 2: Apply the schema change**

The easiest path at this stage — recreate the DB volume (destroys existing scan data):

```bash
cd server
docker compose down -v
docker compose up -d
```

Wait for `server-timescaledb-1` to show `healthy` (`docker compose ps`).

**Step 3: Verify the commands table exists**

```bash
docker compose exec timescaledb psql -U botanical -c "\dt"
```

Expected: `commands`, `devices`, `nodes`, `scan_events` all listed.

**Step 4: Create server/api/pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatchling.build.targets.wheel]
packages = ["src/api"]

[project]
name = "botanical-api"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "fastapi==0.135.1",
    "uvicorn[standard]==0.41.0",
    "asyncpg==0.31.0",
]

[project.optional-dependencies]
dev = [
    "pytest==9.0.2",
    "pytest-asyncio==1.3.0",
    "httpx==0.28.1",
    "ruff==0.15.5",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.ruff]
line-length = 100
src = ["src"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP"]
```

**Step 5: Create empty __init__ files**

```bash
mkdir -p server/api/src/api/routers server/api/tests
touch server/api/src/api/__init__.py
touch server/api/src/api/routers/__init__.py
touch server/api/tests/__init__.py
```

**Step 6: Create server/api/src/api/config.py**

```python
import os


def _require(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise RuntimeError(f"Required environment variable {key!r} is not set")
    return val


DB_URL: str = _require("DB_URL")
```

**Step 7: Set up venv**

```bash
cd server/api
uv venv --python python3.13
uv pip install --python .venv/bin/python -e ".[dev]" --quiet
```

**Step 8: Commit**

```bash
cd ../..
git add server/sql/init.sql server/api/
git commit -m "chore(api): scaffold FastAPI service and add commands table"
```

---

### Task 2: FastAPI app + GET /health with tests

**Files:**
- Create: `server/api/src/api/app.py`
- Create: `server/api/tests/conftest.py`
- Create: `server/api/tests/test_health.py`

**Step 1: Write failing test**

`server/api/tests/test_health.py`:
```python
from fastapi.testclient import TestClient
from api.app import app


def test_health_returns_ok():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

**Step 2: Run to confirm failure**

```bash
cd server/api
.venv/bin/pytest tests/test_health.py -v
```

Expected: `ImportError: No module named 'api.app'`

**Step 3: Create conftest.py**

`server/api/tests/conftest.py`:
```python
from unittest.mock import AsyncMock, MagicMock
import pytest
from api.app import get_pool


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


@pytest.fixture
def mock_pool():
    return make_mock_pool()
```

**Step 4: Implement app.py**

`server/api/src/api/app.py`:
```python
from __future__ import annotations

from contextlib import asynccontextmanager

import asyncpg
from fastapi import Depends, FastAPI, Request

from api.config import DB_URL


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=10)
    yield
    await app.state.pool.close()


app = FastAPI(title="botanical-sentinel API", version="0.1.0", lifespan=lifespan)


async def get_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pool


@app.get("/health")
async def health():
    return {"status": "ok"}
```

**Step 5: Run test — must pass**

```bash
.venv/bin/pytest tests/test_health.py -v
```

Expected: `PASSED`

**Step 6: Lint**

```bash
.venv/bin/ruff check src/ tests/
```

Expected: clean.

**Step 7: Commit**

```bash
cd ../..
git add server/api/src/api/app.py server/api/tests/
git commit -m "feat(api): add FastAPI app skeleton and health endpoint"
```

---

### Task 3: GET /nodes

**Files:**
- Create: `server/api/src/api/models.py`
- Create: `server/api/src/api/routers/nodes.py`
- Create: `server/api/tests/test_nodes.py`
- Modify: `server/api/src/api/app.py`

**Step 1: Write failing tests**

`server/api/tests/test_nodes.py`:
```python
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from api.app import app, get_pool
from tests.conftest import make_mock_pool


NOW = datetime(2026, 3, 8, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def client_with_nodes():
    pool, conn = make_mock_pool(rows=[
        {
            "node_id": "scanner-01",
            "node_type": "esp32_scanner",
            "location": None,
            "last_seen": NOW,
            "firmware_ver": "0.2.0",
        }
    ])
    app.dependency_overrides[get_pool] = lambda: pool
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
```

**Step 2: Run tests to confirm failure**

```bash
.venv/bin/pytest tests/test_nodes.py -v
```

Expected: `ImportError` or 404.

**Step 3: Create models.py**

`server/api/src/api/models.py`:
```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class NodeResponse(BaseModel):
    node_id: str
    node_type: str
    location: str | None
    last_seen: datetime
    firmware_ver: str


class DeviceResponse(BaseModel):
    mac: str
    device_type: str
    label: str | None
    tag: str
    first_seen: datetime
    last_seen: datetime
    vendor: str | None


class ScanEventResponse(BaseModel):
    time: datetime
    node_id: str
    mac: str
    rssi: int
    scan_type: str
    ssid: str | None


class LabelUpdate(BaseModel):
    label: str


class TagUpdate(BaseModel):
    tag: str
```

**Step 4: Create routers/nodes.py**

`server/api/src/api/routers/nodes.py`:
```python
from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends

from api.app import get_pool
from api.models import NodeResponse

router = APIRouter(prefix="/nodes", tags=["nodes"])


@router.get("", response_model=list[NodeResponse])
async def list_nodes(pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT node_id, node_type, location, last_seen, firmware_ver "
            "FROM nodes ORDER BY last_seen DESC"
        )
    return [dict(r) for r in rows]
```

**Step 5: Register router in app.py**

Add to the bottom of `server/api/src/api/app.py`:

```python
from api.routers import nodes

app.include_router(nodes.router)
```

**Step 6: Run tests — must pass**

```bash
.venv/bin/pytest tests/test_nodes.py -v
```

Expected: 2 PASSED.

**Step 7: Commit**

```bash
cd ../..
git add server/api/src/ server/api/tests/test_nodes.py
git commit -m "feat(api): add GET /nodes endpoint"
```

---

### Task 4: GET /devices + PUT /devices/{mac}/label + PUT /devices/{mac}/tag

**Files:**
- Create: `server/api/src/api/routers/devices.py`
- Create: `server/api/tests/test_devices.py`
- Modify: `server/api/src/api/app.py`

**Step 1: Write failing tests**

`server/api/tests/test_devices.py`:
```python
from datetime import UTC, datetime
from unittest.mock import AsyncMock

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
    with TestClient(app) as c:
        yield c, conn
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
```

**Step 2: Run to confirm failure**

```bash
.venv/bin/pytest tests/test_devices.py -v
```

Expected: ImportError or 404s.

**Step 3: Create routers/devices.py**

`server/api/src/api/routers/devices.py`:
```python
from __future__ import annotations

from typing import Literal

import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from api.app import get_pool
from api.models import DeviceResponse, LabelUpdate, TagUpdate

router = APIRouter(prefix="/devices", tags=["devices"])

VALID_TAGS = {"known_resident", "known_vehicle", "unknown", "ignored"}


@router.get("", response_model=list[DeviceResponse])
async def list_devices(
    tag: str | None = None,
    pool: asyncpg.Pool = Depends(get_pool),
):
    async with pool.acquire() as conn:
        if tag:
            rows = await conn.fetch(
                "SELECT mac, device_type, label, tag, first_seen, last_seen, vendor "
                "FROM devices WHERE tag = $1 ORDER BY last_seen DESC",
                tag,
            )
        else:
            rows = await conn.fetch(
                "SELECT mac, device_type, label, tag, first_seen, last_seen, vendor "
                "FROM devices ORDER BY tag = 'unknown' DESC, last_seen DESC"
            )
    return [dict(r) for r in rows]


@router.put("/{mac}/label")
async def set_label(
    mac: str,
    body: LabelUpdate,
    pool: asyncpg.Pool = Depends(get_pool),
):
    async with pool.acquire() as conn:
        status = await conn.execute(
            "UPDATE devices SET label = $1 WHERE mac = $2",
            body.label,
            mac.upper(),
        )
    if status == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Device not found")
    return {"mac": mac, "label": body.label}


@router.put("/{mac}/tag")
async def set_tag(
    mac: str,
    body: TagUpdate,
    pool: asyncpg.Pool = Depends(get_pool),
):
    if body.tag not in VALID_TAGS:
        raise HTTPException(
            status_code=422,
            detail=f"tag must be one of: {', '.join(sorted(VALID_TAGS))}",
        )
    async with pool.acquire() as conn:
        status = await conn.execute(
            "UPDATE devices SET tag = $1 WHERE mac = $2",
            body.tag,
            mac.upper(),
        )
    if status == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Device not found")
    return {"mac": mac, "tag": body.tag}
```

**Step 4: Register router in app.py**

Add below the nodes import:

```python
from api.routers import devices

app.include_router(devices.router)
```

**Step 5: Run tests — all must pass**

```bash
.venv/bin/pytest tests/test_devices.py -v
```

Expected: 6 PASSED.

**Step 6: Lint**

```bash
.venv/bin/ruff check src/ tests/
```

**Step 7: Commit**

```bash
cd ../..
git add server/api/
git commit -m "feat(api): add GET /devices and PUT label/tag endpoints"
```

---

### Task 5: GET /scan/recent + GET /scan/{node_id}/recent

**Files:**
- Create: `server/api/src/api/routers/scan.py`
- Create: `server/api/tests/test_scan.py`
- Modify: `server/api/src/api/app.py`

**Step 1: Write failing tests**

`server/api/tests/test_scan.py`:
```python
from datetime import UTC, datetime
from unittest.mock import AsyncMock

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
    with TestClient(app) as c:
        yield c, conn
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
    assert "100" in str(call_args) or 100 in call_args.args or 100 in (call_args.kwargs or {}).values()


def test_get_recent_for_node(client_scan):
    client, _ = client_scan
    response = client.get("/scan/scanner-01/recent")
    assert response.status_code == 200
    assert response.json()[0]["node_id"] == "scanner-01"


def test_get_recent_custom_limit(client_scan):
    client, _ = client_scan
    response = client.get("/scan/recent?limit=50")
    assert response.status_code == 200
```

**Step 2: Run to confirm failure**

```bash
.venv/bin/pytest tests/test_scan.py -v
```

Expected: 404s (no router registered).

**Step 3: Create routers/scan.py**

`server/api/src/api/routers/scan.py`:
```python
from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends

from api.app import get_pool
from api.models import ScanEventResponse

router = APIRouter(prefix="/scan", tags=["scan"])


@router.get("/recent", response_model=list[ScanEventResponse])
async def recent_all(
    limit: int = 100,
    pool: asyncpg.Pool = Depends(get_pool),
):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT time, node_id, mac, rssi, scan_type, ssid "
            "FROM scan_events ORDER BY time DESC LIMIT $1",
            limit,
        )
    return [dict(r) for r in rows]


@router.get("/{node_id}/recent", response_model=list[ScanEventResponse])
async def recent_for_node(
    node_id: str,
    limit: int = 100,
    pool: asyncpg.Pool = Depends(get_pool),
):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT time, node_id, mac, rssi, scan_type, ssid "
            "FROM scan_events WHERE node_id = $1 ORDER BY time DESC LIMIT $2",
            node_id,
            limit,
        )
    return [dict(r) for r in rows]
```

**Step 4: Register router in app.py**

```python
from api.routers import scan

app.include_router(scan.router)
```

**Step 5: Run tests — all must pass**

```bash
.venv/bin/pytest tests/test_scan.py -v
```

Expected: 4 PASSED.

**Step 6: Run full test suite**

```bash
.venv/bin/pytest -v
```

Expected: all tests PASSED.

**Step 7: Commit**

```bash
cd ../..
git add server/api/
git commit -m "feat(api): add GET /scan/recent and GET /scan/{node_id}/recent"
```

---

### Task 6: WebSocket /live + mqtt_bridge NOTIFY

**Files:**
- Create: `server/api/src/api/routers/live.py`
- Modify: `server/api/src/api/app.py`
- Modify: `server/mqtt_bridge/src/mqtt_bridge/db.py`
- Modify: `server/mqtt_bridge/src/mqtt_bridge/main.py` (pass pool to insert fn)

**Step 1: Understand the approach**

- mqtt_bridge calls `pg_notify('scan_events', json_payload)` after each batch insert
- API has a background task that opens a dedicated asyncpg connection and `LISTEN`s for
  `scan_events` notifications
- When a notification arrives, the payload is broadcast to all active WebSocket connections
- WebSocket clients get a JSON message: `{"node_id": "...", "topic": "wifi", "count": 14}`

**Step 2: Update mqtt_bridge/db.py — add notify call**

In `insert_scan_events`, after the `executemany`, add a NOTIFY:

```python
import json

async def insert_scan_events(pool: asyncpg.Pool, events: list[ScanEvent]) -> None:
    if not events:
        return
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO scan_events (time, node_id, mac, rssi, scan_type, ssid)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            [
                (e.time, e.node_id, e.mac, e.rssi, e.scan_type, e.ssid)
                for e in events
            ],
        )
        payload = json.dumps({
            "node_id": events[0].node_id,
            "scan_type": events[0].scan_type,
            "count": len(events),
        })
        await conn.execute("SELECT pg_notify('scan_events', $1)", payload)
```

**Step 3: Add NOTIFY test to test_handler.py (mqtt_bridge)**

In `server/mqtt_bridge/tests/test_handler.py`, the existing tests cover parsing. The NOTIFY
call is in db.py which requires a real DB — skip unit testing it; the integration verify
(step 8 below) covers it.

**Step 4: Lint mqtt_bridge after change**

```bash
cd server/mqtt_bridge
.venv/bin/ruff check src/
```

**Step 5: Create routers/live.py (WebSocket + LISTEN background task)**

`server/api/src/api/routers/live.py`:
```python
from __future__ import annotations

import asyncio
import json
import logging

import asyncpg
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.config import DB_URL

log = logging.getLogger(__name__)
router = APIRouter(tags=["live"])

# Active WebSocket connections
_connections: set[WebSocket] = set()


async def _broadcast(message: str) -> None:
    dead = set()
    for ws in _connections:
        try:
            await ws.send_text(message)
        except Exception:
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

            # Keep alive until connection drops
            while not conn.is_closed():
                await asyncio.sleep(5)

            await conn.remove_listener("scan_events", on_notify)
            await conn.close()
        except Exception as exc:
            log.warning("LISTEN loop error: %s — reconnecting in 5s", exc)
            await asyncio.sleep(5)


@router.websocket("/live")
async def live(ws: WebSocket):
    await ws.accept()
    _connections.add(ws)
    try:
        while True:
            await ws.receive_text()   # keep connection open; client sends nothing
    except WebSocketDisconnect:
        _connections.discard(ws)
```

**Step 6: Start LISTEN background task in lifespan**

In `server/api/src/api/app.py`, update the lifespan:

```python
import asyncio
from api.routers.live import _listen_loop

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=10)
    task = asyncio.create_task(_listen_loop())
    yield
    task.cancel()
    await app.state.pool.close()
```

And register the router:

```python
from api.routers import live

app.include_router(live.router)
```

**Step 7: Lint**

```bash
cd server/api
.venv/bin/ruff check src/ tests/
```

**Step 8: Commit**

```bash
cd ../..
git add server/api/src/ server/mqtt_bridge/src/
git commit -m "feat(api): add WebSocket /live endpoint with pg LISTEN/NOTIFY"
```

---

### Task 7: OUI vendor lookup in mqtt_bridge

**Files:**
- Modify: `server/mqtt_bridge/pyproject.toml`
- Modify: `server/mqtt_bridge/src/mqtt_bridge/db.py`
- Modify: `server/mqtt_bridge/tests/test_handler.py`

**Step 1: Add mac-vendor-lookup to pyproject.toml**

In `server/mqtt_bridge/pyproject.toml`, add to `dependencies`:

```toml
"mac-vendor-lookup==0.1.15",
```

**Step 2: Reinstall deps**

```bash
cd server/mqtt_bridge
uv pip install --python .venv/bin/python -e ".[dev]" --quiet
```

**Step 3: Write failing test**

Add to `server/mqtt_bridge/tests/test_handler.py`:

```python
from mqtt_bridge.db import lookup_vendor


def test_lookup_vendor_known_mac():
    # Apple OUI — should resolve to something non-empty
    result = lookup_vendor("AC:DE:48:00:11:22")
    assert result is not None
    assert len(result) > 0


def test_lookup_vendor_unknown_mac():
    # Locally administered address — no OUI match
    result = lookup_vendor("02:00:00:00:00:00")
    assert result is None
```

**Step 4: Run to confirm failure**

```bash
.venv/bin/pytest tests/test_handler.py -v -k "vendor"
```

Expected: `ImportError: cannot import name 'lookup_vendor'`

**Step 5: Add lookup_vendor to db.py**

At the top of `server/mqtt_bridge/src/mqtt_bridge/db.py`, add:

```python
from mac_vendor_lookup import MacLookup, VendorNotFoundError

_mac_lookup = MacLookup()


def lookup_vendor(mac: str) -> str | None:
    """Return OUI vendor string or None if not found."""
    try:
        return _mac_lookup.lookup(mac)
    except (VendorNotFoundError, KeyError, ValueError):
        return None
```

Then in `upsert_devices`, populate `vendor` on insert:

```python
async def upsert_devices(pool: asyncpg.Pool, events: list[ScanEvent]) -> None:
    async with pool.acquire() as conn:
        for event in events:
            vendor = lookup_vendor(event.mac)
            await conn.execute(
                """
                INSERT INTO devices (mac, device_type, first_seen, last_seen, tag, vendor)
                VALUES ($1, $2, now(), now(), 'unknown', $3)
                ON CONFLICT (mac) DO UPDATE
                    SET last_seen = now()
                """,
                event.mac,
                event.scan_type,
                vendor,
            )
```

**Step 6: Run tests — all must pass**

```bash
.venv/bin/pytest -v
```

Expected: 11 PASSED (9 existing + 2 new).

**Step 7: Lint**

```bash
.venv/bin/ruff check src/ tests/
```

**Step 8: Commit**

```bash
cd ../..
git add server/mqtt_bridge/
git commit -m "feat(mqtt-bridge): add OUI vendor lookup on device first-seen"
```

---

### Task 8: API Dockerfile + add api to docker-compose

**Files:**
- Create: `server/api/Dockerfile`
- Modify: `server/docker-compose.yml`

**Step 1: Create Dockerfile**

`server/api/Dockerfile`:
```dockerfile
FROM python:3.13-slim
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml .
COPY src/ src/
RUN uv pip install --system --no-cache .
CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Step 2: Add api service to docker-compose.yml**

In `server/docker-compose.yml`, add under `services:` (after `mqtt_bridge`):

```yaml
  api:
    build: ./api
    environment:
      DB_URL: postgresql://botanical:${DB_PASSWORD}@timescaledb:5432/botanical
    ports:
      - "8000:8000"
    depends_on:
      timescaledb:
        condition: service_healthy
    restart: unless-stopped
```

**Step 3: Rebuild and verify**

```bash
cd server
docker compose up -d --build api
```

**Step 4: Verify health endpoint**

```bash
curl http://localhost:8000/health
```

Expected: `{"status":"ok"}`

**Step 5: Verify nodes endpoint returns live data**

```bash
curl http://localhost:8000/nodes | python3 -m json.tool
```

Expected: JSON array with `tft-scanner-01`.

**Step 6: Verify devices returns with vendor populated**

After the next ESP32 scan cycle (up to 30s):

```bash
curl "http://localhost:8000/devices" | python3 -m json.tool | grep vendor
```

Expected: some entries with non-null `vendor` values.

**Step 7: Commit**

```bash
cd ..
git add server/api/Dockerfile server/docker-compose.yml
git commit -m "feat(server): add api service to Docker Compose stack"
```

---

### Task 9: SvelteKit project scaffold + /nodes page

**Files:**
- Create: `web/` (entire SvelteKit project)
- Create: `web/src/lib/api.ts`
- Create: `web/src/routes/nodes/+page.svelte`
- Create: `web/src/routes/nodes/+page.server.ts`

**Step 1: Create SvelteKit project**

```bash
cd /path/to/esp_bot   # repo root
npx sv create web --template minimal --types ts
```

When prompted: select TypeScript, no additional add-ons initially.

```bash
cd web
npm install
```

**Step 2: Add Tailwind CSS**

```bash
npx sv add tailwindcss
```

Follow prompts (accept defaults).

**Step 3: Set PUBLIC_API_URL**

Create `web/.env`:
```
PUBLIC_API_URL=http://localhost:8000
```

Create `web/.env.example`:
```
PUBLIC_API_URL=http://localhost:8000
```

Add to root `.gitignore`: `web/.env`

**Step 4: Create API client**

`web/src/lib/api.ts`:
```typescript
import { env } from "$env/dynamic/public";

const BASE = env.PUBLIC_API_URL ?? "http://localhost:8000";

export async function fetchNodes() {
  const res = await fetch(`${BASE}/nodes`);
  if (!res.ok) throw new Error(`GET /nodes failed: ${res.status}`);
  return res.json();
}

export async function fetchDevices(tag?: string) {
  const url = tag ? `${BASE}/devices?tag=${tag}` : `${BASE}/devices`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`GET /devices failed: ${res.status}`);
  return res.json();
}

export async function fetchRecentScan(nodeId?: string, limit = 100) {
  const path = nodeId ? `/scan/${nodeId}/recent` : "/scan/recent";
  const res = await fetch(`${BASE}${path}?limit=${limit}`);
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
  return res.json();
}

export async function setDeviceLabel(mac: string, label: string) {
  const res = await fetch(`${BASE}/devices/${mac}/label`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label }),
  });
  if (!res.ok) throw new Error(`PUT /devices/${mac}/label failed: ${res.status}`);
  return res.json();
}

export async function setDeviceTag(mac: string, tag: string) {
  const res = await fetch(`${BASE}/devices/${mac}/tag`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tag }),
  });
  if (!res.ok) throw new Error(`PUT /devices/${mac}/tag failed: ${res.status}`);
  return res.json();
}

export function liveWebSocket(onMessage: (data: unknown) => void): WebSocket {
  const ws = new WebSocket(`${BASE.replace("http", "ws")}/live`);
  ws.onmessage = (e) => onMessage(JSON.parse(e.data));
  return ws;
}
```

**Step 5: Create /nodes server load**

`web/src/routes/nodes/+page.server.ts`:
```typescript
import { fetchNodes } from "$lib/api";
import type { PageServerLoad } from "./$types";

export const load: PageServerLoad = async () => {
  const nodes = await fetchNodes();
  return { nodes };
};
```

**Step 6: Create /nodes page**

`web/src/routes/nodes/+page.svelte`:
```svelte
<script lang="ts">
  import type { PageData } from "./$types";

  export let data: PageData;

  function staleness(lastSeen: string): string {
    const diff = (Date.now() - new Date(lastSeen).getTime()) / 1000;
    if (diff < 60) return "text-green-400";
    if (diff < 300) return "text-yellow-400";
    return "text-red-400";
  }

  function relativeTime(ts: string): string {
    const diff = Math.round((Date.now() - new Date(ts).getTime()) / 1000);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
    return `${Math.round(diff / 3600)}h ago`;
  }
</script>

<svelte:head><title>Nodes — botanical-sentinel</title></svelte:head>

<div class="p-6">
  <h1 class="text-xl font-semibold mb-4">Nodes</h1>
  <table class="w-full text-sm border-collapse">
    <thead>
      <tr class="text-left border-b border-zinc-700">
        <th class="py-2 pr-4">Node ID</th>
        <th class="py-2 pr-4">Type</th>
        <th class="py-2 pr-4">Location</th>
        <th class="py-2 pr-4">Firmware</th>
        <th class="py-2">Last Seen</th>
      </tr>
    </thead>
    <tbody>
      {#each data.nodes as node}
        <tr class="border-b border-zinc-800">
          <td class="py-2 pr-4 font-mono">{node.node_id}</td>
          <td class="py-2 pr-4 text-zinc-400">{node.node_type}</td>
          <td class="py-2 pr-4 text-zinc-400">{node.location ?? "—"}</td>
          <td class="py-2 pr-4 text-zinc-400">{node.firmware_ver}</td>
          <td class="py-2 {staleness(node.last_seen)}">{relativeTime(node.last_seen)}</td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>
```

**Step 7: Verify build passes**

```bash
cd web
npm run build
```

Expected: clean build with no TypeScript errors.

**Step 8: Commit**

```bash
cd ..
git add web/
git commit -m "feat(web): scaffold SvelteKit app and add /nodes page"
```

---

### Task 10: /devices page with inline label and tag editing

**Files:**
- Create: `web/src/routes/devices/+page.server.ts`
- Create: `web/src/routes/devices/+page.svelte`

**Step 1: Create /devices server load + form actions**

`web/src/routes/devices/+page.server.ts`:
```typescript
import { fetchDevices, setDeviceLabel, setDeviceTag } from "$lib/api";
import type { Actions, PageServerLoad } from "./$types";

export const load: PageServerLoad = async ({ url }) => {
  const tag = url.searchParams.get("tag") ?? undefined;
  const devices = await fetchDevices(tag);
  return { devices, activeTag: tag };
};

export const actions: Actions = {
  label: async ({ request }) => {
    const form = await request.formData();
    const mac = String(form.get("mac"));
    const label = String(form.get("label"));
    await setDeviceLabel(mac, label);
    return { success: true };
  },
  tag: async ({ request }) => {
    const form = await request.formData();
    const mac = String(form.get("mac"));
    const tag = String(form.get("tag"));
    await setDeviceTag(mac, tag);
    return { success: true };
  },
};
```

**Step 2: Create /devices page**

`web/src/routes/devices/+page.svelte`:
```svelte
<script lang="ts">
  import { enhance } from "$app/forms";
  import type { PageData } from "./$types";

  export let data: PageData;

  const TAGS = ["unknown", "known_resident", "known_vehicle", "ignored"];

  const TAG_COLOR: Record<string, string> = {
    unknown: "text-yellow-400",
    known_resident: "text-green-400",
    known_vehicle: "text-blue-400",
    ignored: "text-zinc-500",
  };
</script>

<svelte:head><title>Devices — botanical-sentinel</title></svelte:head>

<div class="p-6">
  <div class="flex items-center gap-4 mb-4">
    <h1 class="text-xl font-semibold">Devices</h1>
    <div class="flex gap-2 text-sm">
      <a href="/devices" class="px-2 py-1 rounded {!data.activeTag ? 'bg-zinc-700' : 'text-zinc-400 hover:text-white'}">All</a>
      {#each TAGS as tag}
        <a href="/devices?tag={tag}" class="px-2 py-1 rounded {data.activeTag === tag ? 'bg-zinc-700' : 'text-zinc-400 hover:text-white'}">{tag}</a>
      {/each}
    </div>
  </div>

  <table class="w-full text-sm border-collapse">
    <thead>
      <tr class="text-left border-b border-zinc-700">
        <th class="py-2 pr-4">MAC</th>
        <th class="py-2 pr-4">Vendor</th>
        <th class="py-2 pr-4">Type</th>
        <th class="py-2 pr-4">Label</th>
        <th class="py-2 pr-4">Tag</th>
        <th class="py-2">Last Seen</th>
      </tr>
    </thead>
    <tbody>
      {#each data.devices as device}
        <tr class="border-b border-zinc-800">
          <td class="py-2 pr-4 font-mono text-xs">{device.mac}</td>
          <td class="py-2 pr-4 text-zinc-400 text-xs">{device.vendor ?? "—"}</td>
          <td class="py-2 pr-4 text-zinc-400">{device.device_type}</td>

          <td class="py-2 pr-4">
            <form method="POST" action="?/label" use:enhance class="flex gap-1">
              <input type="hidden" name="mac" value={device.mac} />
              <input
                type="text"
                name="label"
                value={device.label ?? ""}
                placeholder="add label"
                class="bg-transparent border-b border-zinc-600 focus:border-zinc-300 outline-none text-sm w-32"
              />
              <button type="submit" class="text-xs text-zinc-500 hover:text-white">✓</button>
            </form>
          </td>

          <td class="py-2 pr-4">
            <form method="POST" action="?/tag" use:enhance>
              <input type="hidden" name="mac" value={device.mac} />
              <select
                name="tag"
                onchange="this.form.submit()"
                class="bg-zinc-800 border border-zinc-600 rounded px-1 py-0.5 text-xs {TAG_COLOR[device.tag]}"
              >
                {#each TAGS as tag}
                  <option value={tag} selected={device.tag === tag}>{tag}</option>
                {/each}
              </select>
            </form>
          </td>

          <td class="py-2 text-zinc-400 text-xs">
            {new Date(device.last_seen).toLocaleString()}
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>
```

**Step 3: Verify build**

```bash
cd web && npm run build
```

Expected: clean build.

**Step 4: Commit**

```bash
cd ..
git add web/src/routes/devices/
git commit -m "feat(web): add /devices page with inline label and tag editing"
```

---

### Task 11: /scan live page

**Files:**
- Create: `web/src/routes/scan/+page.svelte`

**Step 1: Create /scan page with WebSocket feed**

`web/src/routes/scan/+page.svelte`:
```svelte
<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { liveWebSocket } from "$lib/api";

  type ScanEvent = {
    node_id: string;
    scan_type: string;
    count: number;
    time: string;
  };

  let events: ScanEvent[] = [];
  let connected = false;
  let ws: WebSocket;

  onMount(() => {
    ws = liveWebSocket((data) => {
      events = [
        { ...(data as Omit<ScanEvent, "time">), time: new Date().toISOString() },
        ...events.slice(0, 99),   // keep last 100
      ];
    });
    ws.onopen = () => (connected = true);
    ws.onclose = () => (connected = false);
    ws.onerror = () => (connected = false);
  });

  onDestroy(() => ws?.close());
</script>

<svelte:head><title>Live Scan — botanical-sentinel</title></svelte:head>

<div class="p-6">
  <div class="flex items-center gap-3 mb-4">
    <h1 class="text-xl font-semibold">Live Scan</h1>
    <span class="text-xs px-2 py-0.5 rounded-full {connected ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300'}">
      {connected ? "connected" : "disconnected"}
    </span>
  </div>

  {#if events.length === 0}
    <p class="text-zinc-500 text-sm">Waiting for scan events…</p>
  {:else}
    <table class="w-full text-sm border-collapse">
      <thead>
        <tr class="text-left border-b border-zinc-700">
          <th class="py-2 pr-4">Time</th>
          <th class="py-2 pr-4">Node</th>
          <th class="py-2 pr-4">Type</th>
          <th class="py-2">Count</th>
        </tr>
      </thead>
      <tbody>
        {#each events as event}
          <tr class="border-b border-zinc-800">
            <td class="py-1 pr-4 text-zinc-400 font-mono text-xs">
              {new Date(event.time).toLocaleTimeString()}
            </td>
            <td class="py-1 pr-4 font-mono">{event.node_id}</td>
            <td class="py-1 pr-4 {event.scan_type === 'wifi' ? 'text-cyan-400' : 'text-green-400'}">
              {event.scan_type}
            </td>
            <td class="py-1">{event.count}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</div>
```

**Step 2: Add nav to layout**

In `web/src/routes/+layout.svelte` (create if it doesn't exist):

```svelte
<script lang="ts">
  import "../app.css";
</script>

<div class="min-h-screen bg-zinc-900 text-zinc-100 font-sans">
  <nav class="px-6 py-3 border-b border-zinc-800 flex gap-6 text-sm">
    <a href="/" class="font-semibold text-white">botanical-sentinel</a>
    <a href="/nodes" class="text-zinc-400 hover:text-white">Nodes</a>
    <a href="/devices" class="text-zinc-400 hover:text-white">Devices</a>
    <a href="/scan" class="text-zinc-400 hover:text-white">Live Scan</a>
  </nav>
  <slot />
</div>
```

**Step 3: Verify build**

```bash
cd web && npm run build
```

Expected: clean build.

**Step 4: Smoke test in dev mode**

```bash
npm run dev
```

Open `http://localhost:5173/scan`. The status badge should show "connected" once the API
is running and serving WebSocket connections. ESP32 scan events should appear in the table
within 30 seconds.

**Step 5: Commit**

```bash
cd ..
git add web/src/routes/scan/ web/src/routes/+layout.svelte
git commit -m "feat(web): add /scan live page with WebSocket feed"
```

---

### Task 12: CI workflows

**Files:**
- Create: `.github/workflows/server.yml`
- Create: `.github/workflows/firmware.yml`
- Create: `.github/workflows/web.yml`

**Step 1: Create server.yml (ruff + pytest for api and mqtt_bridge)**

`.github/workflows/server.yml`:
```yaml
name: server

on:
  push:
    paths:
      - "server/**"
      - ".github/workflows/server.yml"
  pull_request:
    paths:
      - "server/**"

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2

      - name: Set up Python
        uses: actions/setup-python@0b93645e9fea7318ecaed2b359559ac225c90a2f  # v5.3.0
        with:
          python-version: "3.13"

      - name: Install uv
        run: pip install uv

      - name: Test mqtt_bridge
        working-directory: server/mqtt_bridge
        run: |
          uv venv --python python3.13
          uv pip install --python .venv/bin/python -e ".[dev]" --quiet
          .venv/bin/ruff check src/ tests/
          .venv/bin/pytest -q

      - name: Test api
        working-directory: server/api
        run: |
          uv venv --python python3.13
          uv pip install --python .venv/bin/python -e ".[dev]" --quiet
          .venv/bin/ruff check src/ tests/
          .venv/bin/pytest -q
```

**Step 2: Create firmware.yml**

`.github/workflows/firmware.yml`:
```yaml
name: firmware

on:
  push:
    paths:
      - "nodes/esp32-scanner/**"
      - ".github/workflows/firmware.yml"
  pull_request:
    paths:
      - "nodes/esp32-scanner/**"

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2

      - name: Set up Python
        uses: actions/setup-python@0b93645e9fea7318ecaed2b359559ac225c90a2f  # v5.3.0
        with:
          python-version: "3.11"

      - name: Install PlatformIO
        run: pip install platformio

      - name: Create config.h from example
        run: cp nodes/esp32-scanner/src/config.h.example nodes/esp32-scanner/src/config.h

      - name: Compile firmware
        run: pio run --project-dir nodes/esp32-scanner
```

**Step 3: Create web.yml**

`.github/workflows/web.yml`:
```yaml
name: web

on:
  push:
    paths:
      - "web/**"
      - ".github/workflows/web.yml"
  pull_request:
    paths:
      - "web/**"

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2

      - name: Set up Node
        uses: actions/setup-node@39370e3970a6d050c480ffad4ff0ed4d3fdee5af  # v4.1.0
        with:
          node-version: "22"
          cache: "npm"
          cache-dependency-path: web/package-lock.json

      - name: Install dependencies
        working-directory: web
        run: npm ci

      - name: Build
        working-directory: web
        run: npm run build
        env:
          PUBLIC_API_URL: http://localhost:8000
```

**Step 4: Verify action SHA hashes are current**

```bash
# Check current SHA for actions used above
gh api repos/actions/checkout/git/refs/tags/v4.2.2 --jq '.object.sha'
gh api repos/actions/setup-python/git/refs/tags/v5.3.0 --jq '.object.sha'
gh api repos/actions/setup-node/git/refs/tags/v4.1.0 --jq '.object.sha'
```

Update SHA pins in the workflow files if they differ from the output.

**Step 5: Commit**

```bash
git add .github/
git commit -m "ci: add server, firmware, and web GitHub Actions workflows"
```

---

## Summary

After all tasks complete:

| What | State |
|------|-------|
| TimescaleDB | `commands` table added |
| FastAPI (`server/api/`) | GET /nodes, GET /devices, PUT label/tag, GET /scan/recent, WS /live |
| mqtt_bridge | pg_notify after insert, OUI vendor lookup on first-seen |
| Docker Compose | api service added (port 8000) |
| SvelteKit (`web/`) | /nodes, /devices (inline editing), /scan (live WebSocket) |
| CI | server tests, firmware compile check, web build |

**Next milestone:** Pi camera node, LoRa gateway, PIR → camera trigger pipeline.
