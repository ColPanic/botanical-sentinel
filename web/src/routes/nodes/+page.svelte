<script lang="ts">
  import type { PageData } from "./$types";

  export let data: PageData;

  type Node = (typeof data.nodes)[0];

  let sortKey = "last_seen";
  let sortDir: "asc" | "desc" = "desc";

  function toggleSort(key: string) {
    if (sortKey === key) sortDir = sortDir === "asc" ? "desc" : "asc";
    else { sortKey = key; sortDir = "asc"; }
  }

  function sortVal(n: Node, key: string): string | number {
    const v = (n as Record<string, unknown>)[key];
    if (key === "last_seen") return new Date(v as string).getTime();
    return String(v ?? "").toLowerCase();
  }

  $: sorted = [...data.nodes].sort((a, b) => {
    const av = sortVal(a, sortKey);
    const bv = sortVal(b, sortKey);
    const cmp = av < bv ? -1 : av > bv ? 1 : 0;
    return sortDir === "asc" ? cmp : -cmp;
  });

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
      <tr class="text-left border-b border-zinc-700 select-none">
        {#each [["node_id","Node ID"],["node_type","Type"],["location","Location"],["firmware_ver","Firmware"],["last_seen","Last Seen"]] as [key, label]}
          <th
            class="py-2 pr-4 cursor-pointer hover:text-white whitespace-nowrap"
            on:click={() => toggleSort(key)}
          >{label}{#if sortKey === key}<span class="ml-1 text-zinc-400">{sortDir === "asc" ? "↑" : "↓"}</span>{/if}</th>
        {/each}
      </tr>
    </thead>
    <tbody>
      {#each sorted as node}
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
