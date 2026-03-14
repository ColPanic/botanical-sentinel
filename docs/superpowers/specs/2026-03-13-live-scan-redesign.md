# Live Scan Page Redesign

**Date:** 2026-03-13
**Status:** Approved

## Problem

The current Live Scan page displays raw scan counts per node (node_id, scan_type, count). This tells you a scan happened but nothing about what changed — it duplicates the Nodes tab without adding value.

## Goal

Show what is happening around the property that is **different from normal**: new devices never seen before, unknown visitors present right now, and known residents/vehicles arriving and departing.

## Scope

- Frontend: replace `web/src/routes/scan/+page.svelte` entirely
- Backend: one small change to `server/mqtt_bridge/src/mqtt_bridge/db.py` — expand the `pg_notify` payload to include device MACs
- No schema changes, no new API endpoints, no new database tables

---

## Backend Change

### `mqtt_bridge/db.py` — `insert_scan_events`

Change the `pg_notify` payload from:

```json
{ "node_id": "...", "scan_type": "wifi", "count": 12 }
```

to:

```json
{
  "node_id": "scanner-1",
  "scan_type": "wifi",
  "devices": [
    { "mac": "F8:ED:F8:77:52:63", "rssi": -68, "ssid": "HomeNet" },
    { "mac": "CB:1A:A5:67:45:56", "rssi": -75, "ssid": null }
  ]
}
```

The `devices` array contains one entry per scan event in the batch. RSSI and SSID are included because they are available at notify time and useful for display.

**Constraint:** PostgreSQL `pg_notify` payloads are limited to 8000 bytes. A batch of 20 devices at ~80 bytes each is ~1600 bytes — well within the limit. The existing `MQTT_MAX_PACKET_SIZE=4096` build flag caps batch size, so this is safe.

---

## Frontend Design

### Page Layout (stacked, single column)

```
┌─────────────────────────────────────┐
│ Live Scan                ● connected │
├────────────┬────────────┬────────────┤
│  3  NEW    │ 14 UNKNOWN │  2  KNOWN  │
├────────────┴────────────┴────────────┤
│ RECENT EVENTS                        │
│  NEW ↑  F8:ED:F8:77   Apple   now   │
│  RES ↑  Alice's iPhone         4m   │
│  VEH ↓  Tesla Model 3          8m   │
│  NEW ↓  CB:1A:A5:67            11m  │
├─────────────────────────────────────┤
│ HERE NOW                             │
│ ● F8:ED:F8:77  (new)    node-1 -68  │
│ ● Alice's iPhone (res)  node-2 -54  │
│ ● CB:1A:A5:67  (unk)    node-1 -72  │
└─────────────────────────────────────┘
```

### Sections

**1. Header**
Title "Live Scan" with a connected/disconnected status badge (green/red pill).

**2. Summary counts**
Three fixed cards showing the current count of each non-ignored category visible right now. Updates reactively as the presence map changes.

| Card | Colour | Counts |
|---|---|---|
| NEW | Red | Devices with `first_seen < 30 min` |
| UNKNOWN | Yellow | `tag=unknown` devices seen before |
| KNOWN | Green | `known_resident` + `known_vehicle` combined |

**3. Recent Events feed**
Chronological list, newest at top, capped at 50 entries. Each entry shows:
- Badge: category abbreviation + arrow (↑ arrival, ↓ departure). Departure badges are at 60% opacity.
- Device label (if set) or truncated MAC
- Vendor string (if available, secondary text)
- Relative timestamp ("just now", "4m ago")

Feed events are generated for:
- `new` device: arrival ↑ and departure ↓
- `known_resident` device: arrival ↑ and departure ↓
- `known_vehicle` device: arrival ↑ and departure ↓
- `unknown` device: **no feed events** (silent add/remove from Here Now only)

**4. Here Now list**
All devices currently on the property (across all categories except `ignored`). Each row:
- Coloured dot matching category colour
- Label or truncated MAC
- Category hint in muted text
- Detecting node ID
- RSSI in dBm

