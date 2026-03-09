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
    ws.onopen  = () => (connected = true);
    ws.onclose = () => (connected = false);
    ws.onerror = () => (connected = false);
  });

  onDestroy(() => ws?.close());
</script>

<svelte:head><title>Live Scan — botanical-sentinel</title></svelte:head>

<!-- Header -->
<div class="flex items-center gap-4 mb-5">
  <h1 class="font-display text-lg font-bold tracking-widest uppercase text-text">Live Scan</h1>

  <div class="flex items-center gap-2 px-2.5 py-1 rounded-full text-xs font-mono border
              {connected
                ? 'text-emerald-400 bg-emerald-400/10 border-emerald-400/25'
                : 'text-red-400 bg-red-400/10 border-red-400/25'}">
    <span
      class="inline-block w-1.5 h-1.5 rounded-full"
      style="background: {connected ? '#3fb950' : '#f85149'};
             box-shadow: 0 0 5px {connected ? '#3fb95080' : '#f8514980'};
             animation: {connected ? 'pulse-dot 2s ease-in-out infinite' : 'none'};"
    ></span>
    {connected ? "connected" : "disconnected"}
  </div>

  {#if events.length > 0}
    <span class="text-dim font-mono text-xs">{events.length} events</span>
    <button
      on:click={() => (events = [])}
      class="text-xs font-mono text-dim hover:text-muted transition-colors ml-auto"
    >clear</button>
  {/if}
</div>

{#if events.length === 0}
  <div
    class="flex flex-col items-center justify-center h-48 rounded-md gap-3"
    style="border: 1px solid #21262d; background: #0d1117;"
  >
    <div
      class="w-3 h-3 rounded-full"
      style="background: {connected ? '#3fb950' : '#484f58'};
             box-shadow: 0 0 {connected ? '8px' : '0'} {connected ? '#3fb95060' : 'transparent'};
             animation: {connected ? 'pulse-dot 1.5s ease-in-out infinite' : 'none'};"
    ></div>
    <p class="text-dim font-mono text-xs">
      {connected ? "waiting for scan events…" : "connecting…"}
    </p>
  </div>
{:else}
  <div class="rounded-md overflow-hidden" style="border: 1px solid #21262d;">
    <table class="w-full text-sm border-collapse">
      <thead style="background: #0d1117; border-bottom: 1px solid #21262d;">
        <tr>
          <th class="th-static">Time</th>
          <th class="th-static">Node</th>
          <th class="th-static">Type</th>
          <th class="th-static">Devices</th>
        </tr>
      </thead>
      <tbody style="background: #07090d;">
        {#each events as event, i}
          <tr
            class="border-b transition-colors duration-75"
            style="border-color: #161b22; {i === 0 ? 'animation: flash-row 0.4s ease-out;' : ''}"
            on:mouseenter={(e) => { (e.currentTarget as HTMLElement).style.background = '#0d1117'; }}
            on:mouseleave={(e) => { (e.currentTarget as HTMLElement).style.background = 'transparent'; }}
          >
            <td class="py-2.5 pr-4 font-mono text-[11px] text-dim">
              {new Date(event.time).toLocaleTimeString()}
            </td>
            <td class="py-2.5 pr-4 font-mono text-xs text-muted">{event.node_id}</td>
            <td class="py-2.5 pr-4">
              <span class="badge {event.scan_type === 'wifi'
                ? 'text-sky-400 bg-sky-400/10 border-sky-400/20'
                : 'text-violet-400 bg-violet-400/10 border-violet-400/20'}">
                {event.scan_type}
              </span>
            </td>
            <td class="py-2.5 font-mono text-xs text-text">{event.count}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}

<style>
  @keyframes flash-row {
    from { background: rgba(56,189,248,0.08); }
    to   { background: transparent; }
  }
  @keyframes pulse-dot {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0.25; }
  }
</style>
