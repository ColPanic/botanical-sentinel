# Node Editing on Map — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users edit a node's display name and GPS coordinates from a floating panel on the Map page.

**Architecture:** Backend adds a `name` column to `nodes` and a `PATCH /nodes/{node_id}` endpoint. Frontend extends the `NodeResponse` type and replaces `L.circleMarker` node markers with draggable `L.marker` + DivIcon markers; clicking a marker opens an absolutely-positioned edit panel that supports typing, drag, and click-to-place for GPS.

**Tech Stack:** Python/FastAPI/asyncpg/Pydantic v2, SvelteKit, Leaflet, TypeScript strict mode.

---

## Chunk 1: Backend

### Task 1: DB Migration

**Files:**
- Modify: `server/sql/init.sql`

- [ ] **Step 1: Append the migration to `init.sql`**

Add this line at the end of `server/sql/init.sql`:

```sql
ALTER TABLE nodes ADD COLUMN IF NOT EXISTS name TEXT;
```

- [ ] **Step 2: Verify the SQL is syntactically valid**

```bash
docker exec -i $(docker compose -f server/docker-compose.yml ps -q db) \
  psql -U sentinel -d sentinel -c "ALTER TABLE nodes ADD COLUMN IF NOT EXISTS name TEXT;"
```

Expected: `ALTER TABLE` (or `NOTICE: column "name" of relation "nodes" already exists, skipping`).

- [ ] **Step 3: Commit**

```bash
git add server/sql/init.sql
git commit -m "feat: add name column to nodes table"
```

---

### Task 2: Extend Models

**Files:**
- Modify: `server/api/src/api/models.py`

- [ ] **Step 1: Add `name` to `NodeResponse` and add `NodeUpdate`**

Replace the contents of `server/api/src/api/models.py` with:

```python
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator


class NodeResponse(BaseModel):
    node_id: str
    node_type: str
    location: str | None
    last_seen: datetime
    firmware_ver: str
    lat: float | None
    lon: float | None
    name: str | None


class NodeUpdate(BaseModel):
    name: Annotated[str, Field(max_length=100)] | None = None
    lat: float | None = None
    lon: float | None = None

    @field_validator("name", mode="before")
    @classmethod
    def _trim_name(cls, v: object) -> object:
        if isinstance(v, str):
            v = v.strip()
            return v if v else None
        return v

    @model_validator(mode="after")
    def _lat_lon_rules(self) -> "NodeUpdate":
        has_lat = self.lat is not None
        has_lon = self.lon is not None
        if has_lat != has_lon:
            raise ValueError("lat and lon must be provided together")
        if not has_lat and not has_lon:
            raise ValueError("lat and lon are required")
        return self


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


class DeviceResponse(BaseModel):
    mac: str
    device_type: str
    label: str | None
    tag: str
    first_seen: datetime
    last_seen: datetime
    vendor: str | None
    ssid: str | None


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

- [ ] **Step 2: Run the existing tests to confirm nothing is broken**

```bash
cd server && python -m pytest api/tests/ -q
```

Expected: all existing tests pass.

- [ ] **Step 3: Commit**

```bash
git add server/api/src/api/models.py
git commit -m "feat: add NodeUpdate model and name field to NodeResponse"
```

---

### Task 3: PATCH Endpoint

**Files:**
- Modify: `server/api/src/api/routers/nodes.py`
- Modify: `server/api/src/api/app.py` (CORS fix)

- [ ] **Step 1: Write the failing test first**

Create `server/api/tests/test_nodes.py`:

```python
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
```

- [ ] **Step 2: Run the tests — they should fail**

```bash
cd server && python -m pytest api/tests/test_nodes.py -q
```

Expected: failures mentioning missing endpoint or 405/422 responses.

- [ ] **Step 3: Add the PATCH endpoint to `nodes.py`**

Replace `server/api/src/api/routers/nodes.py` with:

```python
from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from api.app import get_pool
from api.models import NodeResponse, NodeUpdate

router = APIRouter(prefix="/nodes", tags=["nodes"])

_NODE_SELECT = (
    "SELECT node_id, node_type, location, last_seen, firmware_ver, lat, lon, name "
    "FROM nodes"
)


