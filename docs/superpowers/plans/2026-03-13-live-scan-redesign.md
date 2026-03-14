# Live Scan Redesign Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the raw scan-count feed with a real-time property presence dashboard showing new, unknown, and known devices with colour-coded arrivals and departures.

**Architecture:** The backend emits per-device MACs in the pg_notify payload (one small change to db.py). The frontend pre-populates a presence map from `GET /devices` on mount, then maintains it via WebSocket scan batches. A 30-second timer evicts stale entries and generates departure feed events for tracked categories.

**Tech Stack:** Python/asyncpg (backend), SvelteKit 5 (legacy syntax), TypeScript, Vitest 4

**Spec:** `docs/superpowers/specs/2026-03-13-live-scan-redesign.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `server/mqtt_bridge/src/mqtt_bridge/db.py` | Modify | Expand pg_notify payload to include devices array |
| `server/mqtt_bridge/tests/test_db.py` | Modify | Add test for new pg_notify payload format |
| `web/package.json` | Modify | Add vitest devDependency |
| `web/vitest.config.ts` | Create | Vitest config for pure-TS tests |
| `web/src/lib/presence.ts` | Create | Types, constants, and pure classification/departure logic |
| `web/src/lib/presence.test.ts` | Create | Vitest unit tests for presence.ts |
| `web/src/lib/api.ts` | Modify | Add DeviceRecord and ScanBatch types; type fetchDevices return |
| `web/src/routes/scan/+page.svelte` | Rewrite | Presence dashboard UI with summary, feed, and here-now sections |

---

## Chunk 1: Backend — Expand pg_notify payload

### Task 1: Update pg_notify to include device list

**Files:**
- Modify: `server/mqtt_bridge/src/mqtt_bridge/db.py:82-89`
- Modify: `server/mqtt_bridge/tests/test_db.py`

- [ ] **Step 1: Write the failing test**

Add to `server/mqtt_bridge/tests/test_db.py`. The file already imports `AsyncMock`, `datetime`, `UTC`, `ScanEvent`, and `pytest` — only `import json` needs to be added at the top of the file:

```python
import json  # add this import at the top of test_db.py


async def test_insert_scan_events_notify_payload_includes_devices(mock_pool):
    pool, conn = mock_pool
    conn.executemany = AsyncMock()
    conn.execute = AsyncMock()
    from mqtt_bridge.db import insert_scan_events

    events = [
        ScanEvent(
            node_id="scanner-01",
            mac="AA:BB:CC:DD:EE:FF",
            rssi=-65,
            scan_type="wifi",
            ssid="TestNet",
            time=datetime(2026, 3, 12, tzinfo=UTC),
            node_lat=None,
            node_lon=None,
        ),
        ScanEvent(
            node_id="scanner-01",
            mac="11:22:33:44:55:66",
            rssi=-80,
            scan_type="ble",
            ssid=None,
            time=datetime(2026, 3, 12, tzinfo=UTC),
            node_lat=None,
            node_lon=None,
        ),
    ]
    await insert_scan_events(pool, events)

    notify_call = conn.execute.call_args[0]
    payload = json.loads(notify_call[1])

    assert payload["node_id"] == "scanner-01"
    assert payload["scan_type"] == "wifi"
    assert "devices" in payload
    assert len(payload["devices"]) == 2
    assert payload["devices"][0]["mac"] == "AA:BB:CC:DD:EE:FF"
    assert payload["devices"][0]["rssi"] == -65
    assert payload["devices"][0]["ssid"] == "TestNet"
    assert payload["devices"][1]["mac"] == "11:22:33:44:55:66"
    assert payload["devices"][1]["ssid"] is None
    assert "count" not in payload
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest server/mqtt_bridge/tests/test_db.py::test_insert_scan_events_notify_payload_includes_devices -v
```

Expected: `FAILED` — `AssertionError: assert "devices" in {...}`

- [ ] **Step 3: Update the pg_notify payload in db.py**

Replace lines 82-89 in `server/mqtt_bridge/src/mqtt_bridge/db.py`:

```python
        payload = json.dumps(
            {
                "node_id": events[0].node_id,
                "scan_type": events[0].scan_type,
                "devices": [
                    {"mac": e.mac, "rssi": e.rssi, "ssid": e.ssid}
                    for e in events
                ],
            }
        )
        await conn.execute("SELECT pg_notify('scan_events', $1)", payload)
