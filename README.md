# botanical-sentinel

Open-source IoT security and surveillance system for remote properties.

ESP32 nodes passively scan for WiFi and Bluetooth devices, learn the local RF
environment, and alert on unknown devices. A home server aggregates data and serves a
web UI for device tagging and management.

## Hardware (Basically all the various old boards I have laying around the house. Adding more as I build. Please add more!

| Node | Board | Role | Status |
|------|-------|------|--------|
| `esp32-scanner` | ESP32-S3-WROOM-1 + ILI9341 TFT 240×320 | WiFi+BLE passive scan | Working |
| `ttgo-lora32` | TTGO T-Beam V1.1 + SSD1306 OLED 128×64 + GPS | WiFi+BLE passive scan | Working |
| `pi-camera` | Raspberry Pi 4-B + camera module | Motion detection, RTSP | Planned |
| `pi-lora-gateway` | Raspberry Pi 4-B + LoRa hat | LoRa → MQTT bridge | Planned |
| Server | x86_64 Linux | MQTT, database, API, web UI | Working |

## Repository Structure

```
nodes/
  esp32-scanner/   ESP32-S3 + ILI9341 TFT scanner node
  ttgo-lora32/     TTGO T-Beam V1.1 + SSD1306 OLED + GPS scanner node
server/
  docker-compose.yml   Mosquitto, TimescaleDB, MQTT bridge, FastAPI
  mqtt_bridge/         Python subscriber — MQTT → TimescaleDB
  api/                 FastAPI REST + WebSocket endpoints
  sql/init.sql         Schema (applied automatically on first start)
web/                 SvelteKit dashboard (nodes, devices, map, live scan feed)
docs/plans/          Architecture and design documents
```

## Prerequisites

| Tool | Purpose | Install |
|------|---------|---------|
| [PlatformIO](https://platformio.org/install/cli) | Firmware build + flash | `pip install platformio` |
| [Docker](https://docs.docker.com/get-docker/) | Server stack | platform installer |
| [Node.js 22](https://nodejs.org/) | Web dashboard | platform installer |
| [uv](https://docs.astral.sh/uv/) | Python (server dev) | `pip install uv` |

PlatformIO installs itself into `~/.platformio/` on first build. The Makefile expects it at
`~/.platformio/penv/bin/pio` — override with `PIO=` if yours is elsewhere.

## Quick Start

### 1. Server

```bash
cd server
cp .env.example .env          # fill in DB_PASSWORD
make up                       # starts Mosquitto, TimescaleDB, MQTT bridge, FastAPI
```

Services: Mosquitto on :1883, FastAPI on :8000, TimescaleDB on :5432.
Schema is applied automatically from `sql/init.sql` on first TimescaleDB start.

### 2. Firmware — ESP32-S3 scanner

```bash
# Create config — fill in WiFi credentials and MQTT server IP
cp nodes/esp32-scanner/src/config.h.example nodes/esp32-scanner/src/config.h
$EDITOR nodes/esp32-scanner/src/config.h

# Build
make firmware-scanner

# Flash (TFT display variant)
# Enter bootloader first: hold BOOT, press+release RESET, release BOOT
make flash-tft PORT=/dev/cu.usbmodem2101

# Monitor serial output
make monitor
```

See [nodes/esp32-scanner/README.md](nodes/esp32-scanner/README.md) for wiring details and
the TFT display layout.

### 3. Firmware — TTGO T-Beam scanner

```bash
# Create config — same shape as esp32-scanner
cp nodes/ttgo-lora32/src/config.h.example nodes/ttgo-lora32/src/config.h
$EDITOR nodes/ttgo-lora32/src/config.h

# Build
make firmware-lora

# Flash (OLED variant) — CP2102 auto-resets, no manual bootloader step needed
make flash-lora-oled LORA_PORT=/dev/cu.SLAB_USBtoUART

# Monitor serial output
make monitor-lora
```

### 4. Web dashboard

```bash
make web-install    # npm install (first time)
make web            # starts Vite dev server on :5173
```

## Firmware Make Targets

```
make firmware              Build all nodes (esp32-scanner + ttgo-lora32)
make firmware-scanner      Build esp32-scanner only
make firmware-lora         Build ttgo-lora32 only

make flash                 Flash esp32-scanner headless  [PORT=]
make flash-tft             Flash esp32-scanner TFT       [PORT=]
make flash-lora            Flash ttgo-lora32 headless    [LORA_PORT=]
make flash-lora-oled       Flash ttgo-lora32 OLED        [LORA_PORT=]

make monitor               Serial monitor for esp32-scanner
make monitor-lora          Serial monitor for ttgo-lora32
```

The ESP32-S3 board uses native USB with no UART chip. Manual bootloader entry is required
before every flash: hold **BOOT**, press+release **RESET**, release **BOOT**.

The TTGO T-Beam has a CP2102 UART chip. Flashing auto-resets the board — no manual step.

## config.h

Both nodes read credentials from a gitignored `src/config.h`. Copy from the example and
fill in your values:

```cpp
#define WIFI_SSID      "your-network"
#define WIFI_PASSWORD  "your-password"
#define MQTT_HOST      "192.168.1.x"   // IP of the machine running docker compose
#define MQTT_PORT      1883
#define NODE_ID        "esp32-scanner-01"  // unique per device
#define FIRMWARE_VER   "0.1.0"
```

## MQTT Topics

Each node publishes to three topics (NODE_ID comes from `config.h`):

| Topic | Payload | Interval |
|-------|---------|----------|
| `nodes/<NODE_ID>/scan/wifi` | JSON array of WiFi networks (SSID, BSSID, RSSI, channel) | Every 30s |
| `nodes/<NODE_ID>/scan/bt` | JSON array of BLE devices (MAC, name, RSSI) | Every 30s |
| `nodes/<NODE_ID>/status` | JSON object (uptime_ms, free_heap, IP, firmware_ver, wifi_rssi, node_lat, node_lon) | Every 30s |

The MQTT bridge subscribes to `nodes/+/scan/+` and `nodes/+/status` and writes all
messages to TimescaleDB. The API exposes them over REST and WebSocket.

## Scanning Approach

This project uses **passive RF scanning only** — listening for WiFi beacon frames, probe
requests, and BLE advertisements. No active probing, no deauthentication frames.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT
