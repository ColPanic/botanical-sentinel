import { env } from "$env/dynamic/public";
import { browser } from "$app/environment";

// Server-side (SSR load functions): localhost:8000 is reachable directly.
// Browser-side (onMount, client fetches): use PUBLIC_API_URL if set, otherwise
// fall back to relative paths so Vite's dev-server proxy can route them correctly
// regardless of which hostname/IP the browser used to reach the dev server.
const BASE = env.PUBLIC_API_URL ?? (browser ? "" : "http://localhost:8000");

export async function fetchNodes() {
  const res = await fetch(`${BASE}/nodes`);
  if (!res.ok) throw new Error(`GET /nodes failed: ${res.status}`);
  return res.json();
}

export type DeviceRecord = {
  mac: string;
  device_type: string;
  label: string | null;
  tag: string;
  first_seen: string;
  last_seen: string;
  vendor: string | null;
  ssid: string | null;
};

export type ScanBatch = {
  node_id: string;
  scan_type: string;
  devices: Array<{ mac: string; rssi: number; ssid: string | null }>;
};

export async function fetchDevices(tag?: string): Promise<DeviceRecord[]> {
  const url = tag ? `${BASE}/devices?tag=${tag}` : `${BASE}/devices`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`GET /devices failed: ${res.status}`);
  return res.json();
}

export async function fetchRecentScan(nodeId?: string, limit = 100) {
  const path = nodeId ? `/scan/${nodeId}/recent` : "/scan/recent";
  const res = await fetch(`${BASE}${path}?limit=${limit}`);
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
  return res.json();
}

export async function setDeviceLabel(mac: string, label: string) {
  const res = await fetch(`${BASE}/devices/${mac}/label`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label }),
  });
  if (!res.ok) throw new Error(`PUT /devices/${mac}/label failed: ${res.status}`);
  return res.json();
}

export async function setDeviceTag(mac: string, tag: string) {
  const res = await fetch(`${BASE}/devices/${mac}/tag`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tag }),
  });
  if (!res.ok) throw new Error(`PUT /devices/${mac}/tag failed: ${res.status}`);
  return res.json();
}

export function liveWebSocket(onMessage: (data: unknown) => void): WebSocket {
  // When PUBLIC_API_URL is set, connect directly to the API host.
  // Otherwise use a relative URL so Vite's proxy (or any reverse proxy) routes it.
  const wsUrl = env.PUBLIC_API_URL
    ? `${env.PUBLIC_API_URL.replace(/^http/, "ws")}/live`
    : `${location.protocol.replace("http", "ws")}//${location.host}/live`;
  const ws = new WebSocket(wsUrl);
  ws.onmessage = (e) => onMessage(JSON.parse(e.data));
  return ws;
}

export type PositionResponse = {
  time: string;
  mac: string;
  lat: number;
  lon: number;
  accuracy_m: number | null;
  node_count: number;
  method: string;
  label: string | null;
  tag: string;
  vendor: string | null;
  device_type: string;
};

export type NodeResponse = {
  node_id: string;
  node_type: string;
  location: string | null;
  last_seen: string;
  firmware_ver: string;
  lat: number | null;
  lon: number | null;
};

export async function fetchCurrentPositions(tag?: string): Promise<PositionResponse[]> {
  const url = tag ? `${BASE}/positions/current?tag=${tag}` : `${BASE}/positions/current`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`GET /positions/current failed: ${res.status}`);
  return res.json();
}

export async function fetchActivePositions(windowMinutes = 5): Promise<PositionResponse[]> {
  const res = await fetch(`${BASE}/positions/active?window_minutes=${windowMinutes}`);
  if (!res.ok) throw new Error(`GET /positions/active failed: ${res.status}`);
  return res.json();
}

export async function fetchPositionHistory(mac: string, limit = 100): Promise<PositionResponse[]> {
  const res = await fetch(`${BASE}/positions/${encodeURIComponent(mac)}/history?limit=${limit}`);
  if (!res.ok) throw new Error(`GET /positions/${mac}/history failed: ${res.status}`);
  return res.json();
}
