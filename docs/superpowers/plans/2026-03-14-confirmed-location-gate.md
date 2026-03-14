# Confirmed-Location Gate for Fixed Nodes — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent fixed-location nodes with unconfirmed positions from corrupting device location estimates, and surface unlocated nodes on the map for one-click placement.

**Architecture:** Add a `location_confirmed` boolean to the `nodes` table. The MQTT bridge only populates its in-memory coordinate cache from confirmed DB values — never from raw firmware-reported coordinates. Any scan from a node with no confirmed location is dropped before reaching the DB. The `PATCH /nodes/{id}` API sets `location_confirmed=true` when lat/lon are provided. The map shows an amber "Needs placement" panel for unlocated nodes, with a click-to-place flow that reuses the existing edit panel.

**Tech Stack:** PostgreSQL/TimescaleDB, Python (asyncpg, FastAPI, Pydantic v2), SvelteKit, Leaflet

---

## Chunk 1: DB Schema + Bridge

### Task 1: DB schema — add location_confirmed

**Files:**
- Modify: `server/sql/init.sql`

- [ ] **Step 1: Append the migration**

At the end of `server/sql/init.sql`, add:

```sql
-- Idempotent migration: track whether a node's location has been confirmed by a user or GPS fix
ALTER TABLE nodes ADD COLUMN IF NOT EXISTS location_confirmed BOOLEAN NOT NULL DEFAULT FALSE;
```

- [ ] **Step 2: Commit**

```bash
git add server/sql/init.sql
git commit -m "feat: add location_confirmed column to nodes table"
```

---

### Task 2: db.py — update upsert_node and add coord-loading helpers

**Files:**
- Modify: `server/mqtt_bridge/src/mqtt_bridge/db.py`
- Modify: `server/mqtt_bridge/tests/test_db.py`

- [ ] **Step 1: Write four failing tests**

Add to the end of `server/mqtt_bridge/tests/test_db.py`. (`AsyncMock` is already imported at the top of the file — do not add a duplicate import.)

```python
async def test_upsert_node_with_location_confirmed(mock_pool):
    pool, conn = mock_pool
    from mqtt_bridge.db import upsert_node

    await upsert_node(
        pool, "scanner-01", firmware_ver="0.2.0", ip="10.0.0.1",
        lat=38.123, lon=-122.456, location_confirmed=True,
    )
    call_args = conn.execute.call_args[0]
    sql = call_args[0]
    params = call_args[1:]
    assert "location_confirmed" in sql.lower()
    assert True in params


async def test_load_confirmed_node_coords(mock_pool):
    pool, conn = mock_pool
    conn.fetch = AsyncMock(return_value=[
        {"node_id": "scanner-01", "lat": 38.123, "lon": -122.456},
        {"node_id": "scanner-02", "lat": 51.500, "lon": -0.100},
    ])
    from mqtt_bridge.db import load_confirmed_node_coords

    result = await load_confirmed_node_coords(pool)

    assert result == {
        "scanner-01": (38.123, -122.456),
        "scanner-02": (51.500, -0.100),
    }
    sql = conn.fetch.call_args[0][0]
    assert "location_confirmed" in sql.lower()


async def test_get_confirmed_node_coords_returns_none_when_not_confirmed(mock_pool):
    pool, conn = mock_pool
    conn.fetchrow = AsyncMock(return_value=None)
    from mqtt_bridge.db import get_confirmed_node_coords

    result = await get_confirmed_node_coords(pool, "scanner-01")
    assert result is None


async def test_get_confirmed_node_coords_returns_tuple_when_confirmed(mock_pool):
    pool, conn = mock_pool
    conn.fetchrow = AsyncMock(return_value={"lat": 38.123, "lon": -122.456})
    from mqtt_bridge.db import get_confirmed_node_coords

    result = await get_confirmed_node_coords(pool, "scanner-01")
    assert result == (38.123, -122.456)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd server/mqtt_bridge && python -m pytest tests/test_db.py::test_upsert_node_with_location_confirmed tests/test_db.py::test_load_confirmed_node_coords tests/test_db.py::test_get_confirmed_node_coords_returns_none_when_not_confirmed tests/test_db.py::test_get_confirmed_node_coords_returns_tuple_when_confirmed -v
```

