# Device Triangulation & Position Tracking Design

**Date:** 2026-03-12
**Project:** botanical-sentinel
**Status:** Approved

## Overview

Scanner nodes spread across a ~3-acre rural property detect WiFi and BLE devices via passive RF
scanning. Each detection includes an RSSI reading. By combining simultaneous (or near-simultaneous)
detections from multiple nodes with known GPS positions, we can estimate where a detected device is
located on the property.

The primary use case is security: detect unknown devices arriving at the property, track their
movement, and distinguish regulars from intruders. Near-real-time position estimates (within one or
two 30-second scan cycles) are sufficient — sub-second latency is not required.

---

## Hardware Context

- **5+ scanner nodes** deployed across the property
- **Fixed nodes** (ESP32-S3 scanner): no onboard GPS; position set manually in `config.h`
- **Mobile nodes** (TTGO T-Beam): onboard u-blox NEO-M8N GPS; position updated live via status
  messages
- All nodes publish scan batches every 30 seconds over MQTT
- Future: sleeping nodes wake on detection signal from the first node to see a new device

---

## Architecture

### Data Flow

```
Node firmware
  → MQTT (nodes/<id>/scan/wifi|bt, nodes/<id>/status)
  → mqtt_bridge (stores scan_events with embedded node coords; updates node coords)
  → TimescaleDB
  → estimator task (runs every 30s, 90s sliding window)
  → position_estimates hypertable
  → pg_notify('position_estimates', ...)
  → FastAPI LISTEN loop → WebSocket broadcast
  → SvelteKit /map page (Leaflet, live WebSocket updates)
```

### Position Estimation Method

**Weighted centroid** (initial implementation):

```
weight_i = 10^(rssi_i / 10)   # linear power from dB
lat_est  = Σ(weight_i * node_lat_i) / Σ(weight_i)
lon_est  = Σ(weight_i * node_lon_i) / Σ(weight_i)
```

Higher RSSI → exponentially higher weight → estimated position pulled strongly toward the closest
node. Simple, robust to missing nodes, degrades gracefully to a single-node estimate.

**Method labels:**
- `single` — only one node saw the device in the window; position = node position
- `centroid` — two or more nodes contributed; weighted centroid used

**Sliding window:** 90 seconds (3 scan cycles). A device seen by node A at t=0 and node B at t=30
will be combined into a single estimate at t=30 or t=60 when the estimator next runs.

---

## Section 1: Database Schema

All schema changes go into `server/sql/init.sql` using `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
(matching the existing `devices.ssid` migration pattern) so the file remains idempotent.

### `nodes` table — add coordinates

```sql
ALTER TABLE nodes ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION;
ALTER TABLE nodes ADD COLUMN IF NOT EXISTS lon DOUBLE PRECISION;
```

Stores the current position of each node. For fixed nodes this is set once and never changes. For
T-Beams it is updated on every status message that carries a valid GPS fix. Used for map display
only. Not used as the source of truth for historical position computation (see scan_events below).

### `scan_events` table — embed node coordinates at write time

```sql
ALTER TABLE scan_events ADD COLUMN IF NOT EXISTS node_lat DOUBLE PRECISION;
ALTER TABLE scan_events ADD COLUMN IF NOT EXISTS node_lon DOUBLE PRECISION;
```

Node coordinates are stamped onto each scan event row when the mqtt_bridge writes it, using the
node's position at that moment (from the in-memory coord cache). This is the source of truth for
the estimator — it never looks up historical node positions from the `nodes` table, so T-Beam
movement never corrupts historical estimates.

Rows where `node_lat IS NULL` are excluded from triangulation (node position unknown at scan time).

### `position_estimates` hypertable — new

```sql
CREATE TABLE IF NOT EXISTS position_estimates (
    time        TIMESTAMPTZ      NOT NULL,
    mac         TEXT             NOT NULL,
    lat         DOUBLE PRECISION NOT NULL,
    lon         DOUBLE PRECISION NOT NULL,
    accuracy_m  REAL,
    node_count  INTEGER          NOT NULL,
    method      TEXT             NOT NULL   -- 'single' | 'centroid'
);

SELECT create_hypertable('position_estimates', by_range('time'), if_not_exists => TRUE);

-- Index required for efficient DISTINCT ON (mac) ORDER BY mac, time DESC queries
CREATE INDEX IF NOT EXISTS position_estimates_mac_time
    ON position_estimates (mac, time DESC);

