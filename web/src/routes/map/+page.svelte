<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import type { Map as LeafletMap, CircleMarker, Polyline } from "leaflet";
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

    const history = await fetchPositionHistory(mac, 100);
    if (history.length < 2) return;

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