Expected: 4 FAILs (ImportError or missing argument)

- [ ] **Step 3: Replace upsert_node and add two new functions in db.py**

Replace the `upsert_node` function and add the two new functions after it in `server/mqtt_bridge/src/mqtt_bridge/db.py`:

```python
async def upsert_node(
    pool: asyncpg.Pool,
    node_id: str,
    firmware_ver: str,
    ip: str,
    lat: float | None = None,
    lon: float | None = None,
    location_confirmed: bool = False,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO nodes (node_id, node_type, last_seen, firmware_ver, lat, lon, location_confirmed)
            VALUES ($1, 'esp32_scanner', now(), $2, $3, $4, $5)
            ON CONFLICT (node_id) DO UPDATE SET
                last_seen    = now(),
                firmware_ver = EXCLUDED.firmware_ver,
                lat = CASE WHEN $3 IS NOT NULL THEN $3 ELSE nodes.lat END,
                lon = CASE WHEN $4 IS NOT NULL THEN $4 ELSE nodes.lon END,
                location_confirmed = CASE WHEN $5 THEN TRUE ELSE nodes.location_confirmed END
            """,
            node_id,
            firmware_ver,
            lat,
            lon,
            location_confirmed,
        )


async def load_confirmed_node_coords(pool: asyncpg.Pool) -> dict[str, tuple[float, float]]:
    """Return confirmed lat/lon for all nodes where location_confirmed is true."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT node_id, lat, lon FROM nodes
            WHERE location_confirmed = true AND lat IS NOT NULL AND lon IS NOT NULL
            """
        )
    return {row["node_id"]: (row["lat"], row["lon"]) for row in rows}


async def get_confirmed_node_coords(
    pool: asyncpg.Pool, node_id: str
) -> tuple[float, float] | None:
    """Return confirmed lat/lon for a single node, or None if not confirmed."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT lat, lon FROM nodes
            WHERE node_id = $1 AND location_confirmed = true
              AND lat IS NOT NULL AND lon IS NOT NULL
            """,
            node_id,
        )
    if row:
        return (row["lat"], row["lon"])
    return None
```

- [ ] **Step 4: Run all db tests**

```bash
cd server/mqtt_bridge && python -m pytest tests/test_db.py -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add server/mqtt_bridge/src/mqtt_bridge/db.py server/mqtt_bridge/tests/test_db.py
git commit -m "feat: add location_confirmed to upsert_node and add coord-loading helpers"
```

---

### Task 3: main.py — remove firmware coords, gate scans on confirmed location

**Files:**
- Modify: `server/mqtt_bridge/src/mqtt_bridge/main.py`
- Modify: `server/mqtt_bridge/tests/test_main.py`

- [ ] **Step 1: Replace test_main.py with updated tests**

The existing tests `test_handle_status_fixed_node_caches_coords` and `test_handle_scan_no_coords_leaves_none` test behaviour that is being removed. Replace the entire content of `server/mqtt_bridge/tests/test_main.py` with:

