<script lang="ts">
  import { enhance } from "$app/forms";
  import { invalidateAll } from "$app/navigation";
  import { slide } from "svelte/transition";
  import type { PageData } from "./$types";
  import { setDeviceLabel, setDeviceTag } from "$lib/api";

  export let data: PageData;

  const TAGS = ["unknown", "known_resident", "known_vehicle", "ignored"];

  const TAG_BADGE: Record<string, string> = {
    unknown:        "text-amber-400 bg-amber-400/10 border-amber-400/20",
    known_resident: "text-emerald-400 bg-emerald-400/10 border-emerald-400/20",
    known_vehicle:  "text-sky-400 bg-sky-400/10 border-sky-400/20",
    ignored:        "text-zinc-500 bg-zinc-700/30 border-zinc-600/30",
  };

  const TYPE_BADGE: Record<string, string> = {
    ble:  "text-violet-400 bg-violet-400/10 border-violet-400/20",
    wifi: "text-sky-400 bg-sky-400/10 border-sky-400/20",
  };

  type Device = (typeof data.devices)[0];

  // ── Sort ──────────────────────────────────────────────────────────────────

  let sortKey = "last_seen";
  let sortDir: "asc" | "desc" = "desc";

  function toggleSort(key: string) {
    if (sortKey === key) sortDir = sortDir === "asc" ? "desc" : "asc";
    else { sortKey = key; sortDir = "asc"; }
  }

  function sortVal(d: Device, key: string): string | number {
    if (key === "name") return (d.label ?? d.ssid ?? d.mac).toLowerCase();
    const v = (d as Record<string, unknown>)[key];
    if (key === "last_seen") return new Date(v as string).getTime();
    return String(v ?? "").toLowerCase();
  }

  $: sorted = [...data.devices].sort((a, b) => {
    const av = sortVal(a, sortKey);
    const bv = sortVal(b, sortKey);
    const cmp = av < bv ? -1 : av > bv ? 1 : 0;
    return sortDir === "asc" ? cmp : -cmp;
  });

  // ── Selection ─────────────────────────────────────────────────────────────

  let selected = new Set<string>();

  $: allSelected  = sorted.length > 0 && sorted.every((d) => selected.has(d.mac));
  $: someSelected = !allSelected && sorted.some((d) => selected.has(d.mac));

  function toggleDevice(mac: string) {
    if (selected.has(mac)) selected.delete(mac);
    else selected.add(mac);
    selected = selected;
  }

  function toggleAll() {
    selected = allSelected ? new Set() : new Set(sorted.map((d) => d.mac));
  }

  // ── Bulk actions ──────────────────────────────────────────────────────────

  let bulkLabel = "";
  let bulkTag   = "";
  let applying  = false;
  let applyError = "";

  async function applyBulk() {
    if (selected.size === 0) return;
    if (!bulkLabel.trim() && !bulkTag) return;
    applying = true;
    applyError = "";
    try {
      const macs = [...selected];
      const ops: Promise<unknown>[] = [];
      if (bulkLabel.trim()) ops.push(...macs.map((mac) => setDeviceLabel(mac, bulkLabel.trim())));
      if (bulkTag)           ops.push(...macs.map((mac) => setDeviceTag(mac, bulkTag)));
      await Promise.all(ops);
      await invalidateAll();
      selected  = new Set();
      bulkLabel = "";
      bulkTag   = "";
    } catch (e) {
      applyError = e instanceof Error ? e.message : "Apply failed";
    } finally {
      applying = false;
    }
  }

  $: bulkDisabled = applying || (!bulkLabel.trim() && !bulkTag);

  function sortIcon(key: string) {
    if (sortKey !== key) return "";
    return sortDir === "asc" ? " ↑" : " ↓";
  }
</script>

<svelte:head><title>Devices — botanical-sentinel</title></svelte:head>

