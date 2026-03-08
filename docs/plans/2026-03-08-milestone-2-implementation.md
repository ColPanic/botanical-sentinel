# Milestone 2: MQTT Ingestion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add MQTT publishing to the ESP32 scanner and stand up a server-side ingestion
stack (Mosquitto + TimescaleDB + mqtt_bridge Python service).

**Architecture:** ESP32 connects to home WiFi AP on boot, stays connected, and publishes
scan results after each 30s cycle. Server runs Docker Compose with Mosquitto, TimescaleDB,
and an async Python bridge that subscribes to MQTT and writes to the DB.

**Tech Stack:** Arduino/PlatformIO, PubSubClient, ArduinoJson v7, Python 3.13, aiomqtt,
asyncpg, TimescaleDB (PostgreSQL), Docker Compose, Mosquitto.

**Note on TDD:** Firmware has no unit test runner. Discipline is: write → compile (`pio
run`) → flash + serial verify → commit. Python code follows full pytest TDD.

---

### Task 1: config.h template + gitignore

**Files:**
- Create: `nodes/esp32-scanner/config.h.example`
- Modify: `.gitignore`

**Step 1: Create config.h.example**

```cpp
#pragma once

// Copy to config.h and fill in your values. config.h is gitignored.

#define WIFI_SSID      "your-network-name"
#define WIFI_PASSWORD  "your-password"

#define MQTT_HOST      "192.168.1.x"   // IP of your server running Mosquitto
#define MQTT_PORT      1883

#define NODE_ID        "scanner-01"    // unique per device
#define FIRMWARE_VER   "0.2.0"
```

**Step 2: Create your local config.h**

```bash
cp nodes/esp32-scanner/config.h.example nodes/esp32-scanner/config.h
# Edit config.h with your real WiFi credentials and MQTT broker IP
```

**Step 3: Add config.h to .gitignore**

Add this line to `.gitignore` under the `# PlatformIO` section:

```
nodes/**/config.h
```

**Step 4: Verify gitignore works**

```bash
git status
```

Expected: `nodes/esp32-scanner/config.h` does NOT appear as untracked.

**Step 5: Commit**

```bash
git add nodes/esp32-scanner/config.h.example .gitignore
git commit -m "chore(esp32-scanner): add config.h template for WiFi and MQTT credentials"
```

---

### Task 2: Add PubSubClient and ArduinoJson to platformio.ini

**Files:**
- Modify: `nodes/esp32-scanner/platformio.ini`

**Step 1: Look up current stable versions**

Check https://registry.platformio.org for:
- `knolleary/PubSubClient` (expect ~2.8.0)
- `bblanchon/ArduinoJson` (expect ~7.x)

**Step 2: Add lib_deps and build flag**

In `platformio.ini`, update `lib_deps` and add `MQTT_MAX_PACKET_SIZE`:

```ini
lib_deps =
    bodmer/TFT_eSPI @ ^2.5.43
    knolleary/PubSubClient @ ^2.8
    bblanchon/ArduinoJson @ ^7.0
```

And add to `build_flags` (after the existing `USE_FSPI_PORT` line):

```ini
    ; MQTT packet buffer — default 256 is too small for 20-entry JSON payloads
    -D MQTT_MAX_PACKET_SIZE=4096
```

**Step 3: Compile check**

```bash
~/.platformio/penv/bin/pio run --project-dir nodes/esp32-scanner
```

Expected: `[SUCCESS]` — libraries download and compile.

**Step 4: Commit**

```bash
git add nodes/esp32-scanner/platformio.ini
git commit -m "chore(esp32-scanner): add PubSubClient and ArduinoJson dependencies"
```

---

### Task 3: Add WiFi connect, MQTT connect, and publish to firmware

**Files:**
- Modify: `nodes/esp32-scanner/src/main.cpp`

This task rewrites the top of `main.cpp` (includes, globals, new functions) and updates
`setup()` and `loop()`. The scan and display logic is unchanged.

**Step 1: Update includes at the top of main.cpp**

Replace the existing includes block:

```cpp
#include <Arduino.h>
#include <ArduinoJson.h>
#include <BLEAdvertisedDevice.h>
#include <BLEDevice.h>
#include <BLEScan.h>
#include <PubSubClient.h>
#include <TFT_eSPI.h>
#include <WiFi.h>
#include <WiFiClient.h>

#include "config.h"
```

