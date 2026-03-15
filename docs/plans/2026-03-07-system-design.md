# esp_bot — System Design

**Date:** 2026-03-07
**Status:** Approved

---

## Overview

esp_bot is an open-source IoT security and surveillance system for remote properties. It
uses cheap ESP32-based hardware and Raspberry Pi nodes to passively scan for WiFi and
Bluetooth devices, learn the local RF environment, and alert on unknown devices. A home
server aggregates data, hosts a web UI for device tagging, and dispatches async commands
back to nodes.

---

## Hardware Targets

| Node Type | Hardware | Role |
|-----------|----------|------|
| `esp32-scanner` | ESP32-S3-WROOM-1 + ILI9341 TFT | WiFi+BLE passive scan, display results |
| `esp32-lora` | ESP32 + SX1276 LoRa module | Outlier nodes beyond WiFi range |
| `pi-camera` | Raspberry Pi 4-B + camera module | Motion detection, local RTSP stream |
| `pi-lora-gateway` | Raspberry Pi 4-B + LoRa hat | Bridges LoRa network to MQTT on LAN |

**Cameras:** Eufy (primary, local API via `eufy_security`), Arlo (secondary, cloud API),
Pi camera modules (local inference).

**Connectivity:** WiFi covers ~85% of property. LoRa handles outlier nodes beyond WiFi
range. No cloud dependency required for core operation.

**Server:** Lenovo S50 (x86_64, 8 cores, 64 GB RAM) running Docker. Raspberry Pi 4-B
devices available as LoRa gateway nodes.

---

## Repository Structure

```
esp_bot/
├── nodes/
│   ├── esp32-scanner/          # WiFi+BLE scan + TFT display (C++/PlatformIO)
│   ├── esp32-lora/             # LoRa outlier node (future)
│   ├── pi-camera/              # Pi camera + motion detection (Python)
│   └── pi-lora-gateway/        # LoRa → MQTT bridge (Python)
├── server/
│   ├── api/                    # FastAPI REST + WebSocket
│   ├── mqtt_bridge/            # MQTT subscriber → TimescaleDB writer
│   ├── docker-compose.yml
│   └── pyproject.toml
├── web/                        # SvelteKit frontend
├── docs/
│   └── plans/                  # Design docs
├── .github/
│   ├── workflows/
│   │   ├── firmware.yml        # PlatformIO build check (all nodes/esp32-*)
│   │   ├── pi-nodes.yml        # ruff + ty + pytest (all nodes/pi-*)
│   │   ├── server.yml          # ruff + ty + pytest
│   │   └── web.yml             # svelte-check + tsc + vite build
│   ├── ISSUE_TEMPLATE/
│   └── PULL_REQUEST_TEMPLATE.md
├── .env.example
├── CLAUDE.md
├── CONTRIBUTING.md
└── README.md
```

Branch protection on `main`: no direct pushes, all CI checks must pass.

---

## Data Flow

```
ESP32/Pi node                  Server (Lenovo S50)
─────────────────              ──────────────────────────────────
[scan task]  ──MQTT publish──► [Mosquitto broker]
[cmd task]   ◄─MQTT subscribe─     │
                                    ▼
                               [mqtt_bridge service]
                                    │ writes
                                    ▼
                               [TimescaleDB]
                                    │ reads
                                    ▼
                               [FastAPI]  ◄──► [SvelteKit UI]
                                    │ publishes commands
                                    ▼
                               [Mosquitto] ──► nodes/{id}/commands
```

Nodes publish scans and poll for commands on a 30-second cycle. No persistent connection
required — nodes can sleep between cycles.

---

## MQTT Topic Structure

| Direction | Topic | Payload |
|-----------|-------|---------|
| Node → Server | `nodes/{node_id}/scan/wifi` | JSON: SSID, BSSID, RSSI, channel |
| Node → Server | `nodes/{node_id}/scan/bt` | JSON: MAC, name, RSSI, type |
| Node → Server | `nodes/{node_id}/status` | JSON: uptime, free heap, IP, firmware version, wifi_rssi, node_lat, node_lon |
| Node → Server | `nodes/{node_id}/events` | JSON: PIR trigger, gate state, etc. |
| Server → Node | `nodes/{node_id}/commands` | JSON: command type + payload |

---

## Database Schema (TimescaleDB / PostgreSQL)

### `nodes`
| Column | Type | Notes |
|--------|------|-------|
| `node_id` | TEXT PK | e.g. `scanner-01`, `pi-cam-gate` |
| `node_type` | TEXT | `esp32_scanner`, `pi_camera`, `pi_lora_gateway` |
| `location` | TEXT | Human label: `front gate`, `barn` |
| `last_seen` | TIMESTAMPTZ | |
| `firmware_ver` | TEXT | |
| `lat` | DOUBLE PRECISION | |
| `lon` | DOUBLE PRECISION | |
| `location_confirmed` | BOOLEAN | One-way latch, set via map placement |

### `devices`
| Column | Type | Notes |
|--------|------|-------|
| `mac` | TEXT PK | |
| `device_type` | TEXT | `wifi`, `ble`, `bt_classic` |
| `label` | TEXT | User-assigned: `John's Tesla` |
| `tag` | TEXT | `known_resident`, `known_vehicle`, `unknown`, `ignored` |
| `first_seen` | TIMESTAMPTZ | |
| `last_seen` | TIMESTAMPTZ | |
| `vendor` | TEXT | OUI lookup result |