```python
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
    conn.fetchrow = AsyncMock(return_value=None)
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=cm)
    return pool


@pytest.mark.asyncio
async def test_handle_status_tbeam_gps_fix_caches_coords(mock_pool):
    payload = json.dumps(
        {
            "firmware_ver": "0.1.0",
            "ip": "10.0.0.2",
            "gps_fix": True,
            "gps_lat": 38.123,
            "gps_lon": -122.456,
            "uptime_ms": 1000,
        }
    ).encode()
    with (
        patch("mqtt_bridge.main.upsert_node", new=AsyncMock()) as mock_upsert,
        patch(
            "mqtt_bridge.main.get_confirmed_node_coords",
            new=AsyncMock(return_value=(38.123, -122.456)),
        ),
    ):
        await main_module.handle_status(mock_pool, "nodes/tbeam-01/status", payload)
    assert main_module._node_coords["tbeam-01"] == (38.123, -122.456)
    _, kwargs = mock_upsert.call_args
    assert kwargs["lat"] == 38.123
    assert kwargs["location_confirmed"] is True


@pytest.mark.asyncio
async def test_handle_status_firmware_static_coords_not_cached(mock_pool):
    """Firmware-reported node_lat/node_lon must not populate _node_coords."""
    payload = json.dumps(
        {
            "firmware_ver": "0.2.0",
            "ip": "10.0.0.3",
            "node_lat": 38.500,
            "node_lon": -122.900,
            "uptime_ms": 2000,
        }
    ).encode()
    with (
        patch("mqtt_bridge.main.upsert_node", new=AsyncMock()),
        patch("mqtt_bridge.main.get_confirmed_node_coords", new=AsyncMock(return_value=None)),
    ):
        await main_module.handle_status(mock_pool, "nodes/scanner-01/status", payload)
    assert "scanner-01" not in main_module._node_coords


@pytest.mark.asyncio
async def test_handle_status_confirmed_db_coords_are_cached(mock_pool):
    """After a status message, confirmed coords from DB are loaded into _node_coords."""
    payload = json.dumps(
        {"firmware_ver": "0.2.0", "ip": "10.0.0.3", "uptime_ms": 2000}
    ).encode()
    with (
        patch("mqtt_bridge.main.upsert_node", new=AsyncMock()),
        patch(
            "mqtt_bridge.main.get_confirmed_node_coords",
            new=AsyncMock(return_value=(51.500, -0.100)),
        ),
    ):
        await main_module.handle_status(mock_pool, "nodes/scanner-02/status", payload)
    assert main_module._node_coords["scanner-02"] == (51.500, -0.100)


@pytest.mark.asyncio
async def test_handle_status_no_gps_fix_does_not_cache(mock_pool):
    payload = json.dumps(
        {"firmware_ver": "0.1.0", "ip": "10.0.0.2", "gps_fix": False, "uptime_ms": 500}
    ).encode()
    with (
        patch("mqtt_bridge.main.upsert_node", new=AsyncMock()),
        patch("mqtt_bridge.main.get_confirmed_node_coords", new=AsyncMock(return_value=None)),
    ):
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

    with (
        patch("mqtt_bridge.main.upsert_devices", new=AsyncMock()),
        patch("mqtt_bridge.main.insert_scan_events", new=capture_events),
    ):
        await main_module.handle_scan(mock_pool, "nodes/scanner-01/scan/wifi", payload)

    assert len(stamped_events) == 1
    assert stamped_events[0].node_lat == 38.123
    assert stamped_events[0].node_lon == -122.456


@pytest.mark.asyncio
async def test_handle_scan_unconfirmed_node_drops_scan(mock_pool):
    """Scans from nodes with no confirmed location are dropped entirely."""
    # scanner-99 has no entry in _node_coords
    payload = json.dumps(
        [{"ssid": "Net", "bssid": "bb:cc:dd:ee:ff:00", "rssi": -70, "channel": 1}]
    ).encode()
    mock_upsert_devices = AsyncMock()
    mock_insert_events = AsyncMock()
    with (
        patch("mqtt_bridge.main.upsert_devices", new=mock_upsert_devices),
        patch("mqtt_bridge.main.insert_scan_events", new=mock_insert_events),
    ):
        await main_module.handle_scan(mock_pool, "nodes/scanner-99/scan/wifi", payload)
    mock_upsert_devices.assert_not_called()
    mock_insert_events.assert_not_called()
```

- [ ] **Step 2: Run tests to verify the changed ones fail**

```bash
cd server/mqtt_bridge && python -m pytest tests/test_main.py -v
```

Expected: Several FAILs against the current main.py implementation

- [ ] **Step 3: Replace main.py**

