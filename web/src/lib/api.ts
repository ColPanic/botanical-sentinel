import { env } from "$env/dynamic/public";

const BASE = env.PUBLIC_API_URL ?? "http://localhost:8000";

export async function fetchNodes() {
  const res = await fetch(`${BASE}/nodes`);
  if (!res.ok) throw new Error(`GET /nodes failed: ${res.status}`);
  return res.json();
}

export async function fetchDevices(tag?: string) {
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
