# Node Editing on Map — Design Spec

**Date:** 2026-03-13
**Status:** Approved

## Overview

Add the ability to edit node display names and GPS coordinates directly from the Map page. Nodes keep their immutable technical `node_id` (primary key); a new `name` field provides a human-friendly label. GPS coordinates can be set by typing, dragging a marker, or clicking on the map.

## Scope Constraints

- Only nodes that already have lat/lon coordinates appear as markers on the map and are selectable for editing. Nodes without coordinates are not shown on the map and are out of scope for this feature.
- The Nodes list page (`/nodes`) remains read-only.
- No authentication on the new `PATCH` endpoint.
- No real-time broadcast of node edits to other WebSocket clients.
- `node_id` itself is never modified (immutable PK).
- Clearing existing coordinates back to null is not a supported operation (no UI control exists for it).

## Data Model

### DB Migration

One idempotent column addition appended to `server/sql/init.sql`:

```sql
ALTER TABLE nodes ADD COLUMN IF NOT EXISTS name TEXT;
```

`name` is nullable. The UI shows `name` when set, falls back to `node_id` everywhere.

**Existing deployments:** `init.sql` only runs automatically on a fresh TimescaleDB data directory. For existing deployments, run the `ALTER TABLE` statement manually (e.g. `docker exec -it <db-container> psql -U <user> -d <db> -c "ALTER TABLE nodes ADD COLUMN IF NOT EXISTS name TEXT;"`). The `IF NOT EXISTS` guard makes it safe to run multiple times.

### API Changes

**`NodeResponse`** gains one new field: `name: str | None`. This is included in the existing `GET /nodes` response automatically. The SvelteKit frontend's `NodeResponse` type in `api.ts` must be updated to add `name: string | null` alongside this deployment, otherwise `tsc --noEmit` will fail.

**New `NodeUpdate` model:**

```python
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Annotated

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
            raise ValueError("lat and lon are required and cannot be cleared via this endpoint")
        return self
```

Validation notes:
- `mode="before"` on `_trim_name` means trimming happens before `max_length` is enforced, so leading/trailing whitespace is stripped first.
- The `_lat_lon_rules` validator rejects both-null and mismatched lat/lon. The endpoint cannot be used to clear coordinates.
- `name: null` (after trimming) is valid — it clears the display name back to unset.

**New endpoint:**
```
PATCH /nodes/{node_id}
Body: NodeUpdate (JSON)
Response: NodeResponse (updated record)
```

Implementation:
1. Execute `UPDATE nodes SET name=$1, lat=$2, lon=$3 WHERE node_id=$4 RETURNING *`.
2. The server always returns exactly the values written. No DB triggers or transforms are applied.
3. If the `RETURNING` clause produces no row, return HTTP 404.

## Frontend API Client (`web/src/lib/api.ts`)

- Extend `NodeResponse` type: add `name: string | null`
- Add function:
  ```ts
  export async function updateNode(
    nodeId: string,
    patch: { name: string | null; lat: number; lon: number }
  ): Promise<NodeResponse>
  ```
  Calls `PATCH /nodes/{nodeId}` with JSON body. `lat` and `lon` are always required numbers (the UI is only reachable on nodes that have coordinates).

## Map Page UX (`web/src/routes/map/+page.svelte`)

### Node Marker Type

Node markers are changed from `L.circleMarker()` to `L.marker()` with a custom `L.divIcon()`. This is required because `L.circleMarker()` does not support dragging; `L.marker()` does. The DivIcon renders a small filled circle via an inline `<div>` with `border-radius: 50%` CSS, sized and coloured using the same staleness logic as before (green/yellow/grey). Visually the markers appear identical to the current implementation.

### Node Marker Behaviour

- Clicking a marker opens the edit panel for that node. Panel state (name input, lat/lon inputs, unlock state) is initialised from the clicked node's data.
- Clicking a different node marker while a panel is open: run the full Cancel cleanup sequence (see below), then open the new panel.
- Pressing Escape: run the full Cancel cleanup sequence.
- The marker tooltip shows `name` when set, `node_id` otherwise.

### Floating Edit Panel

An absolutely-positioned `<div>` rendered inside the Leaflet map container element (not a Leaflet popup). On panel open and on every Leaflet `move` and `zoom` event, the panel is repositioned to appear centred above the selected node's marker:

```ts
const pt = map.latLngToContainerPoint(marker.getLatLng());
panel.style.left = `${pt.x}px`;
panel.style.top  = `${pt.y - PANEL_HEIGHT - 12}px`;
```

Repositioning is suppressed while a marker drag is in progress (between `dragstart` and `dragend`). The panel repositions once after `dragend`.

**Panel contents:**

| Element | Behaviour |
|---|---|
| Header | `node_id` in monospace, read-only |
| Name input | Text field, always editable. Placeholder: `node_id`. Max 100 chars enforced client-side. |
| Lat input | Number field. `readonly` attribute when GPS locked. |
| Lon input | Number field. `readonly` attribute when GPS locked. |
| Lock / Unlock button | Toggles GPS editing mode. |
| Save | Builds patch, calls `updateNode`, handles response. |
| Cancel / × | Runs full Cancel cleanup, closes panel. |

### GPS Unlock Mode

**On Unlock:**
1. `marker.dragging.enable()`
2. `map.getContainer().style.cursor = 'crosshair'`
3. Attach a `dragstart` listener to the marker that sets a boolean `isDragging = true`.
4. Attach a `dragend` listener to the marker that sets `isDragging = false`, then updates the lat/lon inputs from `marker.getLatLng()`.
5. Attach a `click` listener to the Leaflet map. On each click: if `isDragging` is true, ignore (suppress the post-drag click that some Leaflet versions emit); otherwise move the marker to the clicked latlng and update the lat/lon inputs. The listener stays active until lock/save/cancel.

**Full lock/cleanup sequence** (runs on Lock button, Save, Cancel, Escape, and node-switch):
1. Remove the document `keydown` Escape listener.
2. `marker.dragging.disable()`
3. `map.getContainer().style.cursor = ''`
4. Remove the map `click` listener.
5. Remove the marker `dragend` and `dragstart` listeners.
6. If Cancel / Escape / node-switch (not Save): `marker.setLatLng(originalLatLng)` and restore the lat/lon inputs to the original values. Reset `isDragging = false`.

### Save Flow

1. Trim the name input value. If empty after trim, send as `null`.
2. Read the current lat/lon input values as numbers.
3. Call `updateNode(node.node_id, { name, lat, lon })`.
4. **On success:**
   - `marker.setLatLng([response.lat, response.lon])` (server echoes what was sent; this keeps state consistent).
   - Update the marker tooltip to the returned `name ?? node_id`.
   - Update the stored node entry in the local `nodes` array so the panel shows fresh values if reopened.
   - Run the full lock/cleanup sequence (step 1–5; step 6 is skipped since position is already correct).
   - Close and remove the panel element.
5. **On error:** Display an inline error message in the panel. Do not close or reset anything.

### Escape Key Listener

When a panel opens, attach a single `keydown` listener to `document` that runs the full Cancel cleanup sequence on `key === 'Escape'`. This listener is always the first thing removed in the cleanup sequence, ensuring only one listener is ever active at a time.