Replace the entire content of `server/mqtt_bridge/src/mqtt_bridge/main.py` with:

```python
from __future__ import annotations

import asyncio
import json
import logging

import aiomqtt
import asyncpg

from mqtt_bridge.config import DB_URL, MQTT_HOST, MQTT_PORT
from mqtt_bridge.db import (
    get_confirmed_node_coords,
    insert_scan_events,
    load_confirmed_node_coords,
    upsert_devices,
    upsert_node,
)
from mqtt_bridge.estimator import run_estimator
from mqtt_bridge.handler import extract_node_id, parse_ble, parse_wifi

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger(__name__)

# Populated from confirmed DB records at startup and refreshed on each status message.
# Only nodes with location_confirmed=true in the DB ever appear here.
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
    if coords is None:
        log.debug("node=%s has no confirmed location — scan dropped", node_id)
        return

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
    location_confirmed = False
    if data.get("gps_fix") and "gps_lat" in data:
        lat, lon = float(data["gps_lat"]), float(data["gps_lon"])
        location_confirmed = True
    # Firmware-reported node_lat/node_lon are intentionally ignored.
    # Location for fixed nodes is only confirmed by the user via PATCH /nodes/{id}.

    await upsert_node(
        pool,
        node_id,
        firmware_ver=data.get("firmware_ver", ""),
        ip=data.get("ip", ""),
        lat=lat,
        lon=lon,
        location_confirmed=location_confirmed,
    )

    # Refresh this node's confirmed coords from DB (picks up API-set locations too).
    coords = await get_confirmed_node_coords(pool, node_id)
    if coords:
        _node_coords[node_id] = coords

    log.info("node=%s status uptime_ms=%s lat=%s lon=%s", node_id, data.get("uptime_ms"), lat, lon)


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

    confirmed = await load_confirmed_node_coords(pool)
    _node_coords.update(confirmed)
    log.info("Loaded %d confirmed node location(s) from DB", len(confirmed))

    await run(pool)
```

- [ ] **Step 4: Run all mqtt_bridge tests**

```bash
cd server/mqtt_bridge && python -m pytest tests/ -v
```

Expected: All PASS

- [ ] **Step 5: Run ruff**

```bash
cd server && ruff check mqtt_bridge/ && ruff format --check mqtt_bridge/
```

Expected: No issues

- [ ] **Step 6: Commit**

```bash
git add server/mqtt_bridge/src/mqtt_bridge/main.py server/mqtt_bridge/tests/test_main.py
git commit -m "feat: gate scans on confirmed node location, ignore firmware-reported coords"
```

---

## Chunk 2: API

### Task 4: API — set location_confirmed on PATCH and expose in responses

**Files:**
- Modify: `server/api/src/api/models.py`
- Modify: `server/api/src/api/routers/nodes.py`
- Modify: `server/api/tests/test_nodes.py`

`server/api/tests/test_nodes.py` already exists with 5 passing tests. Do not replace it — update it in place.

- [ ] **Step 1: Update the existing test fixtures and add two new tests**

In `server/api/tests/test_nodes.py`:

**1a.** Add `"location_confirmed": True` to both `NODE_ROW` and `UPDATED_ROW`:

```python
NODE_ROW = {
    "node_id": "scanner-01",
    "node_type": "wifi",
    "location": "garage",
    "last_seen": NOW,
    "firmware_ver": "1.0.0",
    "lat": 51.5,
    "lon": -0.1,
    "name": None,
    "location_confirmed": True,
}

UPDATED_ROW = {**NODE_ROW, "name": "Garage Scanner", "lat": 51.6, "lon": -0.2}
```

**1b.** Append two new tests at the end of the file:

