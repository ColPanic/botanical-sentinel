# Node Marker Visibility on Map

## Problem

Nodes and devices on the map page use similar circular markers with overlapping color palettes (green, yellow, gray). At a glance, it's unclear which markers are scanner nodes (infrastructure) and which are detected devices.

## Design

Replace the 16px circle `divIcon` for nodes with an SVG antenna tower icon and a permanent name label.

### Marker

- **Shape**: Inline SVG radio tower (28×28px) rendered via `L.divIcon`
- **SVG markup** (color interpolated via `makeNodeIcon(color)`):
  ```html
  <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
    <path d="M14 2 L14 22" stroke="${color}" stroke-width="3" stroke-linecap="round"/>
    <path d="M7 8 L14 4 L21 8" stroke="${color}" stroke-width="2" fill="none"
          stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M4 14 L14 8 L24 14" stroke="${color}" stroke-width="2" fill="none"
          stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="14" cy="24" r="3" fill="${color}"/>
  </svg>
  ```
- **Icon anchor**: `[14, 28]` (bottom-center) so tooltip and click target align correctly
- **Icon size**: `[28, 28]` matching the SVG viewBox
- **Colors**: Same green/yellow/gray status scheme based on `last_seen` age — applied to SVG stroke and fill
  - Green (`#4ade80`): seen within 2 minutes
  - Yellow (`#facc15`): seen within 10 minutes (also used for unconfirmed placements)
  - Gray (`#71717a`): older than 10 minutes
- **Label**: Permanent Leaflet tooltip showing `node.name ?? node.node_id`
  - Options: `{ permanent: true, direction: 'bottom', offset: [0, 0], className: 'node-label' }`
  - Suppress default tooltip chrome (white bubble, shadow) via `:global(.node-label)` — Leaflet injects tooltips outside Svelte's scoped DOM

### Scope

Changes are limited to `web/src/routes/map/+page.svelte`:

1. **`makeNodeIcon(color)`** — replace the circle `div` HTML with the antenna tower SVG; set `iconSize: [28, 28]`, `iconAnchor: [14, 28]`
2. **`loadNodes()`** — change `bindTooltip` to `{ permanent: true, direction: 'bottom', offset: [0, 0], className: 'node-label' }`
3. **`startPlacement()`** — same icon and tooltip changes for newly placed nodes
4. **`<style>` block** — add `:global(.node-label)` rule to strip Leaflet's default tooltip bubble (background, border, shadow) and style as a small monospace label

### Not in scope

- Device markers unchanged (remain as `circleMarker` with tag-based colors)
- No API changes
- No new dependencies
