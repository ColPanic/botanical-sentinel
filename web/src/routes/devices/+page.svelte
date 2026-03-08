<script lang="ts">
  import { enhance } from "$app/forms";
  import type { PageData } from "./$types";

  export let data: PageData;

  const TAGS = ["unknown", "known_resident", "known_vehicle", "ignored"];

  const TAG_COLOR: Record<string, string> = {
    unknown: "text-yellow-400",
    known_resident: "text-green-400",
    known_vehicle: "text-blue-400",
    ignored: "text-zinc-500",
  };
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

  <table class="w-full text-sm border-collapse">
    <thead>
      <tr class="text-left border-b border-zinc-700">
        <th class="py-2 pr-4">MAC</th>
        <th class="py-2 pr-4">Vendor</th>
        <th class="py-2 pr-4">Type</th>
        <th class="py-2 pr-4">Label</th>
        <th class="py-2 pr-4">Tag</th>
        <th class="py-2">Last Seen</th>
      </tr>
    </thead>
    <tbody>
      {#each data.devices as device}
        <tr class="border-b border-zinc-800">
          <td class="py-2 pr-4 font-mono text-xs">{device.mac}</td>
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