```python
def test_list_nodes_includes_location_confirmed(client_nodes_list):
    client, _ = client_nodes_list
    resp = client.get("/nodes")
    assert resp.status_code == 200
    assert "location_confirmed" in resp.json()[0]
    assert resp.json()[0]["location_confirmed"] is True


def test_patch_node_sets_location_confirmed_true(client_nodes_patch):
    client, conn = client_nodes_patch
    resp = client.patch(
        "/nodes/scanner-01",
        json={"name": "Garage Scanner", "lat": 51.6, "lon": -0.2},
    )
    assert resp.status_code == 200
    sql = conn.fetchrow.call_args[0][0]
    assert "location_confirmed" in sql.lower()
    assert "true" in sql.lower()
```

- [ ] **Step 2: Run to verify the new tests fail (existing tests may also fail due to missing model field)**

```bash
cd server/api && python -m pytest tests/test_nodes.py -v
```

Expected: The two new tests FAIL; existing tests may also fail with Pydantic validation error because `location_confirmed` is not yet in the model or SELECT

- [ ] **Step 3: Add location_confirmed to NodeResponse in models.py**

In `server/api/src/api/models.py`, add `location_confirmed: bool` as the last field of `NodeResponse`:

```python
class NodeResponse(BaseModel):
    node_id: str
    node_type: str
    location: str | None
    last_seen: datetime
    firmware_ver: str
    lat: float | None
    lon: float | None
    name: str | None
    location_confirmed: bool
```

- [ ] **Step 4: Update nodes.py — add field to SELECT and set in UPDATE**

In `server/api/src/api/routers/nodes.py`, update `_NODE_SELECT`:

```python
_NODE_SELECT = (
    "SELECT node_id, node_type, location, last_seen, firmware_ver, lat, lon, name, location_confirmed FROM nodes"
)
```

Update the `UPDATE` query inside `update_node`:

```python
        row = await conn.fetchrow(
            """
            UPDATE nodes
            SET name = $1, lat = $2, lon = $3, location_confirmed = true
            WHERE node_id = $4
            RETURNING *
            """,
            body.name,
            body.lat,
            body.lon,
            node_id,
        )
```

- [ ] **Step 5: Run all API tests**

```bash
cd server/api && python -m pytest tests/ -v
```

Expected: All PASS

- [ ] **Step 6: Run ruff**

```bash
cd server && ruff check api/ && ruff format --check api/
```

Expected: No issues

- [ ] **Step 7: Commit**

```bash
git add server/api/src/api/models.py server/api/src/api/routers/nodes.py server/api/tests/test_nodes.py
git commit -m "feat: expose location_confirmed in node API and set it on PATCH"
```

---

## Chunk 3: Map UI

### Task 5: api.ts — add location_confirmed to NodeResponse type

**Files:**
- Modify: `web/src/lib/api.ts`

- [ ] **Step 1: Add field to NodeResponse**

In `web/src/lib/api.ts`, update `NodeResponse` to add `location_confirmed`:

```typescript
export type NodeResponse = {
  node_id: string;
  node_type: string;
  location: string | null;
  last_seen: string;
  firmware_ver: string;
  lat: number | null;
  lon: number | null;
  name: string | null;
  location_confirmed: boolean;
};
```

- [ ] **Step 2: Type-check**

```bash
cd web && npm run check
```

Expected: No new errors

- [ ] **Step 3: Commit**

```bash
git add web/src/lib/api.ts
git commit -m "feat: add location_confirmed to NodeResponse type"
```

---

### Task 6: Map page — unlocated nodes panel + placement mode

**Files:**
- Modify: `web/src/routes/map/+page.svelte`

Apply the following changes in sequence. Read the file first to confirm line numbers before each edit.

- [ ] **Step 1: Add placement-mode state variables**

In the `<script>` section, after the line `let saving = false;`, add:

```typescript
  // ── Placement mode state ──────────────────────────────────────────────────────
  let unlocatedNodes: NodeResponse[] = [];
  let pendingNodeId: string | null = null;
  let isNewPlacement = false;
  let placementClickHandler: ((e: LeafletMouseEvent) => void) | null = null;
```

- [ ] **Step 2: Update loadNodes to collect unlocated nodes**

Replace the `loadNodes` function body so it separates confirmed nodes (get markers) from unconfirmed ones (go to `unlocatedNodes`):

