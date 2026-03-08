<script lang="ts">
  import type { PageData } from "./$types";

  export let data: PageData;

  function staleness(lastSeen: string): string {
    const diff = (Date.now() - new Date(lastSeen).getTime()) / 1000;
    if (diff < 60) return "text-green-400";
    if (diff < 300) return "text-yellow-400";
    return "text-red-400";
  }

  function relativeTime(ts: string): string {
    const diff = Math.round((Date.now() - new Date(ts).getTime()) / 1000);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
    return `${Math.round(diff / 3600)}h ago`;
  }
</script>

<svelte:head><title>Nodes — botanical-sentinel</title></svelte:head>

<div class="p-6">
  <h1 class="text-xl font-semibold mb-4">Nodes</h1>
  <table class="w-full text-sm border-collapse">
    <thead>
      <tr class="text-left border-b border-zinc-700">
        <th class="py-2 pr-4">Node ID</th>
        <th class="py-2 pr-4">Type</th>
        <th class="py-2 pr-4">Location</th>
        <th class="py-2 pr-4">Firmware</th>
        <th class="py-2">Last Seen</th>
      </tr>
    </thead>
    <tbody>
      {#each data.nodes as node}
        <tr class="border-b border-zinc-800">
          <td class="py-2 pr-4 font-mono">{node.node_id}</td>
          <td class="py-2 pr-4 text-zinc-400">{node.node_type}</td>
          <td class="py-2 pr-4 text-zinc-400">{node.location ?? "—"}</td>
          <td class="py-2 pr-4 text-zinc-400">{node.firmware_ver}</td>
          <td class="py-2 {staleness(node.last_seen)}">{relativeTime(node.last_seen)}</td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>