### `scan_events` (hypertable, partitioned by time)
| Column | Type | Notes |
|--------|------|-------|
| `time` | TIMESTAMPTZ NN | Partition key |
| `node_id` | TEXT | |
| `mac` | TEXT | |
| `rssi` | INTEGER | |
| `scan_type` | TEXT | `wifi`, `ble`, `bt_classic` |
| `ssid` | TEXT | WiFi only, nullable |

Retention: 90-day rolling window via TimescaleDB `drop_chunks`.

### `commands`
| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `node_id` | TEXT | |
| `command_type` | TEXT | `trigger_camera`, `open_gate`, `reboot` |
| `payload` | JSONB | |
| `created_at` | TIMESTAMPTZ | |
| `executed_at` | TIMESTAMPTZ | NULL until node acknowledges |

---

## Server Stack

| Service | Image | Purpose |
|---------|-------|---------|
| `mosquitto` | `eclipse-mosquitto` | MQTT broker |
| `timescaledb` | `timescale/timescaledb-ha` | PostgreSQL + time-series extension |
| `mqtt_bridge` | custom Python | MQTT subscriber → DB writer |
| `api` | custom Python | FastAPI REST + WebSocket |
| `web` | custom Node | SvelteKit frontend |

`mqtt_bridge` is a separate service from `api` — it runs a blocking MQTT loop with no
HTTP surface. API remains stateless and independently restartable.

### FastAPI Endpoints

```
GET  /nodes                      list all nodes + status
GET  /devices                    list observed devices (filterable by tag)
PUT  /devices/{mac}/label        set human label
PUT  /devices/{mac}/tag          set tag
PATCH /nodes/{node_id}            update node name, location, confirmation
GET  /scan/recent                last N scan events (all nodes)
GET  /scan/{node_id}/recent      last N events for a node
POST /commands/{node_id}         queue a command
GET  /commands/{node_id}/pending node polls for pending commands
WS   /live                       WebSocket: real-time scan events
```

### Configuration

Single `.env` file at repo root (gitignored). `.env.example` checked in.

```
MQTT_HOST=mosquitto
MQTT_PORT=1883
DB_URL=postgresql://esp_bot:password@timescaledb:5432/esp_bot
SECRET_KEY=changeme
```

---

## Web UI (SvelteKit + Tailwind CSS)

| Route | Purpose |
|-------|---------|
| `/nodes` | Node status: location, type, last seen, firmware, staleness indicator |
| `/devices` | Device registry: MAC, vendor, label, tag, first/last seen. Inline editing. Unknown devices float to top. |
| `/scan` | Live scan view per node via WebSocket |
| `/map` | Leaflet map with node and device markers, click-to-place, inline editing, bulk selection |
| `/commands` | Send commands to nodes, view execution status |

Server-side `+page.server.ts` routes fetch from FastAPI on load. No auth for v1 (private
LAN). Basic auth is a future milestone.

---

## Scanning Approach

**Passive only.** Nodes listen for:
- WiFi probe requests, beacon frames (SSID, BSSID, RSSI, channel)
- BLE advertisements (MAC, advertised name if present, RSSI)

No active probing, directed probe requests, or deauthentication frames. This is legal in
all target jurisdictions and appropriate for a public codebase.

Classic Bluetooth inquiry deferred — it blocks for several seconds and is incompatible
with a 30-second scan cycle.

---

## Milestone 1: ESP32 Scanner Prototype

**Goal:** Validate scanning hardware and TFT display layout before any server
infrastructure is built.

**Scope:**
- WiFi passive scan: SSID, BSSID, RSSI, channel
- BLE passive scan: MAC, advertised name, RSSI
- TFT display: paginated scan results
- 30-second repeat cycle
- Serial output mirrors TFT for debugging
- No MQTT, no server, no vendor lookup

**TFT Layout:**
```
┌────────────────────────────────┐
│ WiFi (12)          BT/BLE (4)  │
├────────────────────────────────┤
│ MyNetwork        -45 dBm  ch6  │
│ Neighbor_2G      -72 dBm  ch1  │
│ NETGEAR_5G       -68 dBm  ch11 │
│ [hidden]         -81 dBm  ch6  │
│ ···                            │
├────────────────────────────────┤
│ BLE: iPhone       -61 dBm      │
│ BLE: 7A:3F:..     -74 dBm      │
├────────────────────────────────┤
│ Scan #4   Last: 28s ago        │
└────────────────────────────────┘
```

**Deliverable:** `nodes/esp32-scanner/` compiles cleanly, runs on hardware, displays live
scan results.

---

## Future Milestones (not in scope for v1)

- MQTT publish from ESP32 scanner
- Server Docker Compose stack (Mosquitto + TimescaleDB + FastAPI)
- SvelteKit device registry UI
- Pi camera node with motion detection
- LoRa gateway node
- Gate control integration
- PIR sensor → scan trigger → camera trigger pipeline
- Classic Bluetooth inquiry
- Basic auth for web UI
- OUI vendor lookup
- Eufy camera integration (local API)
- Arlo camera integration (cloud API)