SELECT add_retention_policy(
    'position_estimates',
    INTERVAL '30 days',
    if_not_exists => TRUE
);
```

One row per estimation run per device. Full movement history is preserved automatically via the
hypertable time-series structure. Latest position per device is queried with
`DISTINCT ON (mac) ORDER BY mac, time DESC`.

---

## Section 2: Firmware

### Fixed nodes (ESP32-S3 scanner)

Add to `config.h.example`:

```cpp
#define NODE_LAT  0.000000   // decimal degrees — set for fixed deployed nodes
#define NODE_LON  0.000000
```

Add to the status JSON payload published every 30s:

```json
{ "node_lat": 38.123456, "node_lon": -122.654321 }
```

No other firmware changes needed for fixed nodes.

### Mobile nodes (TTGO T-Beam)

No firmware changes. Already publishes `gps_lat`, `gps_lon`, `gps_fix` in status payload. Server
side begins persisting these (currently discarded in `handle_status`).

### Server-side coordinate rules

- Status with `gps_fix: true` → use `gps_lat`/`gps_lon` (T-Beam live GPS)
- Status with `node_lat`/`node_lon` → use those (fixed node config)
- Never overwrite existing coordinates with `NULL` — only write to DB when valid coords are present

---

## Section 3: mqtt_bridge

### `ScanEvent` dataclass — extend with node coordinates

`handler.py`: add two optional fields to `ScanEvent`:

```python
@dataclass
class ScanEvent:
    node_id:  str
    mac:      str
    rssi:     int
    scan_type: str
    ssid:     str | None
    time:     datetime
    node_lat: float | None = None   # node position at scan time
    node_lon: float | None = None
```

These are populated by `main.py` at write time (not by the parsers in `handler.py`).

### In-memory node coordinate cache — module-level in `main.py`

```python
# module-level in main.py — updated by handle_status, read by handle_scan
_node_coords: dict[str, tuple[float, float]] = {}
```

A module-level dict is appropriate here: `main.py` is a single-process asyncio app with no
threading, so there are no race conditions. Updated whenever a status message with valid coordinates
arrives. Read when writing scan event batches to stamp coordinates onto rows.

### `handle_status` changes

Parse and cache coordinates, then persist to `nodes`:

```python
async def handle_status(pool, topic, payload):
    node_id = extract_node_id(topic)
    data = json.loads(payload)

    # Extract coordinates — T-Beam (gps_fix) or fixed node (node_lat/node_lon)
    lat = lon = None
    if data.get("gps_fix") and "gps_lat" in data:
        lat, lon = float(data["gps_lat"]), float(data["gps_lon"])
    elif "node_lat" in data and "node_lon" in data:
        lat, lon = float(data["node_lat"]), float(data["node_lon"])

    if lat is not None:
        _node_coords[node_id] = (lat, lon)

    await upsert_node(pool, node_id,
                      firmware_ver=data.get("firmware_ver", ""),
                      ip=data.get("ip", ""),
                      lat=lat, lon=lon)
```

### `upsert_node` changes — `db.py`

Add `lat` and `lon` parameters. Only update the coordinate columns when non-None, using
`CASE WHEN` to avoid overwriting valid coordinates with NULL:

```python
async def upsert_node(pool, node_id, firmware_ver, ip, lat=None, lon=None):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO nodes (node_id, node_type, last_seen, firmware_ver,
                               lat, lon)
            VALUES ($1, 'scanner', now(), $2,
                    $3, $4)
            ON CONFLICT (node_id) DO UPDATE SET
                last_seen    = now(),
                firmware_ver = EXCLUDED.firmware_ver,
                lat = CASE WHEN $3 IS NOT NULL THEN $3 ELSE nodes.lat END,
                lon = CASE WHEN $4 IS NOT NULL THEN $4 ELSE nodes.lon END
        """, node_id, firmware_ver, lat, lon)
```

Note: `node_type` is currently hardcoded to `'scanner'`. T-Beam nodes should publish their type
in the status payload so `upsert_node` can store the correct value. This is a pre-existing issue
not introduced by this feature, but worth noting.

### `handle_scan` changes — stamp node coords onto events

After calling `parse_wifi` or `parse_ble`, stamp the cached node coordinates onto each event:

```python
async def handle_scan(pool, topic, payload):
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
    for e in events:
        if coords:
            e.node_lat, e.node_lon = coords

    await upsert_devices(pool, events)
    await insert_scan_events(pool, events)
```

### `insert_scan_events` changes — `db.py`

Include `node_lat` and `node_lon` in the `INSERT`:

```python
await conn.executemany("""
    INSERT INTO scan_events
        (time, node_id, mac, rssi, scan_type, ssid, node_lat, node_lon)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
