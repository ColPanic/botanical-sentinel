# Node Marker Visibility on Map

## Problem

Nodes and devices on the map page use similar circular markers with overlapping color palettes (green, yellow, gray). At a glance, it's unclear which markers are scanner nodes (infrastructure) and which are detected devices.

## Design

Replace the 16px circle `divIcon` for nodes with an SVG antenna tower icon and a permanent name label.

### Marker

- **Shape**: Inline SVG radio tower (~28px) rendered via `L.divIcon`
- **Colors**: Same green/yellow/gray status scheme based on `last_seen` age — applied to SVG stroke and fill
  - Green (`#4ade80`): seen within 2 minutes
  - Yellow (`#facc15`): seen within 10 minutes
  - Gray (`#71717a`): older than 10 minutes
- **Label**: Permanent tooltip showing `node.name ?? node.node_id`, positioned below the icon

### Scope

Changes are limited to `web/src/routes/map/+page.svelte`:

1. **`makeNodeIcon(color)`** — replace the circle `div` HTML with the antenna tower SVG, sized at 28px
2. **`loadNodes()`** — change `bindTooltip(label, { permanent: false })` to `{ permanent: true, direction: 'bottom', className: 'node-label' }` and add a small CSS class for the label style
3. **`startPlacement()`** — same icon change for newly placed nodes

### Not in scope

- Device markers unchanged (remain as `circleMarker` with tag-based colors)
- No API changes
- No new dependencies
