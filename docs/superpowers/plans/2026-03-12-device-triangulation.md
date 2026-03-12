# Device Triangulation & Position Tracking Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Track detected WiFi/BLE devices across a property by combining RSSI readings from multiple scanner nodes into estimated GPS positions, displayed on a live Leaflet map.

**Architecture:** A background estimator task in mqtt_bridge runs every 30 s, queries the last 90 s of scan_events (which now carry the node's GPS coordinates at scan time), computes weighted-centroid positions, writes them to a `position_estimates` TimescaleDB hypertable, and broadcasts updates to the FastAPI WebSocket clients via pg_notify. A new SvelteKit `/map` page renders node pins and device circles using Leaflet.

**Tech Stack:** TimescaleDB (hypertable + pg_notify), asyncpg, FastAPI, Pydantic v2, asyncio, SvelteKit 2, Leaflet 1.9, TailwindCSS.

**Spec:** `docs/superpowers/specs/2026-03-12-device-triangulation-design.md`

---

## File Map

### Created
| File | Purpose |
|------|---------|
| `server/api/src/api/routers/positions.py` | Three new position endpoints |
| `server/mqtt_bridge/src/mqtt_bridge/estimator.py` | Async estimator loop |
| `web/src/routes/map/+page.svelte` | Leaflet map page |
| `web/src/routes/+page.server.ts` | Server-side redirect to /map |
| `server/api/tests/test_positions.py` | API position endpoint tests |

### Modified
| File | Change |
|------|--------|
| `server/sql/init.sql` | Add columns + new hypertable |
| `server/mqtt_bridge/src/mqtt_bridge/handler.py` | Add `node_lat`/`node_lon` to `ScanEvent` |
| `server/mqtt_bridge/src/mqtt_bridge/db.py` | Update `upsert_node` + `insert_scan_events` |
| `server/mqtt_bridge/src/mqtt_bridge/main.py` | Coord cache, `handle_status`, `handle_scan`, `run()` |
| `server/api/src/api/models.py` | Extend `NodeResponse`; add `PositionResponse` |
| `server/api/src/api/routers/nodes.py` | Include `lat`/`lon` in SELECT |
| `server/api/src/api/routers/live.py` | LISTEN on `position_estimates` channel |
| `server/api/src/api/app.py` | Register positions router |
| `server/api/tests/test_nodes.py` | Include `lat`/`lon` in mock rows |
| `nodes/esp32-scanner/src/config.h.example` | Add `NODE_LAT`/`NODE_LON` |
| `nodes/esp32-scanner/src/main.cpp` | Publish `node_lat`/`node_lon` in status |
| `nodes/ttgo-lora32/src/config.h.example` | Add GPS note comment |
| `web/src/lib/api.ts` | Add position fetch helpers |
| `web/src/routes/+layout.svelte` | Add Map nav link |
| `web/src/routes/+page.svelte` | Redirect to /map |

---

## Chunk 1: Database Schema

**Goal:** Add `lat`/`lon` to `nodes`, add `node_lat`/`node_lon` to `scan_events`, create `position_estimates` hypertable.

No unit tests — schema is validated by integration with later tasks. Run a smoke check against the DB instead.

### Task 1: Schema migrations

**Files:**
- Modify: `server/sql/init.sql`

- [ ] **Step 1: Add coordinate columns and new hypertable to init.sql**

Open `server/sql/init.sql` and append the following after the existing `commands` table (before the end of file):

```sql
-- Idempotent coordinate migrations
ALTER TABLE nodes      ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION;
ALTER TABLE nodes      ADD COLUMN IF NOT EXISTS lon DOUBLE PRECISION;
ALTER TABLE scan_events ADD COLUMN IF NOT EXISTS node_lat DOUBLE PRECISION;
ALTER TABLE scan_events ADD COLUMN IF NOT EXISTS node_lon DOUBLE PRECISION;

CREATE TABLE IF NOT EXISTS position_estimates (
    time        TIMESTAMPTZ      NOT NULL,
    mac         TEXT             NOT NULL,
    lat         DOUBLE PRECISION NOT NULL,
    lon         DOUBLE PRECISION NOT NULL,
    accuracy_m  REAL,
    node_count  INTEGER          NOT NULL,
    method      TEXT             NOT NULL
);

SELECT create_hypertable('position_estimates', by_range('time'), if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS position_estimates_mac_time
    ON position_estimates (mac, time DESC);

SELECT add_retention_policy(
    'position_estimates',
    INTERVAL '30 days',
    if_not_exists => TRUE
);
```

- [ ] **Step 2: Verify SQL is syntactically valid**

```bash
cd server && docker compose up -d db
sleep 3
docker compose exec db psql -U sentinel -d sentinel -f /docker-entrypoint-initdb.d/init.sql
```

Expected: no ERROR lines; `ALTER TABLE`, `CREATE TABLE`, `CREATE INDEX` messages appear.

- [ ] **Step 3: Confirm columns exist**

```bash
docker compose exec db psql -U sentinel -d sentinel -c "\d nodes" -c "\d scan_events" -c "\d position_estimates"
```

Expected: `lat`, `lon` in `nodes`; `node_lat`, `node_lon` in `scan_events`; `position_estimates` shows all 7 columns.

- [ ] **Step 4: Commit**

```bash
git add server/sql/init.sql
git commit -m "feat: add coordinate columns and position_estimates hypertable"
```

---

## Chunk 2: mqtt_bridge Data Model & DB Functions

**Goal:** Extend `ScanEvent` with node coordinates; update `upsert_node` to persist lat/lon; update `insert_scan_events` to write node coords into each row.

### Task 2: Extend ScanEvent

**Files:**
- Modify: `server/mqtt_bridge/src/mqtt_bridge/handler.py`
- Modify: `server/mqtt_bridge/tests/test_handler.py`

- [ ] **Step 1: Write failing test for ScanEvent node_lat/lon defaults**

Add to `server/mqtt_bridge/tests/test_handler.py`:

```python
def test_scan_event_node_coords_default_none():
    payload = json.dumps(
        [{"ssid": "Net", "bssid": "aa:bb:cc:dd:ee:ff", "rssi": -50, "channel": 6}]
    ).encode()
    events = parse_wifi("scanner-01", payload)
    assert events[0].node_lat is None
    assert events[0].node_lon is None
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd server/mqtt_bridge && uv pip install --system -e ".[dev]" -q && pytest tests/test_handler.py::test_scan_event_node_coords_default_none -v
```

Expected: `AttributeError` — `ScanEvent` has no attribute `node_lat`.

- [ ] **Step 3: Add fields to ScanEvent**

In `server/mqtt_bridge/src/mqtt_bridge/handler.py`, add two optional fields to the dataclass:

```python
@dataclass
class ScanEvent:
    node_id:   str
    mac:       str
    rssi:      int
    scan_type: str
    ssid:      str | None
    time:      datetime
    node_lat:  float | None = None
    node_lon:  float | None = None
```

- [ ] **Step 4: Run test to confirm it passes**

```bash
cd server/mqtt_bridge && pytest tests/test_handler.py -v
```

Expected: all tests pass, including the new one.

- [ ] **Step 5: Commit**

```bash
git add server/mqtt_bridge/src/mqtt_bridge/handler.py server/mqtt_bridge/tests/test_handler.py
git commit -m "feat: add node_lat/node_lon to ScanEvent dataclass"
```

---

### Task 3: Add pytest-asyncio for async test support

The next three tasks introduce `@pytest.mark.asyncio` tests. `pytest-asyncio` is not currently a dependency and must be added before those tests will run correctly.

**Files:**
- Modify: `server/mqtt_bridge/pyproject.toml`

- [ ] **Step 1: Add pytest-asyncio to dev dependencies**

In `server/mqtt_bridge/pyproject.toml`, update the `[project.optional-dependencies] dev` section and `[tool.pytest.ini_options]`:

```toml
[project.optional-dependencies]
dev = [
    "pytest==9.0.2",
    "pytest-asyncio==0.25.3",
    "ruff==0.15.5",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 2: Install the updated dependencies**

```bash
cd server/mqtt_bridge && uv pip install --system -e ".[dev]" -q
```

Expected: `pytest-asyncio` installs without error.

- [ ] **Step 3: Confirm existing tests still pass**

```bash
cd server/mqtt_bridge && pytest tests/ -v
```

Expected: all existing tests pass.

- [ ] **Step 4: Commit**

```bash
git add server/mqtt_bridge/pyproject.toml
git commit -m "chore: add pytest-asyncio for async test support"
```

---

### Task 4: Update upsert_node to persist coordinates

**Files:**
- Modify: `server/mqtt_bridge/src/mqtt_bridge/db.py`

No additional test file needed — `upsert_node` is already an integration-only function (it requires asyncpg + a real DB). Its correctness is validated by the estimator integration later. We use a focused unit test on the SQL logic via mocking.

- [ ] **Step 1: Write failing test**

Create `server/mqtt_bridge/tests/test_db.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.fixture
def mock_pool():
    conn = AsyncMock()
    conn.execute = AsyncMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=cm)
    return pool, conn


