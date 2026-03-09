<script lang="ts">
  import { enhance } from "$app/forms";
  import { invalidateAll } from "$app/navigation";
  import type { PageData } from "./$types";
  import { setDeviceLabel } from "$lib/api";

  export let data: PageData;

  const TAGS = ["unknown", "known_resident", "known_vehicle", "ignored"];

  const TAG_COLOR: Record<string, string> = {
    unknown: "text-yellow-400",
    known_resident: "text-green-400",
    known_vehicle: "text-blue-400",
    ignored: "text-zinc-500",
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

  $: allSelected = sorted.length > 0 && sorted.every((d) => selected.has(d.mac));
  $: someSelected = !allSelected && sorted.some((d) => selected.has(d.mac));

  function toggleDevice(mac: string) {
    if (selected.has(mac)) selected.delete(mac);
    else selected.add(mac);
    selected = selected;
  }

  function toggleAll() {
    selected = allSelected ? new Set() : new Set(sorted.map((d) => d.mac));
  }

  // ── Bulk label ────────────────────────────────────────────────────────────

  let bulkLabel = "";
  let applying = false;

  async function applyBulkLabel() {
    if (!bulkLabel.trim() || selected.size === 0) return;
    applying = true;
    await Promise.all([...selected].map((mac) => setDeviceLabel(mac, bulkLabel.trim())));
    await invalidateAll();
    selected = new Set();
    bulkLabel = "";
    applying = false;
  }
</script>

<svelte:head><title>Devices — botanical-sentinel</title></svelte:head>

<div class="p-6">
  <div class="flex items-center gap-4 mb-4">
    <h1 class="text-xl font-semibold">Devices</h1>
    <div class="flex gap-2 text-sm">
      <a href="/devices" class="px-2 py-1 rounded {!data.activeTag ? 'bg-zinc-700' : 'text-zinc-400 hover:text-white'}">All</a>
      {#each TAGS as tag}
        <a href="/devices?tag={tag}" class="px-2 py-1 rounded {data.activeTag === tag ? 'bg-zinc-700' : 'text-zinc-400 hover:text-white'}">{tag}</a>
      {/each}
    </div>
  </div>

  {#if selected.size > 0}
    <div class="flex items-center gap-3 mb-3 px-3 py-2 bg-zinc-800 rounded text-sm">
      <span class="text-zinc-400">{selected.size} selected</span>
      <input
        type="text"
        bind:value={bulkLabel}
        placeholder="label for selected…"
        class="bg-transparent border-b border-zinc-600 focus:border-zinc-300 outline-none text-sm w-48"
        on:keydown={(e) => e.key === "Enter" && applyBulkLabel()}
      />
      <button
        on:click={applyBulkLabel}
        disabled={applying || !bulkLabel.trim()}
        class="px-2 py-0.5 rounded bg-zinc-700 hover:bg-zinc-600 disabled:opacity-40 disabled:cursor-not-allowed"
      >{applying ? "Applying…" : "Apply"}</button>
      <button
        on:click={() => (selected = new Set())}
        class="text-zinc-500 hover:text-white"
      >Clear</button>
    </div>
  {/if}

  <table class="w-full text-sm border-collapse">
    <thead>
      <tr class="text-left border-b border-zinc-700 select-none">
        <th class="py-2 pr-3 w-6">
          <input
            type="checkbox"
            checked={allSelected}
            bind:indeterminate={someSelected}
            on:click={toggleAll}
            class="cursor-pointer accent-zinc-400"
          />
        </th>
        {#each [["name","Device"],["vendor","Vendor"],["device_type","Type"]] as [key, col]}
          <th
            class="py-2 pr-4 cursor-pointer hover:text-white whitespace-nowrap"
            on:click={() => toggleSort(key)}
          >{col}{#if sortKey === key}<span class="ml-1 text-zinc-400">{sortDir === "asc" ? "↑" : "↓"}</span>{/if}</th>
        {/each}
        <th class="py-2 pr-4">Label</th>
        <th
          class="py-2 pr-4 cursor-pointer hover:text-white whitespace-nowrap"
          on:click={() => toggleSort("tag")}
        >Tag{#if sortKey === "tag"}<span class="ml-1 text-zinc-400">{sortDir === "asc" ? "↑" : "↓"}</span>{/if}</th>
        <th
          class="py-2 cursor-pointer hover:text-white whitespace-nowrap"
          on:click={() => toggleSort("last_seen")}
        >Last Seen{#if sortKey === "last_seen"}<span class="ml-1 text-zinc-400">{sortDir === "asc" ? "↑" : "↓"}</span>{/if}</th>
      </tr>
    </thead>
    <tbody>
      {#each sorted as device}
        <tr class="border-b border-zinc-800 {selected.has(device.mac) ? 'bg-zinc-800/50' : ''}">
          <td class="py-2 pr-3">
            <input
              type="checkbox"
              checked={selected.has(device.mac)}
              on:click={() => toggleDevice(device.mac)}
              class="cursor-pointer accent-zinc-400"
            />
          </td>
          <td class="py-2 pr-4">
            {#if device.label || device.ssid}
              <span class="text-sm">{device.label ?? device.ssid}</span>
              <span class="block font-mono text-xs text-zinc-500">{device.mac}</span>
            {:else}
              <span class="font-mono text-xs">{device.mac}</span>
            {/if}
          </td>
          <td class="py-2 pr-4 text-zinc-400 text-xs">{device.vendor ?? "—"}</td>
          <td class="py-2 pr-4 text-zinc-400">{device.device_type}</td>
          <td class="py-2 pr-4">
            <form method="POST" action="?/label" use:enhance class="flex gap-1">
              <input type="hidden" name="mac" value={device.mac} />
              <input
                type="text"
                name="label"
                value={device.label ?? ""}
                placeholder="add label"
                class="bg-transparent border-b border-zinc-600 focus:border-zinc-300 outline-none text-sm w-32"
              />
              <button type="submit" class="text-xs text-zinc-500 hover:text-white">✓</button>
            </form>
          </td>
          <td class="py-2 pr-4">
            <form method="POST" action="?/tag" use:enhance>
              <input type="hidden" name="mac" value={device.mac} />
              <select
                name="tag"
                on:change={(e) => (e.currentTarget as HTMLSelectElement).form?.submit()}
                class="bg-zinc-800 border border-zinc-600 rounded px-1 py-0.5 text-xs {TAG_COLOR[device.tag]}"
              >
                {#each TAGS as tag}
                  <option value={tag} selected={device.tag === tag}>{tag}</option>
                {/each}
              </select>
            </form>
          </td>
          <td class="py-2 text-zinc-400 text-xs">
            {new Date(device.last_seen).toLocaleString()}
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>
