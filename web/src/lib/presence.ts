// type-only import+re-export: must stay `import type` to avoid loading SvelteKit runtime in vitest
import type { DeviceRecord } from "./api";
export type { DeviceRecord };

export type DeviceCategory =
  | "new"
  | "unknown"
  | "known_resident"
  | "known_vehicle";

export type PresenceEntry = {
  mac: string;
  category: DeviceCategory;
  label: string | null;
  vendor: string | null;
  node_id: string;
  rssi: number;
  lastSeen: number;
};

export type FeedEvent = {
  id: string;
  direction: "arrival" | "departure";
  category: DeviceCategory;
  mac: string;
  label: string | null;
  vendor: string | null;
  node_id: string;
  time: number;
};

export const NEW_DEVICE_WINDOW_MS = 30 * 60 * 1000;
export const STALE_MS = 5 * 60 * 1000;
export const MAX_FEED_EVENTS = 50;
export const PRESENCE_WINDOW_MS = 5 * 60 * 1000;

/**
 * Determines the display category for a device.
 * Returns null if the device should be excluded (ignored tag).
 */
export function classifyDevice(
  record: DeviceRecord | undefined,
  now: number
): DeviceCategory | null {
  if (!record) return "unknown";
  if (record.tag === "ignored") return null;
  if (now - new Date(record.first_seen).getTime() < NEW_DEVICE_WINDOW_MS) {
    return "new";
  }
  if (record.tag === "known_resident") return "known_resident";
  if (record.tag === "known_vehicle") return "known_vehicle";
  return "unknown";
}

/**
 * Returns true if this category generates feed events on arrival/departure.
 * Unknown devices only appear in the "here now" list, not the feed.
 */
export function hasFeedEvent(category: DeviceCategory): boolean {
  return category !== "unknown";
}

/**
 * Scans the presence map for stale entries.
 * Returns departed entries and a new map with them removed.
 * Does not mutate the input map.
 */
export function collectDepartures(
  presenceMap: Map<string, PresenceEntry>,
  now: number,
  staleMs: number
): { departed: PresenceEntry[]; active: Map<string, PresenceEntry> } {
  const departed: PresenceEntry[] = [];
  const active = new Map<string, PresenceEntry>();

  for (const [mac, entry] of presenceMap) {
    if (now - entry.lastSeen > staleMs) {
      departed.push(entry);
    } else {
      active.set(mac, entry);
    }
  }

  return { departed, active };
}