```

- [ ] **Step 4: Run the new test to verify it passes**

```bash
pytest server/mqtt_bridge/tests/test_db.py::test_insert_scan_events_notify_payload_includes_devices -v
```

Expected: `PASSED`

- [ ] **Step 5: Run the full test suite to confirm no regressions**

```bash
pytest server/mqtt_bridge/tests/ -v
```

Expected: all tests pass. The existing `test_insert_scan_events_includes_node_coords` test checks `executemany`, not `execute`, so it is unaffected.

- [ ] **Step 6: Lint and format**

```bash
ruff check server/mqtt_bridge/src/mqtt_bridge/db.py
ruff format server/mqtt_bridge/src/mqtt_bridge/db.py
ruff check server/mqtt_bridge/tests/test_db.py
ruff format server/mqtt_bridge/tests/test_db.py
```

Expected: no errors or diffs.

- [ ] **Step 7: Commit**

```bash
git add server/mqtt_bridge/src/mqtt_bridge/db.py server/mqtt_bridge/tests/test_db.py
git commit -m "feat: include device list in scan_events pg_notify payload"
```

---

## Chunk 2: Frontend Infrastructure — Types, vitest, presence logic

### Task 2: Add types to api.ts

**Files:**
- Modify: `web/src/lib/api.ts`

- [ ] **Step 1: Add DeviceRecord and ScanBatch types, and type fetchDevices**

Add to the bottom of `web/src/lib/api.ts`:

```typescript
export type DeviceRecord = {
  mac: string;
  device_type: string;
  label: string | null;
  tag: string;
  first_seen: string;
  last_seen: string;
  vendor: string | null;
  ssid: string | null;
};

export type ScanBatch = {
  node_id: string;
  scan_type: string;
  devices: Array<{ mac: string; rssi: number; ssid: string | null }>;
};
```

Also update the `fetchDevices` signature to return the correct type:

```typescript
export async function fetchDevices(tag?: string): Promise<DeviceRecord[]> {
  const url = tag ? `${BASE}/devices?tag=${tag}` : `${BASE}/devices`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`GET /devices failed: ${res.status}`);
  return res.json();
}
```

- [ ] **Step 2: Verify type-check passes**

```bash
npm --prefix web run check
```

Expected: `0 ERRORS 0 WARNINGS`

### Task 3: Set up vitest

**Files:**
- Modify: `web/package.json`
- Create: `web/vitest.config.ts`

- [ ] **Step 1: Install vitest**

```bash
npm --prefix web install --save-dev vitest@4.1.0
```

- [ ] **Step 2: Create vitest.config.ts**

Create `web/vitest.config.ts`:

```typescript
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
```

- [ ] **Step 3: Add test script to package.json**

In `web/package.json`, add to `"scripts"`:

```json
"test": "vitest run"
```

- [ ] **Step 4: Verify vitest binary was installed**

```bash
ls web/node_modules/.bin/vitest
```

Expected: `web/node_modules/.bin/vitest` — fails fast if the install step was skipped.

### Task 4: Create presence.ts with pure logic

**Files:**
- Create: `web/src/lib/presence.ts`
- Create: `web/src/lib/presence.test.ts`

- [ ] **Step 1: Write the failing tests first**

Create `web/src/lib/presence.test.ts`:

```typescript
import { describe, it, expect } from "vitest";
import {
  classifyDevice,
  collectDepartures,
  NEW_DEVICE_WINDOW_MS,
  STALE_MS,
} from "./presence";
import type { DeviceRecord, PresenceEntry } from "./presence";

const NOW = 1_000_000_000_000;

function makeRecord(overrides: Partial<DeviceRecord> = {}): DeviceRecord {
  return {
    mac: "AA:BB:CC:DD:EE:FF",
    device_type: "wifi",
    label: null,
    tag: "unknown",
    first_seen: new Date(NOW - 60 * 60 * 1000).toISOString(), // 1hr ago
    last_seen: new Date(NOW - 60 * 1000).toISOString(),
    vendor: null,
    ssid: null,
    ...overrides,
  };
}

function makeEntry(overrides: Partial<PresenceEntry> = {}): PresenceEntry {
  return {
    mac: "AA:BB:CC:DD:EE:FF",
    category: "unknown",
    label: null,
    vendor: null,
    node_id: "node-1",
    rssi: -70,
    lastSeen: NOW - 60 * 1000,
    ...overrides,
  };
}