""", [(e.time, e.node_id, e.mac, e.rssi, e.scan_type, e.ssid,
       e.node_lat, e.node_lon) for e in events])
```

### Estimator task

A new `async def run_estimator(pool)` coroutine runs every 30s. For each MAC seen in the last 90s
with at least one node that has coordinates:

```
every 30s:
  query:
    SELECT mac, node_lat, node_lon, MAX(rssi) AS rssi
    FROM scan_events
    WHERE time > now() - INTERVAL '90s'
      AND node_lat IS NOT NULL
    GROUP BY mac, node_lat, node_lon

  for each mac group:
    if node_count == 1:
      method = 'single'
      lat, lon = the single node's position
      accuracy_m = 10^((−59 − rssi) / (10 * 2.7))
                   # log-distance path loss: d = 10^((TxPower - RSSI) / (10 * n))
                   # TxPower default = −59 dBm at 1m; n = 2.7 (outdoor path loss)
    else:
      method = 'centroid'
      weights = [10^(rssi_i / 10) for each node]
      lat = Σ(w_i * lat_i) / Σ(w_i)
      lon = Σ(w_i * lon_i) / Σ(w_i)
      accuracy_m = weighted stddev of great-circle distances from estimate to each node
                   # stddev(dist_i, weight=w_i) — gives a rough error radius in metres

    INSERT INTO position_estimates (time, mac, lat, lon, accuracy_m, node_count, method)

  for each inserted row:
    await conn.execute("SELECT pg_notify('position_estimates', $1)", json_payload)
```

The estimator runs as a second `asyncio.Task` in `run()`, sharing the same DB pool with the MQTT
listener:

```python
async def run(pool):
    await asyncio.gather(
        run_mqtt(pool),
        run_estimator(pool),
    )
```

### Inter-process signaling — pg_notify (matching existing pattern)

The estimator and the WebSocket broadcaster live in separate processes (mqtt_bridge vs FastAPI).
The estimator fires `pg_notify('position_estimates', <json>)` — the same mechanism already used
for scan_events. The FastAPI `LISTEN` loop (in `routers/live.py`) adds a listener on the
`position_estimates` channel and broadcasts `position_update` events to connected WebSocket clients.
No new infrastructure is needed.

---

## Section 4: API

### Extended endpoint

**`GET /nodes`** — `NodeResponse` Pydantic model gains `lat: float | None` and `lon: float | None`.

### New endpoints

**`GET /positions/current`**
Latest position estimate per device. Uses `DISTINCT ON (mac) ORDER BY mac, time DESC`. Joined with
`devices` for label, tag, vendor metadata. Supports `?tag=` filter.

Response fields: `mac`, `lat`, `lon`, `accuracy_m`, `node_count`, `method`, `time`, `label`, `tag`,
`vendor`, `device_type`.

**`GET /positions/active?window_minutes=5`**
Devices with a position estimate in the last `window_minutes` minutes (default: 5). Same response
shape as `/current`. Used by the map to distinguish "currently present" from "was here earlier."

**`GET /positions/{mac}/history`**
Full position time-series for one device. Supports `?since=` (ISO timestamp) and `?limit=` (default
100). Returns chronological list for trail rendering.

### WebSocket `/live` extension

When the FastAPI `LISTEN` loop receives a `position_estimates` notification, it broadcasts:

```json
{
  "type": "position_update",
  "mac": "AA:BB:CC:DD:EE:FF",
  "lat": 38.1234,
  "lon": -122.6543,
  "accuracy_m": 25.0,
  "node_count": 3,
  "method": "centroid",
  "time": "2026-03-12T10:00:00Z"
}
```

The existing scan_events notification already uses this pattern. Adding a second channel requires
only adding a second `LISTEN 'position_estimates'` call in the existing listener setup.

---

## Section 5: Web UI

### New `/map` page

Leaflet.js map (OpenStreetMap tiles, no API key required). Auto-fits to the bounding box of all
known node positions on load.

**Node markers**
Fixed pins at each node's coordinates. Color by recency:
- Green: seen within 2 minutes
- Yellow: seen within 10 minutes
- Gray: offline / unknown position

Clicking a node shows a popup with node ID, last seen timestamp, and recent scan counts.

**Device circles**
One circle per device with a known position estimate. Center = estimated position, radius =
`accuracy_m`. Color by tag:
- Yellow: `unknown`
- Green: `known_resident`
- Blue: `known_vehicle`
- Gray: `ignored` (hidden by default)

**Movement trails**
Clicking a device circle loads `/positions/{mac}/history` and draws a polyline of the last 30
minutes of movement. Opacity fades from full (recent) to 20% (oldest), giving a visual sense of
direction and speed.

**Live updates**
WebSocket connection reacts to `position_update` events, moving circles in real-time without
polling.

**Filter bar**
Tag filter chips (same tags as the `/devices` page). `window_minutes` control to hide devices not
seen within N minutes (default: 5). Toggle to show/hide `ignored` devices.

### Navigation change

`/` becomes the map page (or redirects to `/map`). The map is the primary operational view.

---

## Out of Scope (this iteration)

- Trilateration (proper circle intersection for 3+ nodes) — weighted centroid is sufficient for
  now; can be added later without schema changes
- Wake-on-detection (sleeping nodes triggered by first-detect node) — firmware protocol TBD
- Per-device TxPower calibration for RSSI-to-distance accuracy improvement
- Camera / motion sensor integration
- Alerting / push notifications
- `node_type` field accuracy for T-Beam nodes — pre-existing issue, tracked separately
