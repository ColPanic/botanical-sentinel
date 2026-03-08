<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { liveWebSocket } from "$lib/api";

  type ScanEvent = {
    node_id: string;
    scan_type: string;
    count: number;
    time: string;
  };

  let events: ScanEvent[] = [];
  let connected = false;
  let ws: WebSocket | undefined;

  onMount(() => {
    ws = liveWebSocket((data) => {
      events = [
        { ...(data as Omit<ScanEvent, "time">), time: new Date().toISOString() },
        ...events.slice(0, 99),
      ];
    });
    ws.onopen = () => (connected = true);
    ws.onclose = () => (connected = false);
    ws.onerror = () => (connected = false);
  });

  onDestroy(() => ws?.close());
</script>

<svelte:head><title>Live Scan — botanical-sentinel</title></svelte:head>

<div class="p-6">
  <div class="flex items-center gap-3 mb-4">
    <h1 class="text-xl font-semibold">Live Scan</h1>
    <span class="text-xs px-2 py-0.5 rounded-full {connected ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300'}">
      {connected ? "connected" : "disconnected"}
    </span>
  </div>

  {#if events.length === 0}
    <p class="text-zinc-500 text-sm">Waiting for scan events…</p>
  {:else}
    <table class="w-full text-sm border-collapse">
      <thead>
        <tr class="text-left border-b border-zinc-700">
          <th class="py-2 pr-4">Time</th>
          <th class="py-2 pr-4">Node</th>
          <th class="py-2 pr-4">Type</th>
          <th class="py-2">Count</th>
        </tr>
      </thead>
      <tbody>
        {#each events as event}
          <tr class="border-b border-zinc-800">
            <td class="py-1 pr-4 text-zinc-400 font-mono text-xs">
              {new Date(event.time).toLocaleTimeString()}
            </td>
            <td class="py-1 pr-4 font-mono">{event.node_id}</td>
            <td class="py-1 pr-4 {event.scan_type === 'wifi' ? 'text-cyan-400' : 'text-green-400'}">
              {event.scan_type}
            </td>
            <td class="py-1">{event.count}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</div>