@pytest.mark.asyncio
async def test_upsert_node_with_coords(mock_pool):
    pool, conn = mock_pool
    from mqtt_bridge.db import upsert_node
    await upsert_node(pool, "scanner-01", firmware_ver="0.2.0", ip="10.0.0.1",
                      lat=38.123, lon=-122.456)
    call_args = conn.execute.call_args
    sql = call_args[0][0]
    params = call_args[0][1:]
    assert "lat" in sql.lower()
    assert 38.123 in params
    assert -122.456 in params


@pytest.mark.asyncio
async def test_upsert_node_without_coords_does_not_overwrite(mock_pool):
    pool, conn = mock_pool
    from mqtt_bridge.db import upsert_node
    await upsert_node(pool, "scanner-01", firmware_ver="0.2.0", ip="10.0.0.1",
                      lat=None, lon=None)
    sql = conn.execute.call_args[0][0]
    # Must use CASE WHEN to avoid overwriting with NULL
    assert "CASE WHEN" in sql
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd server/mqtt_bridge && pytest tests/test_db.py -v
```

Expected: `TypeError` — `upsert_node` does not accept `lat`/`lon`.

- [ ] **Step 3: Update upsert_node in db.py**

Replace the existing `upsert_node` function:

```python
async def upsert_node(
    pool: asyncpg.Pool,
    node_id: str,
    firmware_ver: str,
    ip: str,
    lat: float | None = None,
    lon: float | None = None,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO nodes (node_id, node_type, last_seen, firmware_ver, lat, lon)
            VALUES ($1, 'esp32_scanner', now(), $2, $3, $4)
            ON CONFLICT (node_id) DO UPDATE SET
                last_seen    = now(),
                firmware_ver = EXCLUDED.firmware_ver,
                lat = CASE WHEN $3 IS NOT NULL THEN $3 ELSE nodes.lat END,
                lon = CASE WHEN $4 IS NOT NULL THEN $4 ELSE nodes.lon END
            """,
            node_id,
            firmware_ver,
            lat,
            lon,
        )
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd server/mqtt_bridge && pytest tests/test_db.py tests/test_handler.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add server/mqtt_bridge/src/mqtt_bridge/db.py server/mqtt_bridge/tests/test_db.py
git commit -m "feat: upsert_node persists lat/lon with null-safe CASE WHEN"
```

---

### Task 5: Update insert_scan_events to write node coords

**Files:**
- Modify: `server/mqtt_bridge/src/mqtt_bridge/db.py`
- Modify: `server/mqtt_bridge/tests/test_db.py`

- [ ] **Step 1: Write failing test**

Add to `server/mqtt_bridge/tests/test_db.py`:

```python
from datetime import UTC, datetime
from mqtt_bridge.handler import ScanEvent

@pytest.mark.asyncio
async def test_insert_scan_events_includes_node_coords(mock_pool):
    pool, conn = mock_pool
    conn.executemany = AsyncMock()
    conn.execute = AsyncMock()
    from mqtt_bridge.db import insert_scan_events
    events = [
        ScanEvent(
            node_id="scanner-01", mac="AA:BB:CC:DD:EE:FF",
            rssi=-60, scan_type="wifi", ssid="Net",
            time=datetime(2026, 3, 12, tzinfo=UTC),
            node_lat=38.123, node_lon=-122.456,
        )
    ]
    await insert_scan_events(pool, events)
    rows = conn.executemany.call_args[0][1]
    assert rows[0][6] == 38.123   # node_lat is 7th param
    assert rows[0][7] == -122.456  # node_lon is 8th param
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd server/mqtt_bridge && pytest tests/test_db.py::test_insert_scan_events_includes_node_coords -v
```

Expected: `AssertionError` or `IndexError` — current insert only has 6 params.

- [ ] **Step 3: Update insert_scan_events in db.py**

Replace the `executemany` call inside `insert_scan_events`:

```python
async def insert_scan_events(pool: asyncpg.Pool, events: list[ScanEvent]) -> None:
    if not events:
        return
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO scan_events
                (time, node_id, mac, rssi, scan_type, ssid, node_lat, node_lon)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            [
                (e.time, e.node_id, e.mac, e.rssi, e.scan_type, e.ssid,
                 e.node_lat, e.node_lon)
                for e in events
            ],
        )
        payload = json.dumps(
            {
                "node_id": events[0].node_id,
                "scan_type": events[0].scan_type,
                "count": len(events),
            }
        )
        await conn.execute("SELECT pg_notify('scan_events', $1)", payload)
```

- [ ] **Step 4: Run all mqtt_bridge tests**

```bash
cd server/mqtt_bridge && pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add server/mqtt_bridge/src/mqtt_bridge/db.py server/mqtt_bridge/tests/test_db.py
git commit -m "feat: insert_scan_events writes node_lat/node_lon per row"
```

---

## Chunk 3: mqtt_bridge Runtime — Coord Cache & Estimator

**Goal:** Add the module-level `_node_coords` cache to `main.py`, update `handle_status` and `handle_scan` to use it, and implement the position estimator as a separate module.

### Task 6: Coordinate cache + handle_status/handle_scan updates

**Files:**
- Modify: `server/mqtt_bridge/src/mqtt_bridge/main.py`

- [ ] **Step 1: Add _node_coords cache and update handle_status**

Replace `main.py` content with:

```python
from __future__ import annotations

import asyncio
import json
import logging

import aiomqtt
import asyncpg

from mqtt_bridge.config import DB_URL, MQTT_HOST, MQTT_PORT
from mqtt_bridge.db import insert_scan_events, upsert_devices, upsert_node
from mqtt_bridge.estimator import run_estimator
from mqtt_bridge.handler import extract_node_id, parse_ble, parse_wifi

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger(__name__)

# Populated by handle_status; used by handle_scan to stamp node position onto events.
_node_coords: dict[str, tuple[float, float]] = {}


async def handle_scan(pool: asyncpg.Pool, topic: str, payload: bytes) -> None:
    node_id = extract_node_id(topic)

    if "/scan/wifi" in topic:
        events = parse_wifi(node_id, payload)
    elif "/scan/bt" in topic:
        events = parse_ble(node_id, payload)
    else:
        return

    if not events:
        return

    coords = _node_coords.get(node_id)
    if coords:
        for e in events:
            e.node_lat, e.node_lon = coords

    await upsert_devices(pool, events)
    await insert_scan_events(pool, events)
    log.info("node=%s topic=%s count=%d", node_id, topic.split("/")[-1], len(events))


async def handle_status(pool: asyncpg.Pool, topic: str, payload: bytes) -> None:
    node_id = extract_node_id(topic)
    data: dict = json.loads(payload)

    lat: float | None = None
    lon: float | None = None
    if data.get("gps_fix") and "gps_lat" in data:
        lat, lon = float(data["gps_lat"]), float(data["gps_lon"])
    elif "node_lat" in data and "node_lon" in data:
        lat, lon = float(data["node_lat"]), float(data["node_lon"])

    if lat is not None and lon is not None:
        _node_coords[node_id] = (lat, lon)

    await upsert_node(
        pool,
        node_id,
        firmware_ver=data.get("firmware_ver", ""),
        ip=data.get("ip", ""),
        lat=lat,
        lon=lon,
    )
    log.info("node=%s status uptime_ms=%s lat=%s lon=%s",
             node_id, data.get("uptime_ms"), lat, lon)


async def _run_mqtt(pool: asyncpg.Pool) -> None:
    while True:
        try:
            async with aiomqtt.Client(MQTT_HOST, MQTT_PORT) as client:
                log.info("Connected to MQTT broker %s:%d", MQTT_HOST, MQTT_PORT)
                await client.subscribe("nodes/+/scan/#")
                await client.subscribe("nodes/+/status")

                async for message in client.messages:
                    topic = str(message.topic)
                    try:
                        if "/scan/" in topic:
                            await handle_scan(pool, topic, message.payload)
                        elif "/status" in topic:
                            await handle_status(pool, topic, message.payload)
                    except Exception:
                        log.exception("Error handling topic=%s", topic)

        except aiomqtt.MqttError as exc:
            log.warning("MQTT connection lost: %s — reconnecting in 5s", exc)
            await asyncio.sleep(5)


async def run(pool: asyncpg.Pool) -> None:
    await asyncio.gather(
        _run_mqtt(pool),
        run_estimator(pool),
    )


async def main() -> None:
    log.info("Connecting to database")
    pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=5)
    log.info("Database connected")
    await run(pool)
```

- [ ] **Step 2: Write test for handle_status coord extraction**

Create `server/mqtt_bridge/tests/test_main.py`:

```python
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import mqtt_bridge.main as main_module


@pytest.fixture(autouse=True)
def reset_node_coords():
    main_module._node_coords.clear()
    yield
    main_module._node_coords.clear()


@pytest.fixture
def mock_pool():
    conn = AsyncMock()
    conn.execute = AsyncMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=cm)
    return pool


@pytest.mark.asyncio
async def test_handle_status_tbeam_gps_fix_caches_coords(mock_pool):
    payload = json.dumps({
        "firmware_ver": "0.1.0", "ip": "10.0.0.2",
        "gps_fix": True, "gps_lat": 38.123, "gps_lon": -122.456,
        "uptime_ms": 1000,
    }).encode()
    with patch("mqtt_bridge.main.upsert_node", new=AsyncMock()) as mock_upsert:
        await main_module.handle_status(mock_pool, "nodes/tbeam-01/status", payload)
    assert main_module._node_coords["tbeam-01"] == (38.123, -122.456)
    mock_upsert.assert_called_once()
    _, kwargs = mock_upsert.call_args
    assert kwargs["lat"] == 38.123


@pytest.mark.asyncio
async def test_handle_status_fixed_node_caches_coords(mock_pool):
    payload = json.dumps({
        "firmware_ver": "0.2.0", "ip": "10.0.0.3",
        "node_lat": 38.500, "node_lon": -122.900,
        "uptime_ms": 2000,
    }).encode()
    with patch("mqtt_bridge.main.upsert_node", new=AsyncMock()):
        await main_module.handle_status(mock_pool, "nodes/scanner-01/status", payload)
    assert main_module._node_coords["scanner-01"] == (38.500, -122.900)


@pytest.mark.asyncio
async def test_handle_status_no_gps_fix_does_not_cache(mock_pool):
    payload = json.dumps({
        "firmware_ver": "0.1.0", "ip": "10.0.0.2",
        "gps_fix": False, "uptime_ms": 500,
    }).encode()
    with patch("mqtt_bridge.main.upsert_node", new=AsyncMock()):
        await main_module.handle_status(mock_pool, "nodes/tbeam-01/status", payload)
    assert "tbeam-01" not in main_module._node_coords


@pytest.mark.asyncio
async def test_handle_scan_stamps_coords_from_cache(mock_pool):
    main_module._node_coords["scanner-01"] = (38.123, -122.456)
    payload = json.dumps(
        [{"ssid": "Net", "bssid": "aa:bb:cc:dd:ee:ff", "rssi": -60, "channel": 6}]
    ).encode()
    stamped_events = []

    async def capture_events(pool, events):
        stamped_events.extend(events)

    with patch("mqtt_bridge.main.upsert_devices", new=AsyncMock()), \
         patch("mqtt_bridge.main.insert_scan_events", new=capture_events):
        await main_module.handle_scan(mock_pool, "nodes/scanner-01/scan/wifi", payload)

    assert len(stamped_events) == 1
    assert stamped_events[0].node_lat == 38.123
    assert stamped_events[0].node_lon == -122.456


@pytest.mark.asyncio
async def test_handle_scan_no_coords_leaves_none(mock_pool):
    # scanner-01 not in cache
    payload = json.dumps(
        [{"ssid": "Net", "bssid": "bb:cc:dd:ee:ff:00", "rssi": -70, "channel": 1}]
    ).encode()
    stamped_events = []

    async def capture_events(pool, events):
        stamped_events.extend(events)

    with patch("mqtt_bridge.main.upsert_devices", new=AsyncMock()), \
         patch("mqtt_bridge.main.insert_scan_events", new=capture_events):
        await main_module.handle_scan(mock_pool, "nodes/scanner-02/scan/wifi", payload)

    assert stamped_events[0].node_lat is None
```

- [ ] **Step 3: Run tests (estimator import will fail — expected)**

```bash
cd server/mqtt_bridge && pytest tests/test_main.py -v
```

Expected: `ImportError: cannot import name 'run_estimator'` — estimator module not yet created.

- [ ] **Step 4: Create stub estimator to unblock tests**

Create `server/mqtt_bridge/src/mqtt_bridge/estimator.py`:

```python
from __future__ import annotations

import asyncio
import logging

import asyncpg

log = logging.getLogger(__name__)


async def run_estimator(pool: asyncpg.Pool) -> None:
    """Stub — full implementation in next task."""
    while True:
        await asyncio.sleep(30)
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
cd server/mqtt_bridge && pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add server/mqtt_bridge/src/mqtt_bridge/main.py \
        server/mqtt_bridge/src/mqtt_bridge/estimator.py \
        server/mqtt_bridge/tests/test_main.py
git commit -m "feat: add node coord cache to mqtt_bridge main; stub estimator"
```

---

### Task 7: Position estimator implementation

**Files:**
- Modify: `server/mqtt_bridge/src/mqtt_bridge/estimator.py`

- [ ] **Step 1: Write failing tests for estimator math helpers**

Create `server/mqtt_bridge/tests/test_estimator.py`:

```python
import math
import pytest
from mqtt_bridge.estimator import haversine, rssi_to_distance, weighted_centroid


def test_haversine_same_point_is_zero():
    assert haversine(38.0, -122.0, 38.0, -122.0) == pytest.approx(0.0)


def test_haversine_known_distance():
    # Approx 1 degree of latitude ≈ 111,195 m
    d = haversine(0.0, 0.0, 1.0, 0.0)
    assert 111_000 < d < 112_000


def test_rssi_to_distance_at_minus59_is_1m():
    # At reference RSSI (-59 dBm at 1m), distance should be ≈ 1m
    d = rssi_to_distance(-59)
    assert d == pytest.approx(1.0, rel=0.01)


def test_rssi_to_distance_weaker_signal_is_farther():
    assert rssi_to_distance(-80) > rssi_to_distance(-60)


def test_weighted_centroid_single_node():
    nodes = [(38.0, -122.0, -60)]
    lat, lon = weighted_centroid(nodes)
    assert lat == pytest.approx(38.0)
    assert lon == pytest.approx(-122.0)


def test_weighted_centroid_equal_rssi_is_midpoint():
    # Two nodes at equal RSSI → midpoint
    nodes = [(38.0, -122.0, -60), (38.2, -122.0, -60)]
    lat, lon = weighted_centroid(nodes)
    assert lat == pytest.approx(38.1, rel=0.001)
    assert lon == pytest.approx(-122.0, rel=0.001)


def test_weighted_centroid_stronger_rssi_pulls_toward_closer_node():
    # Node A is strong (-50), node B is weak (-80) → estimate closer to A
    nodes = [(38.0, -122.0, -50), (38.4, -122.0, -80)]
    lat, lon = weighted_centroid(nodes)
    assert lat < 38.2  # pulled toward A (38.0)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd server/mqtt_bridge && pytest tests/test_estimator.py -v
```

Expected: `ImportError` — `haversine`, `rssi_to_distance`, `weighted_centroid` not yet defined.

- [ ] **Step 3: Implement full estimator module**

Replace `server/mqtt_bridge/src/mqtt_bridge/estimator.py` with:

```python
from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import UTC, datetime

import asyncpg

log = logging.getLogger(__name__)

EARTH_RADIUS_M = 6_371_000.0
# Log-distance path loss constants
_TX_POWER_DBM = -59    # reference RSSI at 1 m (reasonable default for WiFi/BLE)
_PATH_LOSS_EXP = 2.7   # outdoor path loss exponent


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in metres between two GPS coordinates."""
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return EARTH_RADIUS_M * 2 * math.asin(math.sqrt(a))


def rssi_to_distance(rssi: int) -> float:
    """Estimate distance in metres from RSSI using log-distance path loss model."""
    return 10 ** ((_TX_POWER_DBM - rssi) / (10 * _PATH_LOSS_EXP))


def weighted_centroid(nodes: list[tuple[float, float, int]]) -> tuple[float, float]:
    """
    Compute weighted centroid of node positions.

    Args:
        nodes: list of (lat, lon, rssi) tuples

    Returns:
        (lat, lon) estimate
    """
    weights = [10 ** (rssi / 10) for _, _, rssi in nodes]
    total = sum(weights)
    lat = sum(w * n[0] for w, n in zip(weights, nodes)) / total
    lon = sum(w * n[1] for w, n in zip(weights, nodes)) / total
    return lat, lon


def _accuracy_single(rssi: int) -> float:
    """Rough accuracy estimate for a single-node observation."""
    return rssi_to_distance(rssi)


def _accuracy_centroid(
    nodes: list[tuple[float, float, int]],
    est_lat: float,
    est_lon: float,
) -> float:
    """Weighted stddev of great-circle distances from estimate to each node."""
    weights = [10 ** (rssi / 10) for _, _, rssi in nodes]
    total = sum(weights)
    variance = sum(
        w * haversine(est_lat, est_lon, lat, lon) ** 2
        for w, (lat, lon, _) in zip(weights, nodes)
    ) / total
    return math.sqrt(variance)


async def _estimate_once(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT mac, node_lat, node_lon, MAX(rssi) AS rssi
            FROM scan_events
            WHERE time > now() - INTERVAL '90 seconds'
              AND node_lat IS NOT NULL
            GROUP BY mac, node_lat, node_lon
            """
        )

    # Group rows by mac
    by_mac: dict[str, list[tuple[float, float, int]]] = {}
    for row in rows:
        by_mac.setdefault(row["mac"], []).append(
            (row["node_lat"], row["node_lon"], row["rssi"])
        )

    if not by_mac:
        return

    now = datetime.now(UTC)
    inserts: list[tuple] = []
    notifications: list[str] = []

    for mac, node_readings in by_mac.items():
        node_count = len(node_readings)

        if node_count == 1:
            lat, lon, rssi = node_readings[0]
            accuracy_m = _accuracy_single(rssi)
            method = "single"
        else:
            lat, lon = weighted_centroid(node_readings)
            accuracy_m = _accuracy_centroid(node_readings, lat, lon)
            method = "centroid"

        inserts.append((now, mac, lat, lon, accuracy_m, node_count, method))
        notifications.append(
            json.dumps({
                "type": "position_update",
                "mac": mac,
                "lat": lat,
                "lon": lon,
                "accuracy_m": accuracy_m,
                "node_count": node_count,
                "method": method,
                "time": now.isoformat(),
            })
        )

    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO position_estimates
                (time, mac, lat, lon, accuracy_m, node_count, method)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            inserts,
        )
        for payload in notifications:
            await conn.execute("SELECT pg_notify('position_estimates', $1)", payload)

    log.info("estimator: updated %d device positions", len(inserts))


async def run_estimator(pool: asyncpg.Pool) -> None:
    """Run position estimation every 30 seconds."""
    while True:
        try:
            await _estimate_once(pool)
        except Exception:
            log.exception("Estimator error — will retry next cycle")
        await asyncio.sleep(30)
```

- [ ] **Step 4: Run all mqtt_bridge tests**

```bash
cd server/mqtt_bridge && pytest tests/ -v
```

Expected: all tests pass including new estimator math tests.

- [ ] **Step 5: Commit**

```bash
git add server/mqtt_bridge/src/mqtt_bridge/estimator.py \
        server/mqtt_bridge/tests/test_estimator.py
git commit -m "feat: implement position estimator with weighted centroid"
```

---

## Chunk 4: FastAPI Position API

**Goal:** Extend `NodeResponse` with coordinates, add `/positions` router with three endpoints, extend the WebSocket live listener to the `position_estimates` pg_notify channel.

### Task 8: Extend models and nodes router

**Files:**
- Modify: `server/api/src/api/models.py`
- Modify: `server/api/src/api/routers/nodes.py`
- Modify: `server/api/tests/test_nodes.py`

- [ ] **Step 1: Write failing test for lat/lon in nodes response**

In `server/api/tests/test_nodes.py`, update the mock row and add an assertion:

```python
# In client_with_nodes fixture, update the row dict to include lat/lon:
{
    "node_id": "scanner-01",
    "node_type": "esp32_scanner",
    "location": None,
    "last_seen": NOW,
    "firmware_ver": "0.2.0",
    "lat": 38.123,
    "lon": -122.456,
}

# Add new test:
def test_get_nodes_includes_coordinates(client_with_nodes):
    client, _ = client_with_nodes
    response = client.get("/nodes")
    data = response.json()
    assert data[0]["lat"] == 38.123
    assert data[0]["lon"] == -122.456
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd server/api && uv pip install --system -e ".[dev]" -q && pytest tests/test_nodes.py -v
```

Expected: `ValidationError` — `NodeResponse` does not have `lat`/`lon`.

- [ ] **Step 3: Update NodeResponse in models.py**

In `server/api/src/api/models.py`, update `NodeResponse` and add `PositionResponse`:

```python
class NodeResponse(BaseModel):
    node_id: str
    node_type: str
    location: str | None
    last_seen: datetime
    firmware_ver: str
    lat: float | None
    lon: float | None


class PositionResponse(BaseModel):
    time: datetime
    mac: str
    lat: float
    lon: float
    accuracy_m: float | None
    node_count: int
    method: str
    label: str | None
    tag: str
    vendor: str | None
    device_type: str
```

- [ ] **Step 4: Update nodes router SELECT to include lat/lon**

In `server/api/src/api/routers/nodes.py`, update the query:

```python
rows = await conn.fetch(
    "SELECT node_id, node_type, location, last_seen, firmware_ver, lat, lon "
    "FROM nodes ORDER BY last_seen DESC"
)
```

- [ ] **Step 5: Run tests to confirm pass**

```bash
cd server/api && pytest tests/test_nodes.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add server/api/src/api/models.py \
        server/api/src/api/routers/nodes.py \
        server/api/tests/test_nodes.py
git commit -m "feat: add lat/lon to NodeResponse and PositionResponse model"
```

---

### Task 9: Positions router

**Files:**
- Create: `server/api/src/api/routers/positions.py`
- Create: `server/api/tests/test_positions.py`
- Modify: `server/api/src/api/app.py`

- [ ] **Step 1: Write failing tests**

Create `server/api/tests/test_positions.py`:

```python
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
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd server/api && pytest tests/test_positions.py -v
```

Expected: `404 Not Found` — `/positions/*` routes don't exist yet.

- [ ] **Step 3: Create positions router**

Create `server/api/src/api/routers/positions.py`:

```python
from __future__ import annotations

from datetime import datetime

import asyncpg
from fastapi import APIRouter, Depends, Query

from api.app import get_pool
from api.models import PositionResponse

router = APIRouter(prefix="/positions", tags=["positions"])

_HISTORY_SQL = """
    SELECT p.time, p.mac, p.lat, p.lon, p.accuracy_m, p.node_count, p.method,
           d.label, d.tag, d.vendor, d.device_type
    FROM position_estimates p
    JOIN devices d USING (mac)
    WHERE p.mac = $1
      AND ($2::timestamptz IS NULL OR p.time >= $2)
    ORDER BY p.time ASC
    LIMIT $3
"""


@router.get("/current", response_model=list[PositionResponse])
async def current_positions(
    tag: str | None = None,
    pool: asyncpg.Pool = Depends(get_pool),
):
    # Use uniform parameterisation — $1::text IS NULL safely handles the no-filter case
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (p.mac)
                p.time, p.mac, p.lat, p.lon, p.accuracy_m, p.node_count, p.method,
                d.label, d.tag, d.vendor, d.device_type
            FROM position_estimates p
            JOIN devices d USING (mac)
            WHERE ($1::text IS NULL OR d.tag = $1)
            ORDER BY p.mac, p.time DESC
            """,
            tag,
        )
    return [dict(r) for r in rows]


@router.get("/active", response_model=list[PositionResponse])
async def active_positions(
    window_minutes: int = Query(default=5, ge=1, le=1440),
    pool: asyncpg.Pool = Depends(get_pool),
):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (p.mac)
                p.time, p.mac, p.lat, p.lon, p.accuracy_m, p.node_count, p.method,
                d.label, d.tag, d.vendor, d.device_type
            FROM position_estimates p
            JOIN devices d USING (mac)
            WHERE p.time > now() - ($1 * INTERVAL '1 minute')
            ORDER BY p.mac, p.time DESC
            """,
            window_minutes,
        )
    return [dict(r) for r in rows]


@router.get("/{mac}/history", response_model=list[PositionResponse])
async def position_history(
    mac: str,
    since: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    pool: asyncpg.Pool = Depends(get_pool),
):
    async with pool.acquire() as conn:
        rows = await conn.fetch(_HISTORY_SQL, mac.upper(), since, limit)
    return [dict(r) for r in rows]
```

- [ ] **Step 4: Register router in app.py**

In `server/api/src/api/app.py`, add after the existing router imports:

```python
from api.routers import positions as positions_router  # noqa: E402
app.include_router(positions_router.router)
```

- [ ] **Step 5: Run all API tests**

```bash
cd server/api && pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add server/api/src/api/routers/positions.py \
        server/api/src/api/app.py \
        server/api/tests/test_positions.py
git commit -m "feat: add /positions/current, /active, /{mac}/history endpoints"
```

---

### Task 10: Extend WebSocket LISTEN to position_estimates

**Files:**
- Modify: `server/api/src/api/routers/live.py`

- [ ] **Step 1: Add position_estimates listener**

In `server/api/src/api/routers/live.py`, update `_listen_loop` to also listen on the new channel:

```python
async def _listen_loop() -> None:
    """Background task: LISTEN for pg_notify and broadcast to WebSocket clients."""
    while True:
        try:
            conn = await asyncpg.connect(DB_URL)
            log.info("WebSocket LISTEN task connected to DB")

            async def on_notify(connection, pid, channel, payload):
                await _broadcast(payload)

            await conn.add_listener("scan_events", on_notify)
            await conn.add_listener("position_estimates", on_notify)

            while not conn.is_closed():
                await asyncio.sleep(5)
        except Exception as exc:
            log.warning("LISTEN loop error: %s — reconnecting in 5s", exc)
            await asyncio.sleep(5)
```

- [ ] **Step 2: Run all API tests**

```bash
cd server/api && pytest tests/ -v
```

Expected: all pass (no tests for the LISTEN loop itself — it's integration-only).

- [ ] **Step 3: Commit**

```bash
git add server/api/src/api/routers/live.py
git commit -m "feat: WebSocket LISTEN on position_estimates pg_notify channel"
```

---

## Chunk 5: Firmware — Fixed Node Location Publishing

**Goal:** Fixed ESP32-S3 scanner nodes publish `node_lat`/`node_lon` in their status payload; TTGO T-Beam config.h.example notes that GPS handles location automatically.

### Task 11: esp32-scanner firmware

**Files:**
- Modify: `nodes/esp32-scanner/src/config.h.example`
- Modify: `nodes/esp32-scanner/src/main.cpp`

- [ ] **Step 1: Add NODE_LAT/LON to config.h.example**

In `nodes/esp32-scanner/src/config.h.example`, add after `FIRMWARE_VER`:

```cpp
// GPS position of this fixed node — set to actual deployed coordinates.
// T-Beam nodes use onboard GPS instead; leave these at 0.0 for T-Beams.
#define NODE_LAT  0.000000   // decimal degrees, e.g. 38.123456
#define NODE_LON  0.000000   // decimal degrees, e.g. -122.654321
```

- [ ] **Step 2: Replace publishStatus() in main.cpp**

Find and replace the entire `publishStatus()` function in `nodes/esp32-scanner/src/main.cpp` with the version below (adds `node_lat` and `node_lon` fields; all other fields are unchanged):

```cpp
static void publishStatus() {
    JsonDocument doc;
    doc["uptime_ms"]    = millis();
    doc["free_heap"]    = ESP.getFreeHeap();
    doc["ip"]           = WiFi.localIP().toString();
    doc["firmware_ver"] = FIRMWARE_VER;
    doc["wifi_rssi"]    = WiFi.RSSI();
    doc["node_lat"]     = NODE_LAT;
    doc["node_lon"]     = NODE_LON;

    serializeJson(doc, mqttBuf, sizeof(mqttBuf));
    mqtt.publish(topicStatus, mqttBuf);
    Serial.printf("[MQTT] → %s\n", topicStatus);
}
```

- [ ] **Step 3: Add NODE_LAT/LON to your local config.h**

`config.h` is gitignored and is not updated from `config.h.example` automatically. Each developer must add the defines manually to their local `config.h`:

```cpp
#define NODE_LAT  38.123456   // replace with actual deployed coordinates
#define NODE_LON  -122.654321
```

- [ ] **Step 4: Verify esp32-scanner firmware builds**

```bash
~/.platformio/penv/bin/pio run --project-dir nodes/esp32-scanner -e esp32-s3-devkitc-1-headless
```

Expected: `SUCCESS` — no compile errors.

- [ ] **Step 5: Add GPS comment to ttgo-lora32 config.h.example**

In `nodes/ttgo-lora32/src/config.h.example`, add after `FIRMWARE_VER`:

```cpp
// Location: T-Beam uses onboard NEO-M8N GPS automatically.
// No NODE_LAT/NODE_LON needed — GPS coordinates are published in status.
```

- [ ] **Step 6: Verify T-Beam firmware builds**

```bash
~/.platformio/penv/bin/pio run --project-dir nodes/ttgo-lora32 -e ttgo-lora32-headless
```

Expected: `SUCCESS`.

- [ ] **Step 7: Commit**

```bash
git add nodes/esp32-scanner/src/config.h.example \
        nodes/esp32-scanner/src/main.cpp \
        nodes/ttgo-lora32/src/config.h.example
git commit -m "feat: fixed nodes publish node_lat/node_lon in status payload"
```

---

## Chunk 6: Web UI — Map Page

**Goal:** Add a `/map` page with Leaflet showing node markers and device position circles with live WebSocket updates. Add Map link to nav, redirect root to /map.

### Task 12: Install Leaflet

**Files:**
- Modify: `web/package.json`

- [ ] **Step 1: Install leaflet and types**

```bash
cd web && npm install --save-exact leaflet@1.9.4 && npm install --save-dev --save-exact @types/leaflet@1.9.14
```

- [ ] **Step 2: Verify dev server still starts**

```bash
cd web && npm run check
```

Expected: no TypeScript errors.

- [ ] **Step 3: Commit**

```bash
git add web/package.json web/package-lock.json
git commit -m "feat: add leaflet 1.9.4 dependency to web"
```

---

### Task 13: Position API helpers in api.ts

**Files:**
- Modify: `web/src/lib/api.ts`

- [ ] **Step 1: Add fetch helpers for positions**

Append to `web/src/lib/api.ts`:

```typescript
export type PositionResponse = {
  time: string;
  mac: string;
  lat: number;
  lon: number;
  accuracy_m: number | null;
  node_count: number;
  method: string;
  label: string | null;
  tag: string;
  vendor: string | null;
  device_type: string;
};

export type NodeResponse = {
  node_id: string;
  node_type: string;
  location: string | null;
  last_seen: string;
  firmware_ver: string;
  lat: number | null;
  lon: number | null;
};

export async function fetchCurrentPositions(tag?: string): Promise<PositionResponse[]> {
  const url = tag ? `${BASE}/positions/current?tag=${tag}` : `${BASE}/positions/current`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`GET /positions/current failed: ${res.status}`);
  return res.json();
}

export async function fetchActivePositions(windowMinutes = 5): Promise<PositionResponse[]> {
  const res = await fetch(`${BASE}/positions/active?window_minutes=${windowMinutes}`);
  if (!res.ok) throw new Error(`GET /positions/active failed: ${res.status}`);
  return res.json();
}

export async function fetchPositionHistory(mac: string, limit = 100): Promise<PositionResponse[]> {
  const res = await fetch(`${BASE}/positions/${encodeURIComponent(mac)}/history?limit=${limit}`);
  if (!res.ok) throw new Error(`GET /positions/${mac}/history failed: ${res.status}`);
  return res.json();
}
```

- [ ] **Step 2: Type-check**

```bash
cd web && npm run check
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add web/src/lib/api.ts
git commit -m "feat: add position fetch helpers and typed NodeResponse to api.ts"
```

---

### Task 14: Map page

**Files:**
- Create: `web/src/routes/map/+page.svelte`

- [ ] **Step 1: Create the map page**

Create `web/src/routes/map/+page.svelte`:

```svelte
<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import type { Map as LeafletMap, CircleMarker, Polyline } from "leaflet";
  // Static import for Leaflet CSS — dynamic import does not work reliably in Vite/SvelteKit
  import "leaflet/dist/leaflet.css";
  import { liveWebSocket, fetchActivePositions, fetchPositionHistory } from "$lib/api";
  import type { PositionResponse, NodeResponse } from "$lib/api";
  import { fetchNodes } from "$lib/api";

  let mapEl: HTMLDivElement;
  let map: LeafletMap | undefined;
  let connected = false;
  let ws: WebSocket | undefined;
  let windowMinutes = 5;
  let showIgnored = false;

  // Map state
  const deviceMarkers = new Map<string, CircleMarker>();
  const nodeMarkers = new Map<string, CircleMarker>();
  const trailLines = new Map<string, Polyline>();
  let selectedMac: string | null = null;

  const TAG_COLORS: Record<string, string> = {
    unknown: "#facc15",
    known_resident: "#4ade80",
    known_vehicle: "#60a5fa",
    ignored: "#71717a",
  };

  async function initMap() {
    const L = await import("leaflet");

    map = L.map(mapEl).setView([0, 0], 2);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap contributors",
      maxZoom: 19,
    }).addTo(map);

    await loadNodes();
    await loadPositions();
  }

  async function loadNodes() {
    if (!map) return;
    const L = await import("leaflet");
    const nodes: NodeResponse[] = await fetchNodes();
    const bounds: [number, number][] = [];

    for (const node of nodes) {
      if (node.lat == null || node.lon == null) continue;
      bounds.push([node.lat, node.lon]);

      const age = Date.now() - new Date(node.last_seen).getTime();
      const color = age < 120_000 ? "#4ade80" : age < 600_000 ? "#facc15" : "#71717a";

      const marker = L.circleMarker([node.lat, node.lon], {
        radius: 8,
        color,
        fillColor: color,
        fillOpacity: 0.9,
        weight: 2,
      })
        .bindPopup(`<b>${node.node_id}</b><br>Last seen: ${new Date(node.last_seen).toLocaleTimeString()}`)
        .addTo(map);

      nodeMarkers.set(node.node_id, marker);
    }

    if (bounds.length > 0) {
      map.fitBounds(bounds as [[number, number], [number, number]], { padding: [40, 40] });
    }
  }

  async function loadPositions() {
    const positions = await fetchActivePositions(windowMinutes);
    for (const pos of positions) {
      if (pos.tag === "ignored" && !showIgnored) continue;
      updateDeviceMarker(pos);
    }
  }

  async function updateDeviceMarker(pos: PositionResponse) {
    if (!map) return;
    const L = await import("leaflet");

    const color = TAG_COLORS[pos.tag] ?? TAG_COLORS.unknown;
    const radius = Math.max(5, Math.min(40, (pos.accuracy_m ?? 20) / 3));

    if (deviceMarkers.has(pos.mac)) {
      deviceMarkers.get(pos.mac)!.setLatLng([pos.lat, pos.lon]);
    } else {
      const marker = L.circleMarker([pos.lat, pos.lon], {
        radius,
        color,
        fillColor: color,
        fillOpacity: 0.4,
        weight: 2,
      })
        .bindTooltip(pos.label ?? pos.mac, { permanent: false })
        .addTo(map);

      marker.on("click", () => selectDevice(pos.mac));
      deviceMarkers.set(pos.mac, marker);
    }
  }

  async function selectDevice(mac: string) {
    if (!map) return;
    const L = await import("leaflet");

    // Clear previous trail
    if (trailLines.has(mac)) {
      trailLines.get(mac)!.remove();
      trailLines.delete(mac);
    }

    selectedMac = mac;
    const history = await fetchPositionHistory(mac, 100);
    if (history.length < 2) return;

    const now = Date.now();
    const coords = history.map((p) => [p.lat, p.lon] as [number, number]);
    const trail = L.polyline(coords, {
      color: "#f97316",
      weight: 2,
      opacity: 0.8,
    }).addTo(map);

    trailLines.set(mac, trail);
  }

  function handleLiveEvent(data: unknown) {
    const event = data as { type?: string } & PositionResponse;
    if (event.type !== "position_update") return;
    if (event.tag === "ignored" && !showIgnored) return;
    updateDeviceMarker(event);
  }

  onMount(async () => {
    await initMap();
    ws = liveWebSocket(handleLiveEvent);
    ws.onopen = () => (connected = true);
    ws.onclose = () => (connected = false);
    ws.onerror = () => (connected = false);
  });

  onDestroy(() => {
    ws?.close();
    map?.remove();
  });
</script>

<svelte:head><title>Map — botanical-sentinel</title></svelte:head>

<div class="flex flex-col h-[calc(100vh-49px)]">
  <!-- Filter bar -->
  <div class="flex items-center gap-4 px-4 py-2 border-b border-zinc-800 bg-zinc-900 text-sm">
    <span class="text-xs px-2 py-0.5 rounded-full {connected ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300'}">
      {connected ? "live" : "disconnected"}
    </span>
    <label class="flex items-center gap-1 text-zinc-400">
      Last seen:
      <select
        class="bg-zinc-800 border border-zinc-700 rounded px-1 py-0.5 text-zinc-100"
        bind:value={windowMinutes}
        onchange={loadPositions}
      >
        <option value={5}>5 min</option>
        <option value={15}>15 min</option>
        <option value={60}>1 hour</option>
        <option value={1440}>All today</option>
      </select>
    </label>
    <label class="flex items-center gap-1 text-zinc-400 cursor-pointer">
      <input type="checkbox" bind:checked={showIgnored} onchange={loadPositions} />
      Show ignored
    </label>
    <!-- Tag legend -->
    <div class="flex items-center gap-3 ml-auto">
      {#each Object.entries(TAG_COLORS) as [tag, color]}
        <span class="flex items-center gap-1 text-xs text-zinc-400">
          <span class="inline-block w-3 h-3 rounded-full" style="background:{color}"></span>
          {tag.replace("_", " ")}
        </span>
      {/each}
    </div>
  </div>

  <!-- Map container -->
  <div bind:this={mapEl} class="flex-1 z-0"></div>
</div>
```

- [ ] **Step 2: Type-check**

```bash
cd web && npm run check
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add web/src/routes/map/+page.svelte
git commit -m "feat: add Leaflet map page with node markers and device circles"
```

---

### Task 15: Update navigation and root page

**Files:**
- Modify: `web/src/routes/+layout.svelte`
- Modify: `web/src/routes/+page.svelte`
- Create: `web/src/routes/+page.server.ts`

- [ ] **Step 1: Add Map to nav and redirect root**

In `web/src/routes/+layout.svelte`, add the Map link as the first nav item after the logo:

```svelte
<a href="/map" class="text-zinc-400 hover:text-white">Map</a>
```

Create `web/src/routes/+page.server.ts` for a proper server-side redirect (avoids flash of content and works without JavaScript):

```typescript
import { redirect } from "@sveltejs/kit";
import type { PageServerLoad } from "./$types";

export const load: PageServerLoad = () => {
  redirect(302, "/map");
};
```

Replace `web/src/routes/+page.svelte` with an empty file (the server load handles the redirect):

```svelte
```

- [ ] **Step 2: Type-check and verify build**

```bash
cd web && npm run check && npm run build
```

Expected: clean build.

- [ ] **Step 3: Commit**

```bash
git add web/src/routes/+layout.svelte web/src/routes/+page.svelte
git commit -m "feat: add Map to nav, redirect root to /map"
```

---

## Final Verification

- [ ] Run full test suite:

```bash
cd server/mqtt_bridge && pytest tests/ -v
cd server/api && pytest tests/ -v
cd web && npm run check
```

- [ ] Run linters:

```bash
cd server && ruff check . && ruff format --check .
cd web && npm run check
```

- [ ] Bring up the server stack and verify end-to-end:

```bash
cd server && docker compose up -d
# With a real node publishing, check:
# 1. position_estimates table receives rows
# 2. GET /positions/current returns data
# 3. /map page shows node pins and device circles
```
