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

      marker.on("click", () => openPanel(nodeData.get(node.node_id) ?? node));
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
    if (node.lat == null || node.lon == null) return;
    if (selectedNode) runCleanup({ restorePosition: true });

    selectedNode = node;
    editName = node.name ?? "";
    editLat = node.lat;
    editLon = node.lon;
    originalLat = node.lat;
    originalLon = node.lon;
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
    }
    if (mapClickHandler && map) {
      map.off("click", mapClickHandler);
      mapClickHandler = null;
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
      runCleanup({ restorePosition: false });
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
              disabled={!gpsUnlocked}
              class="w-full bg-zinc-800 border border-zinc-600 rounded px-2 py-1 text-zinc-100 text-xs focus:outline-none focus:border-zinc-400"
              class:opacity-50={!gpsUnlocked}
            />
          </label>
          <label class="flex-1">
            <span class="text-zinc-500 text-xs">Lon</span>
            <input
              type="number"
              step="any"
              bind:value={editLon}
              disabled={!gpsUnlocked}
              class="w-full bg-zinc-800 border border-zinc-600 rounded px-2 py-1 text-zinc-100 text-xs focus:outline-none focus:border-zinc-400"
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
