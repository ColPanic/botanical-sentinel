<script lang="ts">
  import { page } from "$app/state";
  import "../app.css";

  let { children } = $props();

  const links = [
    { href: "/nodes",   label: "Nodes" },
    { href: "/devices", label: "Devices" },
    { href: "/scan",    label: "Live Scan" },
  ];
</script>

<svelte:head>
  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'><circle cx='8' cy='8' r='6' fill='%2338bdf8' opacity='.9'/></svg>" />
</svelte:head>

<div class="min-h-screen bg-bg text-text font-sans">
  <nav
    class="sticky top-0 z-50 flex items-center gap-8 px-6 h-12"
    style="
      background: linear-gradient(to bottom, #0d1117, #0a0e14);
      border-bottom: 1px solid #21262d;
      box-shadow: 0 1px 0 0 rgba(56,189,248,0.06);
    "
  >
    <a
      href="/"
      class="flex items-center gap-2 font-display text-sm font-bold tracking-wider text-text hover:text-accent transition-colors"
      style="letter-spacing: 0.12em;"
    >
      <span
        class="inline-block w-2 h-2 rounded-full bg-accent"
        style="box-shadow: 0 0 6px 1px rgba(56,189,248,0.6);"
      ></span>
      BOTANICAL-SENTINEL
    </a>

    <div class="flex items-center gap-1 ml-2">
      {#each links as link}
        {@const active = page.url.pathname.startsWith(link.href)}
        <a
          href={link.href}
          class="relative px-3 py-1 text-xs font-mono font-medium tracking-widest uppercase transition-colors duration-150 rounded
                 {active ? 'text-accent' : 'text-muted hover:text-text'}"
        >
          {link.label}
          {#if link.href === "/scan"}
            <span class="ml-1.5 inline-block w-1.5 h-1.5 rounded-full bg-emerald-400 align-middle"
              style="animation: pulse-dot 2s ease-in-out infinite;"></span>
          {/if}
          {#if active}
            <span
              class="absolute bottom-0 left-3 right-3 h-px bg-accent rounded-full"
              style="box-shadow: 0 0 4px rgba(56,189,248,0.8);"
            ></span>
          {/if}
        </a>
      {/each}
    </div>
  </nav>

  <main class="px-6 py-6 max-w-[1400px] mx-auto">
    {@render children()}
  </main>
</div>

<style>
  @keyframes pulse-dot {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0.3; }
  }
</style>