describe("classifyDevice", () => {
  it("returns null for ignored devices", () => {
    expect(classifyDevice(makeRecord({ tag: "ignored" }), NOW)).toBe(null);
  });

  it("returns new when first_seen is within 30 minutes", () => {
    const record = makeRecord({
      first_seen: new Date(NOW - 10 * 60 * 1000).toISOString(),
    });
    expect(classifyDevice(record, NOW)).toBe("new");
  });

  it("classifies as new regardless of tag when first_seen is recent", () => {
    const record = makeRecord({
      tag: "known_resident",
      first_seen: new Date(NOW - 5 * 60 * 1000).toISOString(),
    });
    expect(classifyDevice(record, NOW)).toBe("new");
  });

  it("returns unknown for unknown tag beyond new window", () => {
    expect(classifyDevice(makeRecord({ tag: "unknown" }), NOW)).toBe("unknown");
  });

  it("returns known_resident for resident tag beyond new window", () => {
    expect(
      classifyDevice(makeRecord({ tag: "known_resident" }), NOW)
    ).toBe("known_resident");
  });

  it("returns known_vehicle for vehicle tag beyond new window", () => {
    expect(
      classifyDevice(makeRecord({ tag: "known_vehicle" }), NOW)
    ).toBe("known_vehicle");
  });

  it("returns unknown when record is undefined (MAC not in table)", () => {
    expect(classifyDevice(undefined, NOW)).toBe("unknown");
  });
});