@router.get("", response_model=list[NodeResponse])
async def list_nodes(pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        rows = await conn.fetch(f"{_NODE_SELECT} ORDER BY last_seen DESC")
    return [dict(r) for r in rows]


@router.patch("/{node_id}", response_model=NodeResponse)
async def update_node(
    node_id: str,
    body: NodeUpdate,
    pool: asyncpg.Pool = Depends(get_pool),
):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE nodes SET name=$1, lat=$2, lon=$3 WHERE node_id=$4 RETURNING *",
            body.name,
            body.lat,
            body.lon,
            node_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Node not found")
    return dict(row)
```

- [ ] **Step 4: Fix CORS to allow PATCH requests**

In `server/api/src/api/app.py`, update the `allow_methods` line:

Old:
```python
    allow_methods=["GET", "PUT"],
```

New:
```python
    allow_methods=["GET", "PUT", "PATCH"],
```

- [ ] **Step 5: Run the new tests — they should pass**

```bash
cd server && python -m pytest api/tests/test_nodes.py -q
```

Expected: all 5 tests pass.

- [ ] **Step 6: Run the full test suite to check for regressions**

```bash
cd server && python -m pytest api/tests/ -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add server/api/src/api/routers/nodes.py server/api/src/api/app.py server/api/tests/test_nodes.py
git commit -m "feat: add PATCH /nodes/{node_id} endpoint for name and GPS editing"
```

---

## Chunk 2: Frontend

### Task 4: Frontend API Client

**Files:**
- Modify: `web/src/lib/api.ts`

- [ ] **Step 1: Extend `NodeResponse` and add `updateNode`**

In `web/src/lib/api.ts`, make these two changes:

Replace the `NodeResponse` type:
```ts
export type NodeResponse = {
  node_id: string;
  node_type: string;
  location: string | null;
  last_seen: string;
  firmware_ver: string;
  lat: number | null;
  lon: number | null;
  name: string | null;
};
```

Add `updateNode` after `fetchNodes`:
```ts
export async function updateNode(
  nodeId: string,
  patch: { name: string | null; lat: number; lon: number },
): Promise<NodeResponse> {
  const res = await fetch(`${BASE}/nodes/${encodeURIComponent(nodeId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error(`PATCH /nodes/${nodeId} failed: ${res.status}`);
  return res.json();
}
```

- [ ] **Step 2: Run type-check**

```bash
cd web && npm run check
```

Expected: no TypeScript errors.

- [ ] **Step 3: Commit**

```bash
git add web/src/lib/api.ts
git commit -m "feat: add updateNode API client and name field to NodeResponse"
```

---

### Task 5: Map Page — Node Editing UI

**Files:**
- Modify: `web/src/routes/map/+page.svelte`

This task replaces the map page with a version that converts node markers to draggable `L.marker` + DivIcon, adds the floating edit panel, and wires up all the editing interactions.

- [ ] **Step 1: Replace `web/src/routes/map/+page.svelte`**

```svelte
<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import type { Map as LeafletMap, Marker, Polyline, LeafletMouseEvent } from "leaflet";
  import "leaflet/dist/leaflet.css";
  import {
    liveWebSocket,
    fetchActivePositions,
    fetchPositionHistory,
    fetchNodes,
    updateNode,
  } from "$lib/api";
  import type { PositionResponse, NodeResponse } from "$lib/api";
  import type { CircleMarker } from "leaflet";

  let mapEl: HTMLDivElement;
  let map: LeafletMap | undefined;
  let connected = false;
  let ws: WebSocket | undefined;
  let windowMinutes = 5;
  let showIgnored = false;

  // Map state
  const deviceMarkers = new Map<string, CircleMarker>();
  const nodeMarkers = new Map<string, Marker>();
  const nodeData = new Map<string, NodeResponse>();
  const trailLines = new Map<string, Polyline>();

  const TAG_COLORS: Record<string, string> = {
    unknown: "#facc15",
    known_resident: "#4ade80",
    known_vehicle: "#60a5fa",
    ignored: "#71717a",
  };

  // ── Edit panel state ────────────────────────────────────────────────────────
  let panelEl: HTMLDivElement | undefined;
  let selectedNode: NodeResponse | null = null;
  let editName = "";
  let editLat = 0;
  let editLon = 0;
  let originalLat = 0;
  let originalLon = 0;
  let gpsUnlocked = false;
  let isDragging = false;
  let saveError: string | null = null;
  let saving = false;

  // Stored listener refs for cleanup
  let mapClickHandler: ((e: LeafletMouseEvent) => void) | null = null;
  let dragStartHandler: (() => void) | null = null;
  let dragEndHandler: (() => void) | null = null;
  let escapeHandler: ((e: KeyboardEvent) => void) | null = null;

  // ── Marker helpers ──────────────────────────────────────────────────────────
  function nodeColor(node: NodeResponse): string {
    const age = Date.now() - new Date(node.last_seen).getTime();
    return age < 120_000 ? "#4ade80" : age < 600_000 ? "#facc15" : "#71717a";
  }

  async function makeNodeIcon(color: string) {
    const L = await import("leaflet");
    return L.divIcon({
      className: "",
      html: `<div style="width:16px;height:16px;border-radius:50%;background:${color};border:2px solid rgba(0,0,0,0.3);box-sizing:border-box;"></div>`,
      iconSize: [16, 16],
      iconAnchor: [8, 8],
    });
  }

  // ── Map initialisation ──────────────────────────────────────────────────────
  async function initMap() {
    const L = await import("leaflet");
    map = L.map(mapEl).setView([0, 0], 2);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap contributors",
      maxZoom: 19,
    }).addTo(map);

    await loadNodes();
    await loadPositions();

    const allLatLngs = [
      ...Array.from(nodeMarkers.values()).map((m) => m.getLatLng()),
      ...Array.from(deviceMarkers.values()).map((m) => m.getLatLng()),
    ];
    if (allLatLngs.length > 0) {
      map.fitBounds(L.latLngBounds(allLatLngs), { padding: [40, 40] });
    }

    map.on("move zoom", repositionPanel);
  }

  async function loadNodes() {
    if (!map) return;
    const L = await import("leaflet");
    const nodes: NodeResponse[] = await fetchNodes();

    for (const node of nodes) {
      if (node.lat == null || node.lon == null) continue;
      nodeData.set(node.node_id, node);

      const color = nodeColor(node);
      const icon = await makeNodeIcon(color);
      const label = node.name ?? node.node_id;

      const marker = L.marker([node.lat, node.lon], { icon })
        .bindTooltip(label, { permanent: false })
        .addTo(map!);

      marker.on("click", () => openPanel(node));
      nodeMarkers.set(node.node_id, marker);
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
        .addTo(map!);
      marker.on("click", () => selectDevice(pos.mac));
      deviceMarkers.set(pos.mac, marker);
    }
  }

  async function selectDevice(mac: string) {
    if (!map) return;
    const L = await import("leaflet");
    if (trailLines.has(mac)) {
      trailLines.get(mac)!.remove();
      trailLines.delete(mac);
    }
    const history = await fetchPositionHistory(mac, 100);
    if (history.length < 2) return;
    const coords = history.map((p) => [p.lat, p.lon] as [number, number]);
    const trail = L.polyline(coords, { color: "#f97316", weight: 2, opacity: 0.8 }).addTo(map);
    trailLines.set(mac, trail);
  }

  function handleLiveEvent(data: unknown) {
    const event = data as { type?: string } & PositionResponse;
    if (event.type !== "position_update") return;
    if (event.tag === "ignored" && !showIgnored) return;
    updateDeviceMarker(event);
  }

  // ── Edit panel ──────────────────────────────────────────────────────────────
  function openPanel(node: NodeResponse) {
    if (selectedNode) runCleanup({ restorePosition: true });

    selectedNode = node;
    editName = node.name ?? "";
    editLat = node.lat!;
    editLon = node.lon!;
    originalLat = node.lat!;
    originalLon = node.lon!;
    saveError = null;
    gpsUnlocked = false;
    isDragging = false;

    escapeHandler = (e: KeyboardEvent) => {
      if (e.key === "Escape") runCleanup({ restorePosition: true });
    };
    document.addEventListener("keydown", escapeHandler);

    // Defer reposition until panel element is rendered
    requestAnimationFrame(repositionPanel);
  }

  function closePanel() {
    selectedNode = null;
    saveError = null;
    gpsUnlocked = false;
    isDragging = false;
  }

  function repositionPanel() {
    if (!map || !selectedNode || !panelEl || isDragging) return;
    const marker = nodeMarkers.get(selectedNode.node_id);
    if (!marker) return;
    const pt = map.latLngToContainerPoint(marker.getLatLng());
    const h = panelEl.offsetHeight || 160;
    panelEl.style.left = `${pt.x}px`;
    panelEl.style.top = `${pt.y - h - 12}px`;
    panelEl.style.transform = "translateX(-50%)";
  }

  function removeDragListeners(marker: Marker) {
    if (dragStartHandler) { marker.off("dragstart", dragStartHandler); dragStartHandler = null; }
    if (dragEndHandler) { marker.off("dragend", dragEndHandler); dragEndHandler = null; }
  }

  // Remove all editing listeners and optionally restore marker position.
  function runCleanup({ restorePosition }: { restorePosition: boolean }) {
    // 1. Escape listener
    if (escapeHandler) {
      document.removeEventListener("keydown", escapeHandler);
      escapeHandler = null;
    }

    if (!selectedNode) { closePanel(); return; }
    const marker = nodeMarkers.get(selectedNode.node_id);

    if (marker) {
      if (marker.dragging) marker.dragging.disable();
      removeDragListeners(marker);
      if (mapClickHandler && map) {
        map.off("click", mapClickHandler);
        mapClickHandler = null;
      }
    }
    if (map) map.getContainer().style.cursor = "";

    if (restorePosition && marker) {
      marker.setLatLng([originalLat, originalLon]);
      editLat = originalLat;
      editLon = originalLon;
    }

    isDragging = false;
    gpsUnlocked = false;
    closePanel();
  }

  function toggleGps() {
    if (!selectedNode || !map) return;
    const marker = nodeMarkers.get(selectedNode.node_id);
    if (!marker) return;

    if (gpsUnlocked) {
      // Lock GPS
      if (marker.dragging) marker.dragging.disable();
      removeDragListeners(marker);
      if (mapClickHandler) {
        map.off("click", mapClickHandler);
        mapClickHandler = null;
      }
      map.getContainer().style.cursor = "";
      gpsUnlocked = false;
    } else {
      // Unlock GPS
      if (marker.dragging) marker.dragging.enable();
      map.getContainer().style.cursor = "crosshair";

      dragStartHandler = () => { isDragging = true; };
      dragEndHandler = () => {
        isDragging = false;
        const ll = marker.getLatLng();
        editLat = ll.lat;
        editLon = ll.lng;
        repositionPanel();
      };
      marker.on("dragstart", dragStartHandler);
      marker.on("dragend", dragEndHandler);

      mapClickHandler = (e: LeafletMouseEvent) => {
        if (isDragging) return;
        marker.setLatLng([e.latlng.lat, e.latlng.lng]);
        editLat = e.latlng.lat;
        editLon = e.latlng.lng;
        repositionPanel();
      };
      map.on("click", mapClickHandler);
      gpsUnlocked = true;
    }
  }

  async function handleSave() {
    if (!selectedNode) return;
    saving = true;
    saveError = null;
    try {
      const name = editName.trim() || null;
      const updated = await updateNode(selectedNode.node_id, {
        name,
        lat: editLat,
        lon: editLon,
      });

      const marker = nodeMarkers.get(updated.node_id);
      if (marker) {
        marker.setLatLng([updated.lat!, updated.lon!]);
        marker.getTooltip()?.setContent(updated.name ?? updated.node_id);
      }

      nodeData.set(updated.node_id, updated);

      // Cleanup without restoring position (save succeeded)
      if (escapeHandler) {
        document.removeEventListener("keydown", escapeHandler);
        escapeHandler = null;
      }
      if (marker) {
        if (marker.dragging) marker.dragging.disable();
        removeDragListeners(marker);
      }
      if (mapClickHandler && map) {
        map.off("click", mapClickHandler);
        mapClickHandler = null;
      }
      if (map) map.getContainer().style.cursor = "";

      closePanel();
    } catch (e) {
      saveError = e instanceof Error ? e.message : "Save failed";
    } finally {
      saving = false;
    }
  }

  // ── Lifecycle ───────────────────────────────────────────────────────────────
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
    if (escapeHandler) document.removeEventListener("keydown", escapeHandler);
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
    <div class="flex items-center gap-3 ml-auto">
      {#each Object.entries(TAG_COLORS) as [tag, color]}
        <span class="flex items-center gap-1 text-xs text-zinc-400">
          <span class="inline-block w-3 h-3 rounded-full" style="background:{color}"></span>
          {tag.replace("_", " ")}
        </span>
      {/each}
    </div>
  </div>

  <!-- Map container (position:relative so the panel can be absolute inside it) -->
  <div class="relative flex-1 z-0">
    <div bind:this={mapEl} class="w-full h-full"></div>

    <!-- Floating edit panel -->
    {#if selectedNode}
      <div
        bind:this={panelEl}
        class="absolute z-[1000] w-64 bg-zinc-900 border border-zinc-700 rounded-lg shadow-xl p-3 text-sm"
        style="pointer-events:auto"
      >
        <!-- Header -->
        <div class="flex items-center justify-between mb-2">
          <span class="font-mono text-xs text-zinc-400">{selectedNode.node_id}</span>
          <button
            class="text-zinc-500 hover:text-zinc-200 text-base leading-none"
            onclick={() => runCleanup({ restorePosition: true })}
          >×</button>
        </div>

        <!-- Name -->
        <label class="block mb-3">
          <span class="text-zinc-400 text-xs">Display name</span>
          <input
            type="text"
            maxlength="100"
            placeholder={selectedNode.node_id}
            bind:value={editName}
            class="mt-0.5 w-full bg-zinc-800 border border-zinc-600 rounded px-2 py-1 text-zinc-100 text-sm focus:outline-none focus:border-zinc-400"
          />
        </label>

        <!-- GPS coordinates -->
        <div class="flex items-center justify-between mb-1">
          <span class="text-zinc-400 text-xs">GPS position</span>
          <button
            class="text-xs px-2 py-0.5 rounded border {gpsUnlocked
              ? 'border-amber-500 text-amber-400 hover:bg-amber-900/30'
              : 'border-zinc-600 text-zinc-400 hover:bg-zinc-700'}"
            onclick={toggleGps}
          >{gpsUnlocked ? "🔓 Lock" : "🔒 Unlock"}</button>
        </div>
        <div class="flex gap-2 mb-3">
          <label class="flex-1">
            <span class="text-zinc-500 text-xs">Lat</span>
            <input
              type="number"
              step="any"
              bind:value={editLat}
              readonly={!gpsUnlocked}
              class="w-full bg-zinc-800 border border-zinc-600 rounded px-2 py-1 text-zinc-100 text-xs focus:outline-none focus:border-zinc-400 disabled:opacity-50"
              class:opacity-50={!gpsUnlocked}
            />
          </label>
          <label class="flex-1">
            <span class="text-zinc-500 text-xs">Lon</span>
            <input
              type="number"
              step="any"
              bind:value={editLon}
              readonly={!gpsUnlocked}
              class="w-full bg-zinc-800 border border-zinc-600 rounded px-2 py-1 text-zinc-100 text-xs focus:outline-none focus:border-zinc-400 disabled:opacity-50"
              class:opacity-50={!gpsUnlocked}
            />
          </label>
        </div>

        {#if saveError}
          <p class="text-red-400 text-xs mb-2">{saveError}</p>
        {/if}

        <!-- Actions -->
        <div class="flex gap-2">
          <button
            class="flex-1 bg-zinc-700 hover:bg-zinc-600 text-zinc-200 rounded px-3 py-1.5 text-xs"
            onclick={() => runCleanup({ restorePosition: true })}
          >Cancel</button>
          <button
            disabled={saving}
            class="flex-1 bg-blue-700 hover:bg-blue-600 disabled:opacity-50 text-white rounded px-3 py-1.5 text-xs"
            onclick={handleSave}
          >{saving ? "Saving…" : "Save"}</button>
        </div>
      </div>
    {/if}
  </div>
</div>
```

- [ ] **Step 2: Run type-check**

```bash
cd web && npm run check
```

Expected: no TypeScript errors. Fix any that appear — they will be type narrowing issues from the Leaflet event types or `map.on` overloads.

- [ ] **Step 3: Build to confirm no build errors**

```bash
cd web && npm run build
```

Expected: build succeeds.

- [ ] **Step 4: Manual smoke test**

Start the dev server:
```bash
cd web && npm run dev
```

Open the Map page and verify:
1. Node markers appear as filled circles (same look as before).
2. Clicking a node marker opens the floating panel above it.
3. The panel shows the `node_id` in the header and an empty name field.
4. The Unlock button enables dragging — dragging the marker updates the lat/lon inputs.
5. Clicking on the map (while unlocked) moves the marker and updates inputs.
6. The Lock button re-locks GPS and resets the cursor.
7. Cancel closes the panel and restores the marker to its original position.
8. Save calls the API. With the server running, verify the change persists on page reload.
9. Pressing Escape closes the panel and restores position.
10. Opening a second marker while one panel is open closes the first cleanly.

- [ ] **Step 5: Commit**

```bash
git add web/src/routes/map/+page.svelte
git commit -m "feat: add node editing panel to map page"
```

---

## Final Step: Push

- [ ] **Push all commits**

```bash
git push
```