**Step 2: Add MQTT globals after the existing state block**

After `static uint8_t bleCount = 0;`, add:

```cpp
// ── MQTT ──────────────────────────────────────────────────────────────────────

static WiFiClient   wifiClient;
static PubSubClient mqtt(wifiClient);

// Topic strings built from NODE_ID at setup time
static char topicWifi[64];
static char topicBle[64];
static char topicStatus[64];

// Shared serialisation buffer — 4096 bytes, lives in global RAM
static char mqttBuf[4096];
```

**Step 3: Add connectWifi() before scanWifi()**

```cpp
// ── Connectivity ──────────────────────────────────────────────────────────────

static void connectWifi() {
    if (WiFi.status() == WL_CONNECTED) return;

    Serial.printf("[WiFi] Connecting to %s", WIFI_SSID);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    for (uint8_t attempts = 0;
         WiFi.status() != WL_CONNECTED && attempts < 20;
         attempts++) {
        delay(500);
        Serial.print(".");
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("\n[WiFi] Connected. IP: %s\n",
            WiFi.localIP().toString().c_str());
    } else {
        Serial.println("\n[WiFi] Failed — will retry next cycle");
    }
}

static void connectMqtt() {
    if (mqtt.connected()) return;

    Serial.printf("[MQTT] Connecting to %s:%d as %s\n",
        MQTT_HOST, MQTT_PORT, NODE_ID);

    if (mqtt.connect(NODE_ID)) {
        Serial.println("[MQTT] Connected");
    } else {
        Serial.printf("[MQTT] Failed, state=%d\n", mqtt.state());
    }
}
```

**Step 4: Add publish functions before renderDisplay()**

```cpp
// ── MQTT publish ──────────────────────────────────────────────────────────────

static void publishWifi() {
    JsonDocument doc;
    JsonArray arr = doc.to<JsonArray>();

    for (uint8_t i = 0; i < wifiCount; i++) {
        JsonObject obj = arr.add<JsonObject>();
        obj["ssid"] = wifiResults[i].ssid;

        char bssid[18];
        snprintf(bssid, sizeof(bssid),
            "%02X:%02X:%02X:%02X:%02X:%02X",
            wifiResults[i].bssid[0], wifiResults[i].bssid[1],
            wifiResults[i].bssid[2], wifiResults[i].bssid[3],
            wifiResults[i].bssid[4], wifiResults[i].bssid[5]);
        obj["bssid"]   = bssid;
        obj["rssi"]    = wifiResults[i].rssi;
        obj["channel"] = wifiResults[i].channel;
    }

    serializeJson(doc, mqttBuf, sizeof(mqttBuf));
    mqtt.publish(topicWifi, mqttBuf);
    Serial.printf("[MQTT] → %s (%u entries)\n", topicWifi, wifiCount);
}

static void publishBle() {
    JsonDocument doc;
    JsonArray arr = doc.to<JsonArray>();

    for (uint8_t i = 0; i < bleCount; i++) {
        JsonObject obj = arr.add<JsonObject>();
        obj["mac"]  = bleResults[i].mac;
        obj["name"] = bleResults[i].name;
        obj["rssi"] = bleResults[i].rssi;
    }

    serializeJson(doc, mqttBuf, sizeof(mqttBuf));
    mqtt.publish(topicBle, mqttBuf);
    Serial.printf("[MQTT] → %s (%u entries)\n", topicBle, bleCount);
}

static void publishStatus() {
    JsonDocument doc;
    doc["uptime_ms"]    = millis();
    doc["free_heap"]    = ESP.getFreeHeap();
    doc["ip"]           = WiFi.localIP().toString();
    doc["firmware_ver"] = FIRMWARE_VER;

    serializeJson(doc, mqttBuf, sizeof(mqttBuf));
    mqtt.publish(topicStatus, mqttBuf);
    Serial.printf("[MQTT] → %s\n", topicStatus);
}
```

**Step 5: Replace setup()**

