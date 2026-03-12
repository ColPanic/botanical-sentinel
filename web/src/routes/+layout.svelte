<script lang="ts">
  import favicon from "$lib/assets/favicon.svg";
  import "../app.css";

  let { children } = $props();
</script>

<svelte:head>
  <link rel="icon" href={favicon} />
</svelte:head>

<div class="min-h-screen bg-zinc-900 text-zinc-100 font-sans">
  <nav class="px-6 py-3 border-b border-zinc-800 flex gap-6 text-sm">
    <a href="/" class="font-semibold text-white">botanical-sentinel</a>
    <a href="/map" class="text-zinc-400 hover:text-white">Map</a>
    <a href="/nodes" class="text-zinc-400 hover:text-white">Nodes</a>
    <a href="/devices" class="text-zinc-400 hover:text-white">Devices</a>
    <a href="/scan" class="text-zinc-400 hover:text-white">Live Scan</a>
  </nav>
  {@render children()}
</div>