```typescript
  async function loadNodes() {
    if (!map) return;
    const L = await import("leaflet");
    const nodes: NodeResponse[] = await fetchNodes();
    unlocatedNodes = [];

    for (const node of nodes) {
      nodeData.set(node.node_id, node);
      if (!node.location_confirmed || node.lat == null || node.lon == null) {
        unlocatedNodes.push(node);
        continue;
      }

      const color = nodeColor(node);
      const icon = await makeNodeIcon(color);
      const label = node.name ?? node.node_id;

      const marker = L.marker([node.lat, node.lon], { icon })
        .bindTooltip(label, { permanent: false })
        .addTo(map!);

      marker.on("click", () => openPanel(nodeData.get(node.node_id) ?? node));
      nodeMarkers.set(node.node_id, marker);
    }
  }
```

- [ ] **Step 3: Add cancelPlacement function**

After the `toggleGps` function, add:

```typescript
  function cancelPlacement() {
    if (placementClickHandler && map) {
      map.off("click", placementClickHandler);
      placementClickHandler = null;
    }
    if (map) map.getContainer().style.cursor = "";
    pendingNodeId = null;
  }
```

- [ ] **Step 4: Add startPlacement function**

After `cancelPlacement`, add:

```typescript
  async function startPlacement(node: NodeResponse) {
    if (!map) return;
    if (selectedNode) runCleanup({ restorePosition: true });
    if (pendingNodeId) cancelPlacement();

    pendingNodeId = node.node_id;
    map.getContainer().style.cursor = "crosshair";

    placementClickHandler = async (e: LeafletMouseEvent) => {
      if (!map) return;
      map.off("click", placementClickHandler!);
      placementClickHandler = null;
      map.getContainer().style.cursor = "";
      pendingNodeId = null;

      const L = await import("leaflet");
      const icon = await makeNodeIcon("#facc15");
      const marker = L.marker([e.latlng.lat, e.latlng.lng], { icon })
        .bindTooltip(node.name ?? node.node_id, { permanent: false })
        .addTo(map!);
      marker.on("click", () => openPanel(nodeData.get(node.node_id)!));
      nodeMarkers.set(node.node_id, marker);

      const provisionalNode: NodeResponse = { ...node, lat: e.latlng.lat, lon: e.latlng.lng };
      nodeData.set(node.node_id, provisionalNode);

      isNewPlacement = true;
      // openPanel sets gpsUnlocked=false; toggleGps() must be called after it
      // to start the new placement with GPS already unlocked.
      openPanel(provisionalNode);
      toggleGps();
    };

    map.on("click", placementClickHandler);
  }
```

- [ ] **Step 5: Update runCleanup to handle new-placement cancellation**

Inside `runCleanup`, replace the `if (restorePosition && marker)` block (and the following `isDragging = false; gpsUnlocked = false; closePanel()` lines) with:

```typescript
    if (restorePosition && marker) {
      if (isNewPlacement) {
        marker.remove();
        nodeMarkers.delete(selectedNode!.node_id);
      } else {
        marker.setLatLng([originalLat, originalLon]);
        editLat = originalLat;
        editLon = originalLon;
      }
    }

    isNewPlacement = false;
    isDragging = false;
    gpsUnlocked = false;
    closePanel();
```

- [ ] **Step 6: Update handleSave to remove from unlocatedNodes and refresh icon**

In `handleSave`, locate the existing block inside the `try {`:

```typescript
      const marker = nodeMarkers.get(updated.node_id);
      if (marker) {
        marker.setLatLng([updated.lat!, updated.lon!]);
        marker.getTooltip()?.setContent(updated.name ?? updated.node_id);
      }

      nodeData.set(updated.node_id, updated);
      runCleanup({ restorePosition: false });
```

Replace it with (add `setIcon` and the `unlocatedNodes` filter; keep `nodeData.set` and `runCleanup` in place):