```cpp
void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("=== botanical-sentinel scanner node ===");

    tft.init();
    tft.setRotation(1);
    tft.fillScreen(TFT_BLACK);

    // Build topic strings once
    snprintf(topicWifi,   sizeof(topicWifi),   "nodes/%s/scan/wifi", NODE_ID);
    snprintf(topicBle,    sizeof(topicBle),    "nodes/%s/scan/bt",   NODE_ID);
    snprintf(topicStatus, sizeof(topicStatus), "nodes/%s/status",    NODE_ID);

    WiFi.mode(WIFI_STA);
    connectWifi();

    mqtt.setServer(MQTT_HOST, MQTT_PORT);
    connectMqtt();

    if (mqtt.connected()) {
        publishStatus();
    }

    BLEDevice::init("");
}
```

**Step 6: Replace loop()**

```cpp
void loop() {
    // Maintain connections between scan cycles
    if (WiFi.status() != WL_CONNECTED) {
        connectWifi();
    } else {
        if (!mqtt.connected()) {
            connectMqtt();
        }
        mqtt.loop();
    }

    static uint32_t lastScan = static_cast<uint32_t>(0) - SCAN_INTERVAL_MS;

    if (millis() - lastScan >= SCAN_INTERVAL_MS) {
        tft.fillScreen(TFT_BLACK);
        tft.setTextDatum(MC_DATUM);
        tft.setTextColor(TFT_WHITE, TFT_BLACK);
        tft.drawString("Scanning...", 160, 120, 4);

        lastScan = millis();
        scanCount++;
        Serial.printf("\n--- Scan #%lu ---\n", scanCount);

        scanWifi();
        scanBle();
        renderDisplay(lastScan);

        if (mqtt.connected()) {
            publishWifi();
            publishBle();
            publishStatus();
        } else {
            Serial.println("[MQTT] Not connected — skipping publish");
        }
    }
}
```

**Step 7: Compile check**

```bash
~/.platformio/penv/bin/pio run --project-dir nodes/esp32-scanner
```

Expected: `[SUCCESS]`

**Step 8: Flash and verify serial output**

Enter bootloader: hold BOOT, press+release RESET, release BOOT.
Port re-enumerates as `/dev/cu.usbmodem2101`.

```bash
~/.platformio/penv/bin/pio run --project-dir nodes/esp32-scanner \
    -t upload --upload-port /dev/cu.usbmodem2101
~/.platformio/penv/bin/pio device monitor --project-dir nodes/esp32-scanner
```

Expected serial:
```
=== botanical-sentinel scanner node ===
[WiFi] Connecting to MyNetwork......
[WiFi] Connected. IP: 192.168.1.42
[MQTT] Connecting to 192.168.1.x:1883 as scanner-01
[MQTT] Connected
[MQTT] → nodes/scanner-01/status

--- Scan #1 ---
[WiFi] 8 networks
  ...
[BLE] 3 devices
  ...
[MQTT] → nodes/scanner-01/scan/wifi (8 entries)
[MQTT] → nodes/scanner-01/scan/bt (3 entries)
[MQTT] → nodes/scanner-01/status
```

(MQTT publishes will fail until the broker is running — that's expected. The node logs
"Not connected — skipping publish" and continues scanning.)

**Step 9: Commit**

```bash
git add nodes/esp32-scanner/src/main.cpp
git commit -m "feat(esp32-scanner): add WiFi connection and MQTT publish"
```

---

### Task 4: Scaffold server/ directory and mosquitto config

**Files:**
- Create: `server/mosquitto/mosquitto.conf`
- Create: `server/sql/init.sql`
- Create: `server/.env.example`

**Step 1: Create directory structure**

```bash
mkdir -p server/mosquitto server/sql server/mqtt_bridge/src/mqtt_bridge server/mqtt_bridge/tests
```

**Step 2: Write mosquitto.conf**

`server/mosquitto/mosquitto.conf`:
```
listener 1883
allow_anonymous true
persistence true
persistence_location /mosquitto/data/
log_dest stdout
log_type all
```

**Step 3: Write init.sql**