Sorted: new first, then known (resident/vehicle), then unknown.

---

## Colour System

| Category | Colour | Hex |
|---|---|---|
| `new` | Red | `#ef4444` |
| `unknown` | Yellow | `#facc15` |
| `known_resident` | Green | `#4ade80` |
| `known_vehicle` | Blue | `#60a5fa` |

Matches the existing `TAG_COLORS` map in `web/src/routes/map/+page.svelte`.

---

## Client-Side State

### Data structures

```typescript
type DeviceCategory = 'new' | 'unknown' | 'known_resident' | 'known_vehicle';

type PresenceEntry = {
  mac: string;
  category: DeviceCategory;
  label: string | null;
  vendor: string | null;
  node_id: string;
  rssi: number;
  lastSeen: number; // Date.now() ms
};

type FeedEvent = {
  id: string;           // crypto.randomUUID() for keyed rendering
  direction: 'arrival' | 'departure';
  category: DeviceCategory;
  mac: string;
  label: string | null;
  vendor: string | null;
  node_id: string;
  time: number;         // Date.now() ms
};
```

### Device lookup table

On mount, `GET /devices` is fetched and stored as `Map<mac, DeviceRecord>` (tag, label, vendor, first_seen). This is the source of truth for classification and never re-fetched during the session — newly seen MACs that aren't in the table are treated as `unknown` until the next mount.

### Classification

```
first_seen within 30 min  →  'new'
tag === 'unknown'          →  'unknown'
tag === 'known_resident'   →  'known_resident'
tag === 'known_vehicle'    →  'known_vehicle'
tag === 'ignored'          →  excluded (never added to presence map)
```

The 30-minute "new" window is a module-level constant (`NEW_DEVICE_WINDOW_MS = 30 * 60 * 1000`).

Note: `first_seen` (used for "new" classification) and `last_seen` (used for pre-population filtering) are independent fields. A device first seen hours ago but active in the last 5 minutes will appear in "Here Now" but will be classified `unknown`, not `new`. This is intentional.

### Pre-population (on mount)

1. Fetch `GET /devices` → build device lookup table
2. Filter for `last_seen > now − 5 min` → add to presence map (no feed events generated for pre-populated entries)

The 5-minute stale window matches the existing `windowMinutes` default used on the Map page.

### WebSocket updates

On each `scan_events` message:
1. For each device in `payload.devices`:
   - Look up MAC in device table to get category, label, vendor
   - Update `lastSeen` and `rssi` in presence map
   - If MAC was **not** in presence map → arrival; add to map; if category is not `unknown` → prepend feed event. Devices already in the map (including those pre-populated on mount) are updated in place — no arrival event is generated.
2. `position_estimates` messages are ignored on this page

### Departure detection

A `setInterval` runs every 30 seconds. For each entry in the presence map:
- If `Date.now() - lastSeen > STALE_MS` (5 min):
  - Remove from presence map
  - If category is `new`, `known_resident`, or `known_vehicle` → prepend departure feed event
  - `unknown` entries are removed silently

### Feed management

- Capped at 50 entries (`MAX_FEED_EVENTS = 50`)
- Prepend on arrival/departure, slice to cap

---

## Error Handling

- WebSocket disconnect: status badge turns red; presence map and feed retain last-known state
- `GET /devices` failure on mount: page renders empty with an error note; WebSocket still connects and builds state from live events
- Malformed WebSocket message (missing `devices` field): skip silently — the existing `liveWebSocket` wrapper already catches JSON parse errors

---

## What Is Not In Scope

- Filtering/searching the Here Now list
- Configuring the stale timeout or new-device window in the UI
- Departure detection via server push (remains client-side timer for now)
- Labelling devices from this page
- Live device table refresh: the `GET /devices` lookup is fetched once on mount and never re-fetched. If a device is re-tagged while the page is open, it will be misclassified until the next page load.