<!-- Header row -->
<div class="flex items-center gap-4 mb-5">
  <h1 class="font-display text-lg font-bold tracking-widest uppercase text-text">Devices</h1>
  <span class="text-dim font-mono text-xs">{data.devices.length} total</span>

  <div class="flex gap-1 ml-2 flex-wrap">
    <a
      href="/devices"
      class="px-2.5 py-1 rounded text-xs font-mono tracking-wide transition-colors
             {!data.activeTag ? 'bg-accent/15 text-accent border border-accent/30' : 'text-muted hover:text-text border border-transparent'}"
    >all</a>
    {#each ["unknown","known_resident","known_vehicle","ignored"] as tag}
      <a
        href="/devices?tag={tag}"
        class="px-2.5 py-1 rounded text-xs font-mono tracking-wide transition-colors
               {data.activeTag === tag ? 'bg-accent/15 text-accent border border-accent/30' : 'text-muted hover:text-text border border-transparent'}"
      >{tag}</a>
    {/each}
  </div>
</div>

<!-- Bulk action bar -->
{#if selected.size > 0}
  <div
    transition:slide={{ duration: 180 }}
    class="flex flex-wrap items-center gap-3 mb-4 px-4 py-2.5 rounded-md"
    style="background: rgba(56,189,248,0.05); border: 1px solid rgba(56,189,248,0.18);"
  >
    <span class="text-xs font-mono text-accent font-medium">{selected.size} selected</span>

    <div class="h-3 w-px bg-line"></div>

    <input
      type="text"
      bind:value={bulkLabel}
      placeholder="set label…"
      class="bg-transparent border-b border-bright focus:border-accent outline-none text-sm text-text placeholder:text-dim w-36 transition-colors"
      on:keydown={(e) => e.key === "Enter" && applyBulk()}
    />

    <select
      bind:value={bulkTag}
      class="bg-raised border border-line rounded px-2 py-1 text-xs font-mono text-muted focus:border-accent outline-none transition-colors cursor-pointer"
    >
      <option value="">set tag…</option>
      {#each TAGS as tag}<option value={tag}>{tag}</option>{/each}
    </select>

    <button
      on:click={applyBulk}
      disabled={bulkDisabled}
      class="px-3 py-1 rounded text-xs font-mono font-medium transition-all
             {bulkDisabled
               ? 'bg-raised text-dim cursor-not-allowed border border-line'
               : 'bg-accent/15 text-accent border border-accent/30 hover:bg-accent/25'}"
    >{applying ? "applying…" : "Apply"}</button>

    <button
      on:click={() => (selected = new Set())}
      class="text-xs font-mono text-dim hover:text-muted transition-colors"
    >clear</button>

    {#if applyError}
      <span class="text-xs font-mono text-red-400">{applyError}</span>
    {/if}
  </div>
{/if}

<!-- Table -->
<div class="rounded-md overflow-hidden" style="border: 1px solid #21262d;">
  <table class="w-full text-sm border-collapse">
    <thead style="background: #0d1117; border-bottom: 1px solid #21262d;">
      <tr>
        <th class="th-static pl-4 pr-3 w-8">
          <input
            type="checkbox"
            checked={allSelected}
            bind:indeterminate={someSelected}
            on:click={toggleAll}
          />
        </th>
        {#each [["name","Device"],["vendor","Vendor"],["device_type","Type"]] as [key, col]}
          <th class="th" on:click={() => toggleSort(key)}>{col}{sortIcon(key)}</th>
        {/each}
        <th class="th-static">Label</th>
        <th class="th" on:click={() => toggleSort("tag")}>Tag{sortIcon("tag")}</th>
        <th class="th" on:click={() => toggleSort("last_seen")}>Last Seen{sortIcon("last_seen")}</th>
        <th class="th-static"></th>
      </tr>
    </thead>
    <tbody style="background: #07090d;">
      {#each sorted as device}
        {@const sel = selected.has(device.mac)}
        <tr
          class="border-b transition-colors duration-75 cursor-default"
          style="border-color: #161b22; background: {sel ? 'rgba(56,189,248,0.05)' : 'transparent'};"
          on:mouseenter={(e) => { if (!sel) (e.currentTarget as HTMLElement).style.background = '#0d1117'; }}
          on:mouseleave={(e) => { if (!sel) (e.currentTarget as HTMLElement).style.background = 'transparent'; }}
        >
          <!-- Checkbox -->
          <td class="pl-4 pr-3 py-2.5">
            <input
              type="checkbox"
              checked={sel}
              on:click={() => toggleDevice(device.mac)}
            />
          </td>

          <!-- Device name / MAC -->
          <td class="py-2.5 pr-4 max-w-[220px]">
            {#if device.label || device.ssid}
              <div class="text-text text-sm font-medium truncate">{device.label ?? device.ssid}</div>
              <div class="font-mono text-[11px] text-dim mt-0.5">{device.mac}</div>
            {:else}
              <div class="font-mono text-xs text-muted">{device.mac}</div>
            {/if}
          </td>

          <!-- Vendor -->
          <td class="py-2.5 pr-4 text-muted text-xs max-w-[160px] truncate">
            {device.vendor ?? <span class="text-dim">—</span>}
          </td>

          <!-- Type badge -->
          <td class="py-2.5 pr-4">
            <span class="badge {TYPE_BADGE[device.device_type] ?? 'text-muted border-bright'}">
              {device.device_type}
            </span>
          </td>

          <!-- Label input -->
          <td class="py-2.5 pr-4">
            <form method="POST" action="?/label" use:enhance class="flex items-center gap-1">
              <input type="hidden" name="mac" value={device.mac} />
              <input
                type="text"
                name="label"
                value={device.label ?? ""}
                placeholder="add label"
                class="bg-transparent border-b border-bright focus:border-accent outline-none text-xs text-text placeholder:text-dim w-28 transition-colors"
              />
              <button type="submit" class="text-dim hover:text-accent transition-colors text-xs ml-1">✓</button>
            </form>
          </td>

          <!-- Tag badge (clickable select overlay) -->
          <td class="py-2.5 pr-4">
            <form method="POST" action="?/tag" use:enhance>
              <input type="hidden" name="mac" value={device.mac} />
              <div class="relative inline-flex">
                <span class="badge {TAG_BADGE[device.tag] ?? 'text-muted border-bright'}">{device.tag}</span>
                <select
                  name="tag"
                  on:change={(e) => (e.currentTarget as HTMLSelectElement).form?.submit()}
                  class="absolute inset-0 opacity-0 cursor-pointer w-full"
                  aria-label="Change tag"
                >
                  {#each TAGS as tag}
                    <option value={tag} selected={device.tag === tag}>{tag}</option>
                  {/each}
                </select>
              </div>
            </form>
          </td>

          <!-- Last seen -->
          <td class="py-2.5 font-mono text-[11px] text-dim whitespace-nowrap">
            {new Date(device.last_seen).toLocaleString()}
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>