`server/sql/init.sql`:
```sql
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS nodes (
    node_id      TEXT PRIMARY KEY,
    node_type    TEXT        NOT NULL,
    location     TEXT,
    last_seen    TIMESTAMPTZ NOT NULL DEFAULT now(),
    firmware_ver TEXT        NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS devices (
    mac         TEXT PRIMARY KEY,
    device_type TEXT        NOT NULL,
    label       TEXT,
    tag         TEXT        NOT NULL DEFAULT 'unknown',
    first_seen  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen   TIMESTAMPTZ NOT NULL DEFAULT now(),
    vendor      TEXT
);

CREATE TABLE IF NOT EXISTS scan_events (
    time      TIMESTAMPTZ NOT NULL,
    node_id   TEXT        NOT NULL,
    mac       TEXT        NOT NULL,
    rssi      INTEGER     NOT NULL,
    scan_type TEXT        NOT NULL,
    ssid      TEXT
);

SELECT create_hypertable('scan_events', by_range('time'), if_not_exists => TRUE);

SELECT add_retention_policy(
    'scan_events',
    INTERVAL '90 days',
    if_not_exists => TRUE
);
```

**Step 4: Write .env.example**

`server/.env.example`:
```
# Copy to .env and fill in values. .env is gitignored.

# Database
DB_PASSWORD=changeme
DB_URL=postgresql://botanical:changeme@localhost:5432/botanical

# MQTT (use localhost when running services outside Docker)
MQTT_HOST=localhost
MQTT_PORT=1883
```

**Step 5: Commit**

```bash
git add server/
git commit -m "chore(server): scaffold mosquitto config, DB init SQL, and .env.example"
```

---

### Task 5: Implement mqtt_bridge — handler.py with unit tests

**Files:**
- Create: `server/mqtt_bridge/src/mqtt_bridge/__init__.py`
- Create: `server/mqtt_bridge/src/mqtt_bridge/handler.py`
- Create: `server/mqtt_bridge/tests/__init__.py`
- Create: `server/mqtt_bridge/tests/test_handler.py`
- Create: `server/mqtt_bridge/pyproject.toml`

**Step 1: Write pyproject.toml**

Look up current stable versions of `aiomqtt`, `asyncpg`, `pytest`, `ruff` before pinning.

`server/mqtt_bridge/pyproject.toml`:
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatchling.build.targets.wheel]
packages = ["src/mqtt_bridge"]

[project]
name = "mqtt-bridge"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "aiomqtt==<CURRENT_STABLE>",
    "asyncpg==<CURRENT_STABLE>",
]

