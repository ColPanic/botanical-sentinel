<script lang="ts">
  import type { PageData } from "./$types";

  export let data: PageData;

  type Node = (typeof data.nodes)[0];

  // ── Sort ──────────────────────────────────────────────────────────────────

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

  function sortIcon(key: string) {
    if (sortKey !== key) return "";
    return sortDir === "asc" ? " ↑" : " ↓";
  }

  // ── Staleness ─────────────────────────────────────────────────────────────

  function statusColor(lastSeen: string): string {
    const diff = (Date.now() - new Date(lastSeen).getTime()) / 1000;
    if (diff < 60)  return "#3fb950";  // green  — seen < 1 min
    if (diff < 300) return "#e3b341";  // amber  — seen < 5 min
    return "#f85149";                  // red    — stale
  }

  function relativeTime(ts: string): string {
    const diff = Math.round((Date.now() - new Date(ts).getTime()) / 1000);
    if (diff < 60)   return `${diff}s ago`;
    if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
    return `${Math.round(diff / 3600)}h ago`;
  }
</script>

<svelte:head><title>Nodes — botanical-sentinel</title></svelte:head>

<div class="flex items-center gap-3 mb-5">
  <h1 class="font-display text-lg font-bold tracking-widest uppercase text-text">Nodes</h1>
  <span class="text-dim font-mono text-xs">{data.nodes.length} online</span>
</div>

<div class="rounded-md overflow-hidden" style="border: 1px solid #21262d;">
  <table class="w-full text-sm border-collapse">
    <thead style="background: #0d1117; border-bottom: 1px solid #21262d;">
      <tr>
        {#each [["node_id","Node ID"],["node_type","Type"],["location","Location"],["firmware_ver","Firmware"],["last_seen","Last Seen"]] as [key, col]}
          <th class="th" on:click={() => toggleSort(key)}>{col}{sortIcon(key)}</th>
        {/each}
      </tr>
    </thead>
    <tbody style="background: #07090d;">
      {#each sorted as node}
        {@const color = statusColor(node.last_seen)}
        <tr
          class="border-b transition-colors duration-75"
          style="border-color: #161b22;"
          on:mouseenter={(e) => { (e.currentTarget as HTMLElement).style.background = '#0d1117'; }}
          on:mouseleave={(e) => { (e.currentTarget as HTMLElement).style.background = 'transparent'; }}
        >
          <!-- Node ID with status dot -->
          <td class="py-2.5 pr-4">
            <div class="flex items-center gap-2">
              <span
                class="inline-block w-1.5 h-1.5 rounded-full flex-shrink-0"
                style="background: {color}; box-shadow: 0 0 5px {color}80;"
              ></span>
              <span class="font-mono text-xs text-text">{node.node_id}</span>
            </div>
          </td>

          <!-- Type -->
          <td class="py-2.5 pr-4">
            <span class="badge text-sky-400 bg-sky-400/10 border-sky-400/20">{node.node_type}</span>
          </td>

          <!-- Location -->
          <td class="py-2.5 pr-4 font-mono text-xs text-muted">
            {#if node.location}
              {node.location}
            {:else}
              <span class="text-dim">—</span>
            {/if}
          </td>

          <!-- Firmware -->
          <td class="py-2.5 pr-4 font-mono text-xs text-dim">{node.firmware_ver || "—"}</td>

          <!-- Last seen -->
          <td class="py-2.5">
            <div class="font-mono text-xs" style="color: {color};">{relativeTime(node.last_seen)}</div>
            <div class="font-mono text-[10px] text-dim mt-0.5">
              {new Date(node.last_seen).toLocaleString()}
            </div>
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>