```typescript
      const marker = nodeMarkers.get(updated.node_id);
      if (marker) {
        marker.setLatLng([updated.lat!, updated.lon!]);
        marker.getTooltip()?.setContent(updated.name ?? updated.node_id);
        const newIcon = await makeNodeIcon(nodeColor(updated));
        marker.setIcon(newIcon);
      }

      nodeData.set(updated.node_id, updated);
      unlocatedNodes = unlocatedNodes.filter((n) => n.node_id !== updated.node_id);
      runCleanup({ restorePosition: false });
```

Do not touch the `} catch` or `} finally` blocks that follow.

- [ ] **Step 7: Add placementClickHandler cleanup to onDestroy**

In `onDestroy`, after `if (escapeHandler) document.removeEventListener("keydown", escapeHandler);`, add:

```typescript
    if (placementClickHandler && map) map.off("click", placementClickHandler);
```

- [ ] **Step 8: Add the "Needs placement" panel to the template**

Inside the `<div class="relative flex-1 z-0">` block, after the `{#if selectedNode}...{/if}` floating edit panel, add:

```svelte
    <!-- Nodes without confirmed location -->
    {#if unlocatedNodes.filter((n) => n.node_id !== selectedNode?.node_id).length > 0}
      <div class="absolute z-[1000] top-4 right-4 w-56 bg-zinc-900 border border-amber-600 rounded-lg shadow-xl p-3 text-sm">
        {#if pendingNodeId}
          <p class="text-amber-400 text-xs mb-2">
            Click map to place <span class="font-mono">{nodeData.get(pendingNodeId)?.name ?? pendingNodeId}</span>
          </p>
          <button
            class="w-full text-xs text-zinc-400 hover:text-zinc-200 py-1 border border-zinc-700 rounded"
            onclick={cancelPlacement}
          >Cancel</button>
        {:else}
          <p class="text-amber-400 text-xs font-semibold mb-2">Needs placement</p>
          {#each unlocatedNodes.filter((n) => n.node_id !== selectedNode?.node_id) as node}
            <div class="flex items-center justify-between py-1">
              <span class="font-mono text-xs text-zinc-300 truncate">{node.name ?? node.node_id}</span>
              <button
                class="ml-2 text-xs px-2 py-0.5 rounded border border-amber-600 text-amber-400 hover:bg-amber-900/30 shrink-0"
                onclick={() => startPlacement(node)}
              >Place</button>
            </div>
          {/each}
        {/if}
      </div>
    {/if}
```

- [ ] **Step 9: Type-check**

```bash
cd web && npm run check
```

Expected: No new errors

- [ ] **Step 10: Commit**

```bash
git add web/src/routes/map/+page.svelte
git commit -m "feat: show unlocated nodes on map with click-to-place flow"
```

---

## Final: integration smoke-test

- [ ] **Step 1: Bring up the full stack**

```bash
cd server && docker compose up -d
```

- [ ] **Step 2: Verify existing confirmed nodes work**

Navigate to the map page. Nodes with `location_confirmed=true` in the DB should appear as normal markers. No "Needs placement" panel should appear if all nodes are confirmed.

- [ ] **Step 3: Verify unconfirmed nodes appear in the panel**

Connect a node that has no confirmed location (or manually set `location_confirmed=false` for a test node via SQL). The amber "Needs placement" panel should appear in the top-right of the map.

- [ ] **Step 4: Verify placement flow**

Click "Place" for the unconfirmed node. Cursor changes to crosshair. Click somewhere on the map. A yellow marker appears and the edit panel opens with GPS unlocked. Adjust position and name, click Save. The marker turns green (if the node is recently active), the "Needs placement" panel entry disappears.

- [ ] **Step 5: Verify scans are gated**

While a node has no confirmed location, confirm no new rows appear in `scan_events` for that node:

```sql
SELECT count(*) FROM scan_events WHERE node_id = '<your-node-id>' AND time > now() - interval '1 minute';
```

Expected: 0 rows while unconfirmed; rows start appearing after confirming.