[project.optional-dependencies]
dev = [
    "pytest==<CURRENT_STABLE>",
    "ruff==<CURRENT_STABLE>",
]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
src = ["src"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP"]
```

**Step 2: Create empty __init__ files**

```bash
touch server/mqtt_bridge/src/mqtt_bridge/__init__.py
touch server/mqtt_bridge/tests/__init__.py
```

**Step 3: Write the failing tests first**

`server/mqtt_bridge/tests/test_handler.py`:
```python
import json
from mqtt_bridge.handler import extract_node_id, parse_ble, parse_wifi


def test_extract_node_id_scan_topic():
    assert extract_node_id("nodes/scanner-01/scan/wifi") == "scanner-01"


def test_extract_node_id_status_topic():
    assert extract_node_id("nodes/pi-cam-gate/status") == "pi-cam-gate"


def test_parse_wifi_basic():
    payload = json.dumps([
        {"ssid": "MyNet", "bssid": "aa:bb:cc:dd:ee:ff", "rssi": -45, "channel": 6}
    ]).encode()
    events = parse_wifi("scanner-01", payload)
    assert len(events) == 1
    assert events[0].mac == "AA:BB:CC:DD:EE:FF"
    assert events[0].rssi == -45
    assert events[0].ssid == "MyNet"
    assert events[0].scan_type == "wifi"
    assert events[0].node_id == "scanner-01"


def test_parse_wifi_empty_ssid_becomes_none():
    payload = json.dumps([
        {"ssid": "", "bssid": "aa:bb:cc:dd:ee:ff", "rssi": -80, "channel": 1}
    ]).encode()
    events = parse_wifi("scanner-01", payload)
    assert events[0].ssid is None


def test_parse_wifi_skips_empty_bssid():
    payload = json.dumps([
        {"ssid": "x", "bssid": "", "rssi": -50, "channel": 6}
    ]).encode()
    assert parse_wifi("scanner-01", payload) == []


def test_parse_wifi_empty_list():
    assert parse_wifi("scanner-01", b"[]") == []


def test_parse_ble_basic():
    payload = json.dumps([
        {"mac": "7a:3f:cc:dd:ee:ff", "name": "iPhone", "rssi": -61}
    ]).encode()
    events = parse_ble("scanner-01", payload)
    assert len(events) == 1
    assert events[0].mac == "7A:3F:CC:DD:EE:FF"
    assert events[0].rssi == -61
    assert events[0].scan_type == "ble"
    assert events[0].ssid is None


def test_parse_ble_skips_empty_mac():
    payload = json.dumps([
        {"mac": "", "name": "x", "rssi": -50}
    ]).encode()
    assert parse_ble("scanner-01", payload) == []


def test_parse_ble_empty_list():
    assert parse_ble("scanner-01", b"[]") == []
```

**Step 4: Set up venv and run tests to confirm they fail**

```bash
cd server/mqtt_bridge
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
pytest -v
```

Expected: `ImportError: No module named 'mqtt_bridge.handler'`

**Step 5: Implement handler.py**

`server/mqtt_bridge/src/mqtt_bridge/handler.py`:
```python
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class ScanEvent:
    node_id: str
    mac: str
    rssi: int
    scan_type: str
    ssid: str | None
    time: datetime


def extract_node_id(topic: str) -> str:
    """Extract node ID from topic string 'nodes/{node_id}/...'."""
    parts = topic.split("/")
    return parts[1] if len(parts) >= 2 else "unknown"


def parse_wifi(node_id: str, payload: bytes) -> list[ScanEvent]:
    """Parse a nodes/{id}/scan/wifi MQTT payload into ScanEvents."""
    items: list[dict] = json.loads(payload)
    now = datetime.now(timezone.utc)
    events = []
    for item in items:
        bssid = item.get("bssid", "").strip().upper()
        if not bssid:
            continue
        ssid = item.get("ssid") or None
        events.append(ScanEvent(
            node_id=node_id,
            mac=bssid,
            rssi=int(item["rssi"]),
            scan_type="wifi",
            ssid=ssid,
            time=now,
        ))
    return events


def parse_ble(node_id: str, payload: bytes) -> list[ScanEvent]:
    """Parse a nodes/{id}/scan/bt MQTT payload into ScanEvents."""
    items: list[dict] = json.loads(payload)
    now = datetime.now(timezone.utc)
    events = []
    for item in items:
        mac = item.get("mac", "").strip().upper()
        if not mac:
            continue
        events.append(ScanEvent(
            node_id=node_id,
            mac=mac,
            rssi=int(item["rssi"]),
            scan_type="ble",
            ssid=None,
            time=now,
        ))
    return events
```

**Step 6: Run tests — all must pass**

```bash
pytest -v
```

Expected: 9 tests PASSED

**Step 7: Run linter**

```bash
ruff check src/ tests/
```

Expected: no output (clean).

**Step 8: Commit**

```bash
cd ../..   # back to repo root
git add server/mqtt_bridge/
git commit -m "feat(mqtt-bridge): implement message parsing with tests"
```

---

### Task 6: Implement mqtt_bridge — db.py, config.py, main.py

**Files:**
- Create: `server/mqtt_bridge/src/mqtt_bridge/config.py`
- Create: `server/mqtt_bridge/src/mqtt_bridge/db.py`
- Create: `server/mqtt_bridge/src/mqtt_bridge/main.py`
- Create: `server/mqtt_bridge/src/mqtt_bridge/__main__.py`

**Step 1: Write config.py**

`server/mqtt_bridge/src/mqtt_bridge/config.py`:
```python
import os


def _require(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise RuntimeError(f"Required environment variable {key!r} is not set")
    return val


MQTT_HOST: str = _require("MQTT_HOST")
MQTT_PORT: int = int(os.environ.get("MQTT_PORT", "1883"))
DB_URL: str = _require("DB_URL")
```

**Step 2: Write db.py**

`server/mqtt_bridge/src/mqtt_bridge/db.py`:
```python
from __future__ import annotations

import asyncpg

from mqtt_bridge.handler import ScanEvent


async def upsert_node(
    pool: asyncpg.Pool,
    node_id: str,
    firmware_ver: str,
    ip: str,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO nodes (node_id, node_type, last_seen, firmware_ver)
            VALUES ($1, 'esp32_scanner', now(), $2)
            ON CONFLICT (node_id) DO UPDATE
                SET last_seen    = now(),
                    firmware_ver = EXCLUDED.firmware_ver
            """,
            node_id,
            firmware_ver,
        )


async def upsert_devices(pool: asyncpg.Pool, events: list[ScanEvent]) -> None:
    async with pool.acquire() as conn:
        for event in events:
            await conn.execute(
                """
                INSERT INTO devices (mac, device_type, first_seen, last_seen, tag)
                VALUES ($1, $2, now(), now(), 'unknown')
                ON CONFLICT (mac) DO UPDATE
                    SET last_seen = now()
                """,
                event.mac,
                event.scan_type,
            )


async def insert_scan_events(pool: asyncpg.Pool, events: list[ScanEvent]) -> None:
    if not events:
        return
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO scan_events (time, node_id, mac, rssi, scan_type, ssid)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            [
                (e.time, e.node_id, e.mac, e.rssi, e.scan_type, e.ssid)
                for e in events
            ],
        )
```

**Step 3: Write main.py**

`server/mqtt_bridge/src/mqtt_bridge/main.py`:
```python
from __future__ import annotations

import asyncio
import json
import logging

import aiomqtt
import asyncpg

from mqtt_bridge.config import DB_URL, MQTT_HOST, MQTT_PORT
from mqtt_bridge.db import insert_scan_events, upsert_devices, upsert_node
from mqtt_bridge.handler import extract_node_id, parse_ble, parse_wifi

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger(__name__)


async def handle_scan(pool: asyncpg.Pool, topic: str, payload: bytes) -> None:
    node_id = extract_node_id(topic)

    if "/scan/wifi" in topic:
        events = parse_wifi(node_id, payload)
    elif "/scan/bt" in topic:
        events = parse_ble(node_id, payload)
    else:
        return

    if not events:
        return

    await upsert_devices(pool, events)
    await insert_scan_events(pool, events)
    log.info("node=%s topic=%s count=%d", node_id, topic.split("/")[-1], len(events))


async def handle_status(pool: asyncpg.Pool, topic: str, payload: bytes) -> None:
    node_id = extract_node_id(topic)
    data: dict = json.loads(payload)
    await upsert_node(
        pool,
        node_id,
        firmware_ver=data.get("firmware_ver", ""),
        ip=data.get("ip", ""),
    )
    log.info("node=%s status uptime_ms=%s", node_id, data.get("uptime_ms"))


async def run(pool: asyncpg.Pool) -> None:
    while True:
        try:
            async with aiomqtt.Client(MQTT_HOST, MQTT_PORT) as client:
                log.info("Connected to MQTT broker %s:%d", MQTT_HOST, MQTT_PORT)
                await client.subscribe("nodes/+/scan/#")
                await client.subscribe("nodes/+/status")

                async for message in client.messages:
                    topic = str(message.topic)
                    try:
                        if "/scan/" in topic:
                            await handle_scan(pool, topic, message.payload)
                        elif "/status" in topic:
                            await handle_status(pool, topic, message.payload)
                    except Exception:
                        log.exception("Error handling topic=%s", topic)

        except aiomqtt.MqttError as exc:
            log.warning("MQTT connection lost: %s — reconnecting in 5s", exc)
            await asyncio.sleep(5)


async def main() -> None:
    log.info("Connecting to database")
    pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=5)
    log.info("Database connected")
    await run(pool)
```

**Step 4: Write __main__.py**

`server/mqtt_bridge/src/mqtt_bridge/__main__.py`:
```python
import asyncio
from mqtt_bridge.main import main

asyncio.run(main())
```

**Step 5: Run linter**

```bash
cd server/mqtt_bridge
ruff check src/
```

Expected: clean.

**Step 6: Commit**

```bash
cd ../..
git add server/mqtt_bridge/src/
git commit -m "feat(mqtt-bridge): implement db writer and async main loop"
```

---

### Task 7: Docker Compose + Dockerfile

**Files:**
- Create: `server/mqtt_bridge/Dockerfile`
- Create: `server/docker-compose.yml`

**Step 1: Write Dockerfile**

`server/mqtt_bridge/Dockerfile`:
```dockerfile
FROM python:3.13-slim
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml .
RUN uv pip install --system --no-cache .
COPY src/ src/
CMD ["python", "-m", "mqtt_bridge"]
```

**Step 2: Write docker-compose.yml**

`server/docker-compose.yml`:
```yaml
services:
  mosquitto:
    image: eclipse-mosquitto:2
    ports:
      - "1883:1883"
    volumes:
      - ./mosquitto/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro
      - mosquitto_data:/mosquitto/data
    restart: unless-stopped

  timescaledb:
    image: timescale/timescaledb-ha:pg17
    environment:
      POSTGRES_USER: botanical
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: botanical
    volumes:
      - timescaledb_data:/home/postgres/pgdata/data
      - ./sql/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    ports:
      - "5432:5432"
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U botanical"]
      interval: 10s
      timeout: 5s
      retries: 5

  mqtt_bridge:
    build: ./mqtt_bridge
    environment:
      MQTT_HOST: mosquitto
      MQTT_PORT: 1883
      DB_URL: postgresql://botanical:${DB_PASSWORD}@timescaledb:5432/botanical
    depends_on:
      timescaledb:
        condition: service_healthy
      mosquitto:
        condition: service_started
    restart: unless-stopped

volumes:
  mosquitto_data:
  timescaledb_data:
```

**Step 3: Create server/.env from example**

```bash
cp server/.env.example server/.env
# Edit server/.env — set DB_PASSWORD to something real
```

**Step 4: Start the stack**

```bash
cd server
docker compose up --build
```

Expected: all three services start. TimescaleDB runs init.sql on first boot (watch for
`database system is ready to accept connections`). mqtt_bridge logs
`Connected to MQTT broker mosquitto:1883`.

**Step 5: Confirm data flows end-to-end**

With the stack running, power on (or reset) the ESP32 scanner with `config.h` pointing
at the server's LAN IP for `MQTT_HOST`. After the first scan cycle:

```bash
# Check scan_events in the DB
docker compose exec timescaledb psql -U botanical -c \
    "SELECT time, node_id, mac, scan_type, rssi FROM scan_events ORDER BY time DESC LIMIT 10;"
```

Expected: rows appear with your local WiFi/BLE MACs.

**Step 6: Commit**

```bash
cd ..
git add server/mqtt_bridge/Dockerfile server/docker-compose.yml
git commit -m "feat(server): add Docker Compose stack with Mosquitto, TimescaleDB, mqtt_bridge"
```

---

### Task 8: Update CLAUDE.md and add server README

**Files:**
- Modify: `CLAUDE.md`
- Create: `server/README.md`

**Step 1: Add server stack section to CLAUDE.md**

Add under `## Build & Flash`:

```markdown
## Server Stack

```bash
cd server
cp .env.example .env   # fill in DB_PASSWORD
docker compose up -d
```

Services: Mosquitto (1883), TimescaleDB (5432), mqtt_bridge (subscriber).
Schema applied automatically from `sql/init.sql` on first TimescaleDB start.
```

**Step 2: Write server/README.md**

```markdown
# server

Docker Compose stack: Mosquitto MQTT broker, TimescaleDB, and mqtt_bridge subscriber.

## Quickstart

```bash
cp .env.example .env
# Set DB_PASSWORD in .env
docker compose up -d
```

## Verify data is flowing

```bash
docker compose exec timescaledb psql -U botanical -c \
  "SELECT time, node_id, mac, scan_type, rssi FROM scan_events ORDER BY time DESC LIMIT 10;"
```

## Services

| Service | Port | Purpose |
|---------|------|---------|
| mosquitto | 1883 | MQTT broker |
| timescaledb | 5432 | PostgreSQL + TimescaleDB |
| mqtt_bridge | — | MQTT → DB subscriber |

## mqtt_bridge development

```bash
cd mqtt_bridge
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest -v
```
```

**Step 3: Commit**

```bash
git add CLAUDE.md server/README.md
git commit -m "docs: update CLAUDE.md and add server README for Milestone 2"
```

---

## Summary

After all tasks complete:

| What | State |
|------|-------|
| ESP32 firmware | Connects to WiFi AP, publishes scan results + status over MQTT every 30s |
| Mosquitto | Running in Docker, receiving node publishes |
| TimescaleDB | `scan_events` hypertable accumulating WiFi + BLE records |
| mqtt_bridge | Async Python subscriber with 9 passing unit tests |

**Next milestone:** FastAPI REST endpoints + SvelteKit device registry UI.
