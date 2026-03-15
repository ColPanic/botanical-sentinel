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
    setDeviceLabel,
    setDeviceTag,
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

  const TAGS = ["unknown", "known_resident", "known_vehicle", "ignored"];

  // ── Device data ─────────────────────────────────────────────────────────────
  const deviceData = new Map<string, PositionResponse>();

  // ── Bulk selection state ────────────────────────────────────────────────────
  let bulkSelected = new Set<string>();
  let bulkTag = "";
  let bulkLabel = "";
  let bulkApplying = false;
  let bulkError: string | null = null;

  // ── Device edit panel state ────────────────────────────────────────────────
  let devicePanelEl: HTMLDivElement | undefined;
  let selectedDevice: PositionResponse | null = null;
  let editDeviceLabel = "";
  let editDeviceTag = "";
  let deviceSaveError: string | null = null;
  let deviceSaving = false;
  let deviceEscapeHandler: ((e: KeyboardEvent) => void) | null = null;

  // ── Node edit panel state ─────────────────────────────────────────────────
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

  // ── Placement mode state ──────────────────────────────────────────────────────
  let unlocatedNodes: NodeResponse[] = [];
  let pendingNodeId: string | null = null;
  let isNewPlacement = false;
  let placementClickHandler: ((e: LeafletMouseEvent) => void) | null = null;

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
      html: `<svg width="28" height="28" viewBox="0 0 28 28" fill="none">
        <path d="M14 2 L14 22" stroke="${color}" stroke-width="3" stroke-linecap="round"/>
        <path d="M7 8 L14 4 L21 8" stroke="${color}" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M4 14 L14 8 L24 14" stroke="${color}" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
        <circle cx="14" cy="24" r="3" fill="${color}"/>
      </svg>`,
      iconSize: [28, 28],
      iconAnchor: [14, 28],
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

    map.on("move zoom", () => { repositionPanel(); repositionDevicePanel(); });
  }

  async function loadNodes() {
    if (!map) return;
    const L = await import("leaflet");

    // Clear existing node markers before reloading
    for (const marker of nodeMarkers.values()) {
      marker.remove();
    }
    nodeMarkers.clear();

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
        .bindTooltip(label, { permanent: true, direction: "bottom", offset: [0, 0], className: "node-label" })
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
    deviceData.set(pos.mac, pos);

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
      marker.on("click", (e: LeafletMouseEvent) => handleDeviceClick(e, pos.mac));
      deviceMarkers.set(pos.mac, marker);
    }
  }

  function handleDeviceClick(e: LeafletMouseEvent, mac: string) {
    if (e.originalEvent.shiftKey) {
      toggleBulkSelect(mac);
      return;
    }
    // Normal click — clear bulk selection if any
    if (bulkSelected.size > 0) clearBulkSelection();
    selectDevice(mac);
  }

  function toggleBulkSelect(mac: string) {
    // Close any open panels when starting bulk selection
    if (selectedDevice) closeDevicePanel();
    if (selectedNode) runCleanup({ restorePosition: true });

    if (bulkSelected.has(mac)) {
      bulkSelected.delete(mac);
    } else {
      bulkSelected.add(mac);
    }
    bulkSelected = bulkSelected; // trigger reactivity
    updateBulkHighlights();
  }

  function clearBulkSelection() {
    bulkSelected = new Set();
    bulkTag = "";
    bulkLabel = "";
    bulkError = null;
    updateBulkHighlights();
  }

  function updateBulkHighlights() {
    for (const [mac, marker] of deviceMarkers) {
      const pos = deviceData.get(mac);
      const baseColor = TAG_COLORS[pos?.tag ?? "unknown"] ?? TAG_COLORS.unknown;
      if (bulkSelected.has(mac)) {
        marker.setStyle({ color: "#fff", fillColor: baseColor, fillOpacity: 0.8, weight: 3 });
      } else {
        marker.setStyle({ color: baseColor, fillColor: baseColor, fillOpacity: 0.4, weight: 2 });
      }
    }
  }

  async function applyBulkEdit() {
    if (bulkSelected.size === 0) return;
    bulkApplying = true;
    bulkError = null;
    try {
      const promises: Promise<unknown>[] = [];
      for (const mac of bulkSelected) {
        if (bulkTag) promises.push(setDeviceTag(mac, bulkTag));
        if (bulkLabel.trim()) promises.push(setDeviceLabel(mac, bulkLabel.trim()));
      }
      await Promise.all(promises);

      // Update local state and markers
      for (const mac of bulkSelected) {
        const pos = deviceData.get(mac);
        if (pos) {
          const updated = { ...pos };
          if (bulkTag) updated.tag = bulkTag;
          if (bulkLabel.trim()) updated.label = bulkLabel.trim();
          deviceData.set(mac, updated);
        }
        const marker = deviceMarkers.get(mac);
        if (marker) {
          const newTag = bulkTag || pos?.tag || "unknown";
          const color = TAG_COLORS[newTag] ?? TAG_COLORS.unknown;
          marker.setStyle({ color, fillColor: color, fillOpacity: 0.4, weight: 2 });
          if (bulkLabel.trim()) marker.getTooltip()?.setContent(bulkLabel.trim());
        }
      }
      clearBulkSelection();
    } catch (e) {
      bulkError = e instanceof Error ? e.message : "Bulk edit failed";
    } finally {
      bulkApplying = false;
    }
  }

  async function selectDevice(mac: string) {
    if (!map) return;
    const L = await import("leaflet");

    // Close any open node panel
    if (selectedNode) runCleanup({ restorePosition: true });

    // Draw trail
    if (trailLines.has(mac)) {
      trailLines.get(mac)!.remove();
      trailLines.delete(mac);
    }
    const history = await fetchPositionHistory(mac, 100);
    if (history.length >= 2) {
      const coords = history.map((p) => [p.lat, p.lon] as [number, number]);
      const trail = L.polyline(coords, { color: "#f97316", weight: 2, opacity: 0.8 }).addTo(map);
      trailLines.set(mac, trail);
    }

    // Open device panel
    const pos = deviceData.get(mac);
    if (!pos) return;
    openDevicePanel(pos);
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
    if (selectedDevice) closeDevicePanel();

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
    if (dragStartHandler) {
      marker.off("dragstart", dragStartHandler);
      dragStartHandler = null;
    }
    if (dragEndHandler) {
      marker.off("dragend", dragEndHandler);
      dragEndHandler = null;
    }
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

  function cancelPlacement() {
    if (placementClickHandler && map) {
      map.off("click", placementClickHandler);
      placementClickHandler = null;
    }
    if (map) map.getContainer().style.cursor = "";
    pendingNodeId = null;
  }

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

      try {
        const L = await import("leaflet");
        const icon = await makeNodeIcon("#facc15");
        const marker = L.marker([e.latlng.lat, e.latlng.lng], { icon })
          .bindTooltip(node.name ?? node.node_id, { permanent: true, direction: "bottom", offset: [0, 0], className: "node-label" })
          .addTo(map!);
        marker.on("click", () => {
          const n = nodeData.get(node.node_id);
          if (n) openPanel(n);
        });
        nodeMarkers.set(node.node_id, marker);
        isNewPlacement = true;

        const provisionalNode: NodeResponse = { ...node, lat: e.latlng.lat, lon: e.latlng.lng };
        nodeData.set(node.node_id, provisionalNode);

        // openPanel sets gpsUnlocked=false; toggleGps() must be called after it
        // to start the new placement with GPS already unlocked.
        openPanel(provisionalNode);
        toggleGps();
      } catch (err) {
        console.error("Placement failed", err);
        // Nothing was added to the map — unlocatedNodes still contains this node so the user can retry.
      }
    };

    map.on("click", placementClickHandler);
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
        if (updated.lat != null && updated.lon != null) {
          marker.setLatLng([updated.lat, updated.lon]);
        }
        marker.getTooltip()?.setContent(updated.name ?? updated.node_id);
        const newIcon = await makeNodeIcon(nodeColor(updated));
        marker.setIcon(newIcon);
      }

      nodeData.set(updated.node_id, updated);
      unlocatedNodes = unlocatedNodes.filter((n) => n.node_id !== updated.node_id);
      runCleanup({ restorePosition: false });
    } catch (e) {
      saveError = e instanceof Error ? e.message : "Save failed";
    } finally {
      saving = false;
    }
  }

  // ── Device edit panel ──────────────────────────────────────────────────────
  function openDevicePanel(pos: PositionResponse) {
    if (selectedDevice) closeDevicePanel();

    selectedDevice = pos;
    editDeviceLabel = pos.label ?? "";
    editDeviceTag = pos.tag;
    deviceSaveError = null;

    deviceEscapeHandler = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeDevicePanel();
    };
    document.addEventListener("keydown", deviceEscapeHandler);

    requestAnimationFrame(repositionDevicePanel);
  }

  function closeDevicePanel() {
    if (deviceEscapeHandler) {
      document.removeEventListener("keydown", deviceEscapeHandler);
      deviceEscapeHandler = null;
    }
    selectedDevice = null;
    deviceSaveError = null;
  }

  function repositionDevicePanel() {
    if (!map || !selectedDevice || !devicePanelEl) return;
    const marker = deviceMarkers.get(selectedDevice.mac);
    if (!marker) return;
    const pt = map.latLngToContainerPoint(marker.getLatLng());
    const h = devicePanelEl.offsetHeight || 160;
    devicePanelEl.style.left = `${pt.x}px`;
    devicePanelEl.style.top = `${pt.y - h - 12}px`;
    devicePanelEl.style.transform = "translateX(-50%)";
  }

  async function handleDeviceSave() {
    if (!selectedDevice) return;
    deviceSaving = true;
    deviceSaveError = null;
    try {
      const label = editDeviceLabel.trim();
      const mac = selectedDevice.mac;

      await Promise.all([
        setDeviceLabel(mac, label),
        editDeviceTag !== selectedDevice.tag ? setDeviceTag(mac, editDeviceTag) : Promise.resolve(),
      ]);

      // Update local state and marker appearance
      const updated: PositionResponse = { ...selectedDevice, label: label || null, tag: editDeviceTag };
      deviceData.set(mac, updated);

      const marker = deviceMarkers.get(mac);
      if (marker) {
        const color = TAG_COLORS[editDeviceTag] ?? TAG_COLORS.unknown;
        marker.setStyle({ color, fillColor: color });
        marker.getTooltip()?.setContent(label || mac);
      }

      closeDevicePanel();
    } catch (e) {
      deviceSaveError = e instanceof Error ? e.message : "Save failed";
    } finally {
      deviceSaving = false;
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

  $: visibleUnlocatedNodes = unlocatedNodes.filter((n) => n.node_id !== selectedNode?.node_id);

  onDestroy(() => {
    ws?.close();
    map?.remove();
    if (escapeHandler) document.removeEventListener("keydown", escapeHandler);
    if (deviceEscapeHandler) document.removeEventListener("keydown", deviceEscapeHandler);
    if (placementClickHandler && map) map.off("click", placementClickHandler);
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

    <!-- Floating device edit panel -->
    {#if selectedDevice}
      <div
        bind:this={devicePanelEl}
        class="absolute z-[1000] w-64 bg-zinc-900 border border-zinc-700 rounded-lg shadow-xl p-3 text-sm"
        style="pointer-events:auto"
      >
        <!-- Header -->
        <div class="flex items-center justify-between mb-2">
          <span class="font-mono text-xs text-zinc-400">{selectedDevice.mac}</span>
          <button
            class="text-zinc-500 hover:text-zinc-200 text-base leading-none"
            onclick={closeDevicePanel}
          >×</button>
        </div>

        <!-- Info -->
        <div class="flex gap-3 mb-3 text-xs text-zinc-500">
          {#if selectedDevice.vendor}
            <span>{selectedDevice.vendor}</span>
          {/if}
          <span>{selectedDevice.device_type}</span>
        </div>

        <!-- Label -->
        <label class="block mb-3">
          <span class="text-zinc-400 text-xs">Label</span>
          <input
            type="text"
            maxlength="100"
            placeholder={selectedDevice.mac}
            bind:value={editDeviceLabel}
            class="mt-0.5 w-full bg-zinc-800 border border-zinc-600 rounded px-2 py-1 text-zinc-100 text-sm focus:outline-none focus:border-zinc-400"
          />
        </label>

        <!-- Tag -->
        <label class="block mb-3">
          <span class="text-zinc-400 text-xs">Tag</span>
          <select
            bind:value={editDeviceTag}
            class="mt-0.5 w-full bg-zinc-800 border border-zinc-600 rounded px-2 py-1 text-zinc-100 text-sm focus:outline-none focus:border-zinc-400"
          >
            {#each TAGS as tag}
              <option value={tag}>{tag.replace("_", " ")}</option>
            {/each}
          </select>
        </label>

        {#if deviceSaveError}
          <p class="text-red-400 text-xs mb-2">{deviceSaveError}</p>
        {/if}

        <!-- Actions -->
        <div class="flex gap-2">
          <button
            class="flex-1 bg-zinc-700 hover:bg-zinc-600 text-zinc-200 rounded px-3 py-1.5 text-xs"
            onclick={closeDevicePanel}
          >Cancel</button>
          <button
            disabled={deviceSaving}
            class="flex-1 bg-blue-700 hover:bg-blue-600 disabled:opacity-50 text-white rounded px-3 py-1.5 text-xs"
            onclick={handleDeviceSave}
          >{deviceSaving ? "Saving…" : "Save"}</button>
        </div>
      </div>
    {/if}

    <!-- Bulk selection action bar -->
    {#if bulkSelected.size > 0}
      <div class="absolute z-[1000] bottom-4 left-1/2 -translate-x-1/2 bg-zinc-900 border border-zinc-700 rounded-lg shadow-xl p-3 text-sm flex items-center gap-3" style="pointer-events:auto">
        <span class="text-zinc-300 text-xs font-semibold whitespace-nowrap">{bulkSelected.size} selected</span>

        <select
          bind:value={bulkTag}
          class="bg-zinc-800 border border-zinc-600 rounded px-2 py-1 text-zinc-100 text-xs"
        >
          <option value="">Tag…</option>
          {#each TAGS as tag}
            <option value={tag}>{tag.replace("_", " ")}</option>
          {/each}
        </select>

        <input
          type="text"
          bind:value={bulkLabel}
          placeholder="Label…"
          class="bg-zinc-800 border border-zinc-600 rounded px-2 py-1 text-zinc-100 text-xs w-32"
        />

        <button
          disabled={bulkApplying || (!bulkTag && !bulkLabel.trim())}
          class="bg-blue-700 hover:bg-blue-600 disabled:opacity-50 text-white rounded px-3 py-1 text-xs whitespace-nowrap"
          onclick={applyBulkEdit}
        >{bulkApplying ? "Applying…" : "Apply"}</button>

        <button
          class="text-zinc-500 hover:text-zinc-200 text-xs"
          onclick={clearBulkSelection}
        >Clear</button>

        {#if bulkError}
          <span class="text-red-400 text-xs">{bulkError}</span>
        {/if}
      </div>
    {/if}

    <!-- Nodes without confirmed location -->
    {#if visibleUnlocatedNodes.length > 0}
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
          {#each visibleUnlocatedNodes as node}
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
  </div>
</div>

<style>
  :global(.node-label) {
    background: none !important;
    border: none !important;
    box-shadow: none !important;
    font-family: ui-monospace, monospace;
    font-size: 10px;
    color: #e4e4e7;
    padding: 0 !important;
    text-shadow: 0 1px 3px rgba(0, 0, 0, 0.8);
  }
  :global(.node-label::before) {
    display: none !important;
  }
</style>
