import { describe, it, expect } from "vitest";
import {
  classifyDevice,
  collectDepartures,
  NEW_DEVICE_WINDOW_MS,
  STALE_MS,
} from "./presence";
import type { DeviceRecord, PresenceEntry } from "./presence";

const NOW = 1_000_000_000_000;

function makeRecord(overrides: Partial<DeviceRecord> = {}): DeviceRecord {
  return {
    mac: "AA:BB:CC:DD:EE:FF",
    device_type: "wifi",
    label: null,
    tag: "unknown",
    first_seen: new Date(NOW - 60 * 60 * 1000).toISOString(), // 1hr ago
    last_seen: new Date(NOW - 60 * 1000).toISOString(),
    vendor: null,
    ssid: null,
    ...overrides,
  };
}

function makeEntry(overrides: Partial<PresenceEntry> = {}): PresenceEntry {
  return {
    mac: "AA:BB:CC:DD:EE:FF",
    category: "unknown",
    label: null,
    vendor: null,
    node_id: "node-1",
    rssi: -70,
    lastSeen: NOW - 60 * 1000,
    ...overrides,
  };
}

describe("classifyDevice", () => {
  it("returns null for ignored devices", () => {
    expect(classifyDevice(makeRecord({ tag: "ignored" }), NOW)).toBe(null);
  });

  it("returns new when first_seen is within 30 minutes", () => {
    const record = makeRecord({
      first_seen: new Date(NOW - 10 * 60 * 1000).toISOString(),
    });
    expect(classifyDevice(record, NOW)).toBe("new");
  });

  it("classifies as new regardless of tag when first_seen is recent", () => {
    const record = makeRecord({
      tag: "known_resident",
      first_seen: new Date(NOW - 5 * 60 * 1000).toISOString(),
    });
    expect(classifyDevice(record, NOW)).toBe("new");
  });

  it("returns unknown for unknown tag beyond new window", () => {
    expect(classifyDevice(makeRecord({ tag: "unknown" }), NOW)).toBe("unknown");
  });

  it("returns known_resident for resident tag beyond new window", () => {
    expect(
      classifyDevice(makeRecord({ tag: "known_resident" }), NOW)
    ).toBe("known_resident");
  });

  it("returns known_vehicle for vehicle tag beyond new window", () => {
    expect(
      classifyDevice(makeRecord({ tag: "known_vehicle" }), NOW)
    ).toBe("known_vehicle");
  });

  it("returns unknown when record is undefined (MAC not in table)", () => {
    expect(classifyDevice(undefined, NOW)).toBe("unknown");
  });
});

describe("collectDepartures", () => {
  it("returns empty when no entries are stale", () => {
    const map = new Map([
      ["AA:BB:CC:DD:EE:FF", makeEntry({ lastSeen: NOW - 60 * 1000 })],
    ]);
    const { departed, active } = collectDepartures(map, NOW, STALE_MS);
    expect(departed).toHaveLength(0);
    expect(active.size).toBe(1);
  });

  it("removes stale entries and returns them as departed", () => {
    const staleEntry = makeEntry({ lastSeen: NOW - 6 * 60 * 1000 });
    const freshEntry = makeEntry({
      mac: "11:22:33:44:55:66",
      lastSeen: NOW - 60 * 1000,
    });
    const map = new Map([
      ["AA:BB:CC:DD:EE:FF", staleEntry],
      ["11:22:33:44:55:66", freshEntry],
    ]);
    const { departed, active } = collectDepartures(map, NOW, STALE_MS);
    expect(departed).toHaveLength(1);
    expect(departed[0].mac).toBe("AA:BB:CC:DD:EE:FF");
    expect(active.size).toBe(1);
    expect(active.has("11:22:33:44:55:66")).toBe(true);
  });

  it("does not mutate the input map", () => {
    const map = new Map([
      ["AA:BB:CC:DD:EE:FF", makeEntry({ lastSeen: NOW - 6 * 60 * 1000 })],
    ]);
    collectDepartures(map, NOW, STALE_MS);
    expect(map.size).toBe(1);
  });
});