describe("collectDepartures", () => {
  it("returns empty when no entries are stale", () => {
    const map = new Map([
      ["AA:BB:CC:DD:EE:FF", makeEntry({ lastSeen: NOW - 60 * 1000 })],
    ]);
    const { departed, active } = collectDepartures(map, NOW, STALE_MS);
    expect(departed).toHaveLength(0);
    expect(active.size).toBe(1);
  });

  it("removes stale entries and returns them as departed", () => {
    const staleEntry = makeEntry({ lastSeen: NOW - 6 * 60 * 1000 });
    const freshEntry = makeEntry({
      mac: "11:22:33:44:55:66",
      lastSeen: NOW - 60 * 1000,
    });
    const map = new Map([
      ["AA:BB:CC:DD:EE:FF", staleEntry],
      ["11:22:33:44:55:66", freshEntry],
    ]);
    const { departed, active } = collectDepartures(map, NOW, STALE_MS);
    expect(departed).toHaveLength(1);
    expect(departed[0].mac).toBe("AA:BB:CC:DD:EE:FF");
    expect(active.size).toBe(1);
    expect(active.has("11:22:33:44:55:66")).toBe(true);
  });

  it("does not mutate the input map", () => {
    const map = new Map([
      ["AA:BB:CC:DD:EE:FF", makeEntry({ lastSeen: NOW - 6 * 60 * 1000 })],
    ]);
    collectDepartures(map, NOW, STALE_MS);
    expect(map.size).toBe(1);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
npm --prefix web test
```

Expected: multiple failures — `Cannot find module './presence'`

- [ ] **Step 3: Create presence.ts with the implementation**

Create `web/src/lib/presence.ts`.

Note: use a relative import for `DeviceRecord` (not `$lib/api`) so that vitest can resolve it without the SvelteKit Vite plugin. Re-export the type so tests only need to import from `"./presence"`.

**Important:** keep this as `export type` (not `export`). A value re-export would cause vitest to evaluate `api.ts` at runtime, which imports `$env/dynamic/public` and `$app/environment` — SvelteKit-only modules that crash without the Vite plugin loaded.

```typescript
// type-only re-export: must stay `export type` to avoid loading SvelteKit runtime in vitest
export type { DeviceRecord } from "./api";

export type DeviceCategory =
  | "new"
  | "unknown"
  | "known_resident"
  | "known_vehicle";

export type PresenceEntry = {
  mac: string;
  category: DeviceCategory;
  label: string | null;
  vendor: string | null;
  node_id: string;
  rssi: number;
  lastSeen: number;
};

export type FeedEvent = {
  id: string;
  direction: "arrival" | "departure";
  category: DeviceCategory;
  mac: string;
  label: string | null;
  vendor: string | null;
  node_id: string;
  time: number;
};

export const NEW_DEVICE_WINDOW_MS = 30 * 60 * 1000;
export const STALE_MS = 5 * 60 * 1000;
export const MAX_FEED_EVENTS = 50;
export const PRESENCE_WINDOW_MS = 5 * 60 * 1000;

/**
 * Determines the display category for a device.
 * Returns null if the device should be excluded (ignored tag).
 */
export function classifyDevice(
  record: DeviceRecord | undefined,
  now: number
): DeviceCategory | null {
  if (!record) return "unknown";
  if (record.tag === "ignored") return null;
  if (now - new Date(record.first_seen).getTime() < NEW_DEVICE_WINDOW_MS) {
    return "new";
  }
  if (record.tag === "known_resident") return "known_resident";
  if (record.tag === "known_vehicle") return "known_vehicle";
  return "unknown";
}

/**
 * Returns true if this category generates feed events on arrival/departure.
 * Unknown devices only appear in the "here now" list, not the feed.
 */
export function hasFeedEvent(category: DeviceCategory): boolean {
  return category !== "unknown";
}

/**
 * Scans the presence map for stale entries.
 * Returns departed entries and a new map with them removed.
 * Does not mutate the input map.
 */
export function collectDepartures(
  presenceMap: Map<string, PresenceEntry>,
  now: number,
  staleMs: number
): { departed: PresenceEntry[]; active: Map<string, PresenceEntry> } {
  const departed: PresenceEntry[] = [];
  const active = new Map<string, PresenceEntry>();

  for (const [mac, entry] of presenceMap) {
    if (now - entry.lastSeen > staleMs) {
      departed.push(entry);
    } else {
      active.set(mac, entry);
    }
  }

  return { departed, active };
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
npm --prefix web test
```

Expected: all tests pass — `classifyDevice` and `collectDepartures` suites green.

- [ ] **Step 5: Verify full type-check still passes**

```bash
npm --prefix web run check
```

Expected: `0 ERRORS 0 WARNINGS`

- [ ] **Step 6: Commit**

```bash
git add web/package.json web/package-lock.json web/vitest.config.ts \
        web/src/lib/api.ts web/src/lib/presence.ts web/src/lib/presence.test.ts
git commit -m "feat: add presence logic and types for live scan redesign"
```

---

## Chunk 3: Frontend — Live Scan Page

### Task 5: Rewrite scan/+page.svelte

**Files:**
- Rewrite: `web/src/routes/scan/+page.svelte`

The page has four visual sections: header (title + connection badge), summary counts (NEW / UNKNOWN / KNOWN), recent events feed, and here-now list. All state is client-side — no `+page.server.ts` needed (none exists for this route).

- [ ] **Step 1: Replace the page with the new implementation**

Replace the entire contents of `web/src/routes/scan/+page.svelte`:

```svelte
<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { fetchDevices, liveWebSocket } from "$lib/api";
  import type { DeviceRecord, ScanBatch } from "$lib/api";
  import {
    classifyDevice,
    collectDepartures,
    hasFeedEvent,
    MAX_FEED_EVENTS,
    PRESENCE_WINDOW_MS,
    STALE_MS,
  } from "$lib/presence";
  import type { DeviceCategory, FeedEvent, PresenceEntry } from "$lib/presence";

  const CATEGORY_COLORS: Record<DeviceCategory, string> = {
    new: "#ef4444",
    unknown: "#facc15",
    known_resident: "#4ade80",
    known_vehicle: "#60a5fa",
  };

  const CATEGORY_LABELS: Record<DeviceCategory, string> = {
    new: "NEW",
    unknown: "UNK",
    known_resident: "RES",
    known_vehicle: "VEH",
  };

  const SORT_ORDER: Record<DeviceCategory, number> = {
    new: 0,
    known_resident: 1,
    known_vehicle: 1,
    unknown: 2,
  };

  let connected = false;
  let error: string | null = null;
  let ws: WebSocket | undefined;
  let departureTimer: ReturnType<typeof setInterval> | undefined;

  let deviceTable = new Map<string, DeviceRecord>();
  let presenceMap = new Map<string, PresenceEntry>();
  let feed: FeedEvent[] = [];

  $: newCount = [...presenceMap.values()].filter(
    (e) => e.category === "new"
  ).length;
  $: unknownCount = [...presenceMap.values()].filter(
    (e) => e.category === "unknown"
  ).length;
  $: knownCount = [...presenceMap.values()].filter(
    (e) => e.category === "known_resident" || e.category === "known_vehicle"
  ).length;
  $: presenceEntries = [...presenceMap.values()].sort(
    (a, b) => SORT_ORDER[a.category] - SORT_ORDER[b.category]
  );

  function handleScanBatch(data: unknown) {
    const batch = data as ScanBatch;
    if (!Array.isArray(batch?.devices)) return;

    const now = Date.now();
    for (const device of batch.devices) {
      const record = deviceTable.get(device.mac);
      const category = classifyDevice(record, now);
      if (category === null) continue;

      const existing = presenceMap.get(device.mac);
      if (existing) {
        existing.lastSeen = now;
        existing.rssi = device.rssi;
        existing.node_id = batch.node_id;
        presenceMap = presenceMap;
      } else {
        const entry: PresenceEntry = {
          mac: device.mac,
          category,
          label: record?.label ?? null,
          vendor: record?.vendor ?? null,
          node_id: batch.node_id,
          rssi: device.rssi,
          lastSeen: now,
        };
        presenceMap.set(device.mac, entry);
        presenceMap = presenceMap;

        if (hasFeedEvent(category)) {
          const event: FeedEvent = {
            id: crypto.randomUUID(),
            direction: "arrival",
            category,
            mac: device.mac,
            label: record?.label ?? null,
            vendor: record?.vendor ?? null,
            node_id: batch.node_id,
            time: now,
          };
          feed = [event, ...feed].slice(0, MAX_FEED_EVENTS);
        }
      }
    }
  }

  function runDepartureCheck() {
    const now = Date.now();
    const { departed, active } = collectDepartures(presenceMap, now, STALE_MS);
    if (departed.length === 0) return;

    presenceMap = active;

    const newEvents: FeedEvent[] = departed
      .filter((e) => hasFeedEvent(e.category))
      .map((e) => ({
        id: crypto.randomUUID(),
        direction: "departure" as const,
        category: e.category,
        mac: e.mac,
        label: e.label,
        vendor: e.vendor,
        node_id: e.node_id,
        time: now,
      }));

    if (newEvents.length > 0) {
      feed = [...newEvents, ...feed].slice(0, MAX_FEED_EVENTS);
    }
  }

  onMount(async () => {
    try {
      const devices = await fetchDevices();
      deviceTable = new Map(devices.map((d) => [d.mac, d]));

      const now = Date.now();
      for (const device of devices) {
        if (now - new Date(device.last_seen).getTime() > PRESENCE_WINDOW_MS) {
          continue;
        }
        const category = classifyDevice(device, now);
        if (category === null) continue;
        presenceMap.set(device.mac, {
          mac: device.mac,
          category,
          label: device.label,
          vendor: device.vendor,
          node_id: "—",
          rssi: 0,
          lastSeen: new Date(device.last_seen).getTime(),
        });
      }
      presenceMap = presenceMap;
    } catch {
      error = "Could not load device list — live updates will still work.";
    }

    ws = liveWebSocket(handleScanBatch);
    ws.onopen = () => (connected = true);
    ws.onclose = () => (connected = false);
    ws.onerror = () => (connected = false);

    departureTimer = setInterval(runDepartureCheck, 30_000);
  });

  onDestroy(() => {
    ws?.close();
    clearInterval(departureTimer);
  });

  function formatTime(ms: number): string {
    const diff = Date.now() - ms;
    if (diff < 10_000) return "just now";
    if (diff < 60_000) return `${Math.floor(diff / 1000)}s ago`;
    if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
    return `${Math.floor(diff / 3_600_000)}h ago`;
  }

  function displayName(mac: string, label: string | null): string {
    return label ?? mac.slice(0, 14);
  }
</script>

<svelte:head><title>Live Scan — botanical-sentinel</title></svelte:head>

<div class="p-6 max-w-2xl mx-auto">
  <!-- Header -->
  <div class="flex items-center gap-3 mb-5">
    <h1 class="text-xl font-semibold">Live Scan</h1>
    <span
      class="text-xs px-2 py-0.5 rounded-full {connected
        ? 'bg-green-900 text-green-300'
        : 'bg-red-900 text-red-300'}"
    >
      {connected ? "● connected" : "○ disconnected"}
    </span>
  </div>

  {#if error}
    <p class="text-yellow-500 text-xs mb-4">{error}</p>
  {/if}

  <!-- Summary counts -->
  <div class="grid grid-cols-3 gap-3 mb-5">
    <div class="rounded-lg bg-red-950 p-3 text-center">
      <div class="text-2xl font-bold text-red-300">{newCount}</div>
      <div class="text-xs text-red-400 mt-0.5">NEW</div>
    </div>
    <div class="rounded-lg bg-yellow-950 p-3 text-center">
      <div class="text-2xl font-bold text-yellow-200">{unknownCount}</div>
      <div class="text-xs text-yellow-400 mt-0.5">UNKNOWN</div>
    </div>
    <div class="rounded-lg bg-green-950 p-3 text-center">
      <div class="text-2xl font-bold text-green-300">{knownCount}</div>
      <div class="text-xs text-green-400 mt-0.5">KNOWN</div>
    </div>
  </div>

  <!-- Event feed -->
  <div class="mb-1">
    <h2 class="text-xs uppercase tracking-widest text-zinc-500 mb-2">
      Recent Events
    </h2>
    {#if feed.length === 0}
      <p class="text-zinc-600 text-sm">No events yet — waiting for scans…</p>
    {:else}
      <div class="space-y-1.5">
        {#each feed as event (event.id)}
          {@const color = CATEGORY_COLORS[event.category]}
          {@const label = CATEGORY_LABELS[event.category]}
          {@const arrival = event.direction === "arrival"}
          <div class="flex items-center gap-2 font-mono text-xs">
            <span
              class="rounded px-1.5 py-0.5 text-[10px] font-semibold min-w-[52px] text-center shrink-0"
              style="background-color: {color}22; color: {color}; opacity: {arrival
                ? 1
                : 0.6};"
            >
              {label}
              {arrival ? "↑" : "↓"}
            </span>
            <span class="text-zinc-200 truncate">
              {displayName(event.mac, event.label)}
            </span>
            {#if event.vendor}
              <span class="text-zinc-500 truncate hidden sm:inline"
                >· {event.vendor}</span
              >
            {/if}
            <span class="text-zinc-600 ml-auto shrink-0">
              {formatTime(event.time)}
            </span>
          </div>
        {/each}
      </div>
    {/if}
  </div>

  <!-- Here now -->
  <div class="mt-5">
    <h2 class="text-xs uppercase tracking-widest text-zinc-500 mb-2">
      Here Now
    </h2>
    {#if presenceEntries.length === 0}
      <p class="text-zinc-600 text-sm">No devices visible.</p>
    {:else}
      <div class="space-y-1">
        {#each presenceEntries as entry (entry.mac)}
          {@const color = CATEGORY_COLORS[entry.category]}
          <div class="flex items-center justify-between font-mono text-xs">
            <div class="flex items-center gap-2 min-w-0">
              <span style="color: {color};" class="shrink-0">●</span>
              <span class="text-zinc-200 truncate">
                {displayName(entry.mac, entry.label)}
              </span>
              <span class="text-zinc-600 shrink-0">
                ({CATEGORY_LABELS[entry.category].toLowerCase()})
              </span>
            </div>
            <div class="flex items-center gap-3 text-zinc-500 shrink-0 ml-2">
              <span>{entry.node_id}</span>
              {#if entry.rssi !== 0}
                <span>{entry.rssi} dBm</span>
              {/if}
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </div>
</div>
```

- [ ] **Step 2: Run type-check**

```bash
npm --prefix web run check
```

Expected: `0 ERRORS 0 WARNINGS`

- [ ] **Step 3: Run tests to confirm presence logic is still green**

```bash
npm --prefix web test
```

Expected: all tests pass

- [ ] **Step 4: Build to confirm production bundle compiles**

```bash
npm --prefix web run build 2>&1 | tail -5
```

Expected: `✔ done` with no errors

- [ ] **Step 5: Commit**

```bash
git add web/src/routes/scan/+page.svelte
git commit -m "feat: redesign live scan as real-time presence dashboard"
```

- [ ] **Step 6: Push**

```bash
git push
```

---

## Deploy checklist

On the edge server after `git pull`:

```bash
# Rebuild both api (db.py changed) and web (page changed)
docker compose -f server/docker-compose.yml up -d --build api web
```

Verify:
1. Open `/scan` — page loads with "disconnected" badge, all counts at 0
2. After first scan batch arrives — badge turns green, devices appear in "Here Now"
3. New devices (first seen < 30 min) show red NEW badge in both feed and here-now
4. Known residents/vehicles show green/blue in feed on arrival; fade on departure
5. Unknown devices appear only in "Here Now" with yellow dot — no feed entry
