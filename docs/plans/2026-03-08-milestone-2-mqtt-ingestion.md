# Milestone 2: MQTT Ingestion Design

**Date:** 2026-03-08
**Status:** Approved

---

## Scope

Add MQTT publishing to the ESP32 scanner firmware and stand up a server-side ingestion
stack (Mosquitto + TimescaleDB + mqtt_bridge). No FastAPI, no web UI — data flows from
node to database only.

---

## Components

### 1. ESP32 Firmware (nodes/esp32-scanner)

- Add `config.h` (gitignored) with WiFi credentials, MQTT broker host/port, and node ID
- Connect to home WiFi AP on boot; stay connected throughout operation
- WiFi scanning runs while connected to AP (ESP32 STA mode supports this natively)
- After each 30s scan cycle: publish WiFi results, BLE results, and a status heartbeat
- Reconnect to WiFi and MQTT broker if connection drops between cycles

### 2. Mosquitto (server/docker-compose.yml)

- `eclipse-mosquitto:2`
- No authentication (LAN-only deployment for v1)
- Persistent message store via Docker volume
- Listens on port 1883

### 3. TimescaleDB (server/docker-compose.yml)

- `timescale/timescaledb-ha:pg17`
- Three tables: `nodes`, `devices`, `scan_events` (hypertable)
- Schema applied via an init SQL script on first start

### 4. mqtt_bridge (server/mqtt_bridge/)

- Python 3.13, single async worker — no HTTP surface
- `aiomqtt` for MQTT, `asyncpg` for Postgres
- Subscribes to `nodes/+/scan/wifi`, `nodes/+/scan/bt`, `nodes/+/status`
- Auto-reconnects to both MQTT and DB on failure

---

## MQTT Topics

| Topic | Payload | QoS | When |
|-------|---------|-----|------|
| `nodes/{node_id}/scan/wifi` | JSON array of `{ssid, bssid, rssi, channel}` | 0 | After each WiFi scan |
| `nodes/{node_id}/scan/bt` | JSON array of `{mac, name, rssi}` | 0 | After each BLE scan |
| `nodes/{node_id}/status` | `{uptime_ms, free_heap, ip, firmware_ver}` | 1 | Boot + each cycle |

`node_id` is a compile-time constant (e.g. `"scanner-01"`), set in `config.h`.

QoS 0 for scan data — dropped publishes are acceptable since the next cycle covers it.
QoS 1 for status so the broker acknowledges receipt.

---

## Database Schema

### `nodes`
| Column | Type | Notes |
|--------|------|-------|
| `node_id` | TEXT PK | e.g. `scanner-01` |
| `node_type` | TEXT | e.g. `esp32_scanner` |
| `location` | TEXT | Human label, nullable |
| `last_seen` | TIMESTAMPTZ | |
| `firmware_ver` | TEXT | |

### `devices`
| Column | Type | Notes |
|--------|------|-------|
| `mac` | TEXT PK | Normalised to uppercase colon-separated |
| `device_type` | TEXT | `wifi` or `ble` |
| `label` | TEXT | User-assigned, nullable |
| `tag` | TEXT | `unknown` by default |
| `first_seen` | TIMESTAMPTZ | |
| `last_seen` | TIMESTAMPTZ | |
| `vendor` | TEXT | OUI lookup — future milestone |

### `scan_events` (hypertable, partition by `time`)
| Column | Type | Notes |
|--------|------|-------|
| `time` | TIMESTAMPTZ NN | Partition key |
| `node_id` | TEXT | |
| `mac` | TEXT | |
| `rssi` | INTEGER | |
| `scan_type` | TEXT | `wifi` or `ble` |
| `ssid` | TEXT | WiFi only, nullable |

Retention: 90-day rolling window via TimescaleDB `drop_chunks` (configured in init SQL).

---

## Data Flow

```
ESP32 scanner
  │
  │  MQTT publish (WiFi/BLE results + status)
  ▼
Mosquitto broker  (port 1883, Docker)
  │
  │  subscribe nodes/+/scan/# and nodes/+/status
  ▼
mqtt_bridge (Python, Docker)
  │
  ├─ upsert → nodes
  ├─ upsert → devices  (first_seen, last_seen, device_type)
  └─ insert → scan_events (one row per device per scan)
  ▼
TimescaleDB (Docker)
```

---

## Configuration

`.env` at repo root (gitignored). `.env.example` checked in.

```
MQTT_HOST=localhost
MQTT_PORT=1883
DB_URL=postgresql://botanical:password@localhost:5432/botanical
```

`nodes/esp32-scanner/config.h` (gitignored):

```cpp
#pragma once
#define WIFI_SSID     "your-ssid"
#define WIFI_PASSWORD "your-password"
#define MQTT_HOST     "192.168.1.x"
#define MQTT_PORT     1883
#define NODE_ID       "scanner-01"
#define FIRMWARE_VER  "0.2.0"
```

---

## Out of Scope

- FastAPI REST endpoints
- SvelteKit web UI
- OUI vendor lookup
- MQTT authentication
- Gate/camera commands
