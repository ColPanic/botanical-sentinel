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
