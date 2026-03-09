# TTGO LoRa32 V1.1 Scanner Node — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `nodes/ttgo-lora32/` — a PlatformIO project for the TTGO LoRa32 V1.1 that
runs WiFi + BLE scanning and displays results on the onboard SSD1306 OLED (128×64, I2C).

**Architecture:** Separate node directory from the existing ESP32-S3 scanner. Same scan
logic and MQTT JSON payloads; display code is new (`#ifdef HAS_OLED`) using Adafruit
SSD1306. Two PlatformIO environments: headless (no OLED lib) and oled.

**Tech Stack:** Arduino framework via PlatformIO, ESP32, Adafruit_SSD1306, Adafruit_GFX,
PubSubClient, ArduinoJson.

---

## Local build command

On this machine PlatformIO lives in a venv. Use the full path:

```bash
~/.platformio/penv/bin/pio run --project-dir nodes/ttgo-lora32 -e ttgo-lora32-headless
```

Or for both envs:

```bash
~/.platformio/penv/bin/pio run --project-dir nodes/ttgo-lora32
```

---

## Task 1: Node skeleton

**Files:**
- Create: `nodes/ttgo-lora32/src/config.h.example`

**Step 1: Create config.h.example**

```cpp
#pragma once

// Copy to config.h and fill in your values. config.h is gitignored.

#define WIFI_SSID      "your-network-name"
#define WIFI_PASSWORD  "your-password"

#define MQTT_HOST      "192.168.1.x"   // IP of your server running Mosquitto
#define MQTT_PORT      1883

#define NODE_ID        "ttgo-lora32-01"   // unique per device
#define FIRMWARE_VER   "0.1.0"
```

**Step 2: Create local config.h for builds**

```bash
cp nodes/ttgo-lora32/src/config.h.example nodes/ttgo-lora32/src/config.h
# Edit config.h to fill in real WiFi/MQTT values
```

**Step 3: Commit**

```bash
git add nodes/ttgo-lora32/src/config.h.example
git commit -m "Add TTGO LoRa32 node skeleton"
```

---

## Task 2: platformio.ini

**Files:**
- Create: `nodes/ttgo-lora32/platformio.ini`

**Step 1: Create platformio.ini**

```ini
; ── Shared base ───────────────────────────────────────────────────────────────
[env]
platform      = espressif32
board         = ttgo-lora32-v1
framework     = arduino
monitor_speed = 115200
upload_speed  = 921600

lib_deps =
    knolleary/PubSubClient @ ^2.8
    bblanchon/ArduinoJson @ ^7.0

build_flags =
    ; MQTT packet buffer — default 256 is too small for 20-entry JSON payloads
    -D MQTT_MAX_PACKET_SIZE=4096
    ; No ARDUINO_USB_CDC_ON_BOOT — this board uses a CH340 USB-serial chip

; ── Headless (no display) ─────────────────────────────────────────────────────
[env:ttgo-lora32-headless]
; Inherits everything from [env] — no additions needed.

; ── With OLED display (SSD1306, 128×64, I2C) ──────────────────────────────────
[env:ttgo-lora32-oled]
lib_deps =
    ${env.lib_deps}
    adafruit/Adafruit SSD1306 @ ^2.5.7
    adafruit/Adafruit GFX Library @ ^1.11.9

build_flags =
    ${env.build_flags}
    -D HAS_OLED=1
    -D OLED_SDA=21
    -D OLED_SCL=22
    -D OLED_RST=16
```

**Step 2: Commit**

```bash
git add nodes/ttgo-lora32/platformio.ini
git commit -m "Add TTGO LoRa32 PlatformIO config"
```

---

## Task 3: main.cpp — headless build

**Files:**
- Create: `nodes/ttgo-lora32/src/main.cpp`

**Step 1: Write main.cpp**

This is nearly identical to `nodes/esp32-scanner/src/main.cpp`. Key differences:
- No `ARDUINO_USB_CDC_ON_BOOT` define needed (CH340 handles USB)
- `#ifdef HAS_OLED` instead of `#ifdef HAS_TFT`
- OLED rendering uses Adafruit_SSD1306 API (see Task 4 for that block)

```cpp
#include <Arduino.h>
#include <ArduinoJson.h>
#include <BLEAdvertisedDevice.h>
#include <BLEDevice.h>
#include <BLEScan.h>
#include <PubSubClient.h>
#ifdef HAS_OLED
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#endif
#include <WiFi.h>
#include <WiFiClient.h>

#include "config.h"

// ── Constants ─────────────────────────────────────────────────────────────────

static constexpr uint32_t SCAN_INTERVAL_MS = 30000;
static constexpr uint8_t  MAX_WIFI         = 20;
static constexpr uint8_t  MAX_BLE          = 20;

// ── Types ─────────────────────────────────────────────────────────────────────

struct WifiResult {
    char    ssid[33];
    uint8_t bssid[6];
    int32_t rssi;
    uint8_t channel;
};

struct BleResult {
    char    name[32];
    char    mac[18];
    int32_t rssi;
};

// ── State ─────────────────────────────────────────────────────────────────────

#ifdef HAS_OLED
static Adafruit_SSD1306 oled(128, 64, &Wire, OLED_RST);
#endif
static WifiResult wifiResults[MAX_WIFI];
static uint8_t    wifiCount  = 0;
static uint32_t   scanCount  = 0;
static BleResult  bleResults[MAX_BLE];
static uint8_t    bleCount   = 0;

// ── MQTT ──────────────────────────────────────────────────────────────────────

static WiFiClient   wifiClient;
static PubSubClient mqtt(wifiClient);

static char topicWifi[64];
static char topicBle[64];
static char topicStatus[64];
static char mqttBuf[4096];

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

// ── WiFi scan ─────────────────────────────────────────────────────────────────

static void scanWifi() {
    int found = WiFi.scanNetworks(/*async=*/false, /*show_hidden=*/true);
    if (found < 0) found = 0;

    wifiCount = static_cast<uint8_t>(found > MAX_WIFI ? MAX_WIFI : found);

    for (uint8_t i = 0; i < wifiCount; i++) {
        String ssid = WiFi.SSID(i);
        strncpy(wifiResults[i].ssid, ssid.c_str(), 32);
        wifiResults[i].ssid[32] = '\0';
        const uint8_t* bssid = WiFi.BSSID(i);
        if (bssid != nullptr) {
            memcpy(wifiResults[i].bssid, bssid, 6);
        } else {
            memset(wifiResults[i].bssid, 0, 6);
        }
        wifiResults[i].rssi    = WiFi.RSSI(i);
        wifiResults[i].channel = static_cast<uint8_t>(WiFi.channel(i));
    }

    WiFi.scanDelete();

    Serial.printf("[WiFi] %u networks\n", wifiCount);
    for (uint8_t i = 0; i < wifiCount; i++) {
        const char* ssid = wifiResults[i].ssid[0]
            ? wifiResults[i].ssid : "[hidden]";
        Serial.printf("  %-32s  %4d dBm  ch%u\n",
            ssid, wifiResults[i].rssi, wifiResults[i].channel);
    }
}

// ── BLE scan ──────────────────────────────────────────────────────────────────

static void scanBle() {
    BLEScan* pScan = BLEDevice::getScan();
    pScan->setActiveScan(false);
    pScan->setInterval(100);
    pScan->setWindow(99);

    BLEScanResults results = pScan->start(/*seconds=*/5, /*is_continue=*/false);
    int found = results.getCount();

    bleCount = static_cast<uint8_t>(found > MAX_BLE ? MAX_BLE : found);

    for (uint8_t i = 0; i < bleCount; i++) {
        BLEAdvertisedDevice dev = results.getDevice(i);

        strncpy(bleResults[i].name, dev.getName().c_str(), 31);
        bleResults[i].name[31] = '\0';

        strncpy(bleResults[i].mac, dev.getAddress().toString().c_str(), 17);
        bleResults[i].mac[17] = '\0';

        bleResults[i].rssi = dev.getRSSI();
    }

    pScan->clearResults();

    Serial.printf("[BLE] %u devices\n", bleCount);
    for (uint8_t i = 0; i < bleCount; i++) {
        const char* label = bleResults[i].name[0]
            ? bleResults[i].name : bleResults[i].mac;
        Serial.printf("  %-31s  %4d dBm\n", label, bleResults[i].rssi);
    }
}

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

// ── Display render ────────────────────────────────────────────────────────────

static void renderDisplay(uint32_t scanStartMs) {
#ifdef HAS_OLED
    // See Task 4 — this stub lets the headless env compile cleanly
    (void)scanStartMs;
#else
    (void)scanStartMs;
#endif
}

// ── Arduino entry points ──────────────────────────────────────────────────────

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("=== botanical-sentinel ttgo-lora32 node ===");

#ifdef HAS_OLED
    Wire.begin(OLED_SDA, OLED_SCL);
    if (!oled.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
        Serial.println("[OLED] Init failed — check wiring");
    } else {
        oled.clearDisplay();
        oled.setTextSize(1);
        oled.setTextColor(SSD1306_WHITE);
        oled.setCursor(0, 0);
        oled.println("botanical-sentinel");
        oled.println("Connecting...");
        oled.display();
    }
#endif

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

void loop() {
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
#ifdef HAS_OLED
        oled.clearDisplay();
        oled.setTextSize(1);
        oled.setTextColor(SSD1306_WHITE);
        oled.setCursor(20, 28);
        oled.println("Scanning...");
        oled.display();
#endif

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

**Step 2: Build headless env — expect SUCCESS**

```bash
~/.platformio/penv/bin/pio run --project-dir nodes/ttgo-lora32 -e ttgo-lora32-headless
```

Expected: `SUCCESS` with RAM/Flash usage summary.

If it fails with "board not found": PlatformIO may need to download the espressif32 platform
first. That's fine — it downloads automatically on first build (takes ~2 min).

**Step 3: Commit**

```bash
git add nodes/ttgo-lora32/src/main.cpp
git commit -m "Add TTGO LoRa32 headless firmware"
```

---

## Task 4: OLED display rendering

**Files:**
- Modify: `nodes/ttgo-lora32/src/main.cpp` — replace the stub `renderDisplay` body

**Step 1: Replace renderDisplay stub with full implementation**

The 128×64 display fits (at 6×8px per char, 1px line gap):

```
y= 0: W:8 B:5 #4          ← header
y= 9: ────────────────     ← divider
y=11: HomeNet      -62     ← wifi[0]: 12-char SSID, 4-char RSSI
y=20: Neighbor     -71     ← wifi[1]
y=29: [hidden]     -85     ← wifi[2]
y=38: ────────────────     ← divider
y=40: AppleTV      -55     ← ble[0]: 14-char name, 4-char RSSI
y=49: Phone        -67     ← ble[1]
y=56: 12s ago              ← elapsed
```

Replace the `renderDisplay` function:

```cpp
static void renderDisplay(uint32_t scanStartMs) {
#ifdef HAS_OLED
    oled.clearDisplay();
    oled.setTextSize(1);
    oled.setTextColor(SSD1306_WHITE);

    // Header: "W:8 B:5 #4"
    char buf[32];
    snprintf(buf, sizeof(buf), "W:%u B:%u #%lu",
        wifiCount, bleCount, static_cast<unsigned long>(scanCount));
    oled.setCursor(0, 0);
    oled.print(buf);

    oled.drawFastHLine(0, 9, 128, SSD1306_WHITE);

    // WiFi rows (up to 3)
    uint8_t wRows = wifiCount < 3 ? wifiCount : 3;
    for (uint8_t i = 0; i < wRows; i++) {
        const char* raw = wifiResults[i].ssid[0]
            ? wifiResults[i].ssid : "[hidden]";
        char ssidBuf[13];
        strncpy(ssidBuf, raw, 12);
        ssidBuf[12] = '\0';
        snprintf(buf, sizeof(buf), "%-12s%4d", ssidBuf, wifiResults[i].rssi);
        oled.setCursor(0, 11 + i * 9);
        oled.print(buf);
    }

    oled.drawFastHLine(0, 38, 128, SSD1306_WHITE);

    // BLE rows (up to 2)
    uint8_t bRows = bleCount < 2 ? bleCount : 2;
    for (uint8_t i = 0; i < bRows; i++) {
        const char* raw = bleResults[i].name[0]
            ? bleResults[i].name : bleResults[i].mac;
        char nameBuf[15];
        strncpy(nameBuf, raw, 14);
        nameBuf[14] = '\0';
        snprintf(buf, sizeof(buf), "%-14s%4d", nameBuf, bleResults[i].rssi);
        oled.setCursor(0, 40 + i * 9);
        oled.print(buf);
    }

    // Footer: elapsed
    uint32_t elapsedSec = (millis() - scanStartMs) / 1000;
    snprintf(buf, sizeof(buf), "%lus ago",
        static_cast<unsigned long>(elapsedSec));
    oled.setCursor(0, 56);
    oled.print(buf);

    oled.display();
#else
    (void)scanStartMs;
#endif
}
```

**Step 2: Build oled env — expect SUCCESS**

```bash
~/.platformio/penv/bin/pio run --project-dir nodes/ttgo-lora32 -e ttgo-lora32-oled
```

Expected: `SUCCESS`.

**Step 3: Build both envs — expect SUCCESS on both**

```bash
~/.platformio/penv/bin/pio run --project-dir nodes/ttgo-lora32
```

**Step 4: Commit**

```bash
git add nodes/ttgo-lora32/src/main.cpp
git commit -m "Add TTGO LoRa32 OLED display rendering"
```

---

## Task 5: CI workflow

The existing `firmware.yml` triggers on `nodes/esp32-**/**` — the `ttgo-lora32` directory
doesn't match that glob. Extend the workflow to cover it.

**Files:**
- Modify: `.github/workflows/firmware.yml`

**Step 1: Update firmware.yml**

Change the `on:` paths and matrix to include ttgo-lora32. Also add a step to copy
`config.h.example → config.h` so the CI build succeeds without secrets.

```yaml
name: Firmware

on:
  pull_request:
    paths:
      - 'nodes/esp32-**/**'
      - 'nodes/ttgo-lora32/**'
      - '.github/workflows/firmware.yml'
  push:
    branches: [main]
    paths:
      - 'nodes/esp32-**/**'
      - 'nodes/ttgo-lora32/**'

jobs:
  build:
    runs-on: ubuntu-24.04
    permissions:
      contents: read
    strategy:
      matrix:
        node: [esp32-scanner, ttgo-lora32]
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5  # v4

      - uses: actions/cache@0057852bfaa89a56745cba8c7296529d2fc39830  # v4
        with:
          path: ~/.platformio
          key: pio-${{ matrix.node }}-${{ hashFiles(format('nodes/{0}/platformio.ini', matrix.node)) }}

      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065  # v5
        with:
          python-version: '3.13'

      - name: Install PlatformIO
        run: pip install platformio==6.1.19

      - name: Create CI config.h from example
        run: cp nodes/${{ matrix.node }}/src/config.h.example nodes/${{ matrix.node }}/src/config.h

      - name: Build ${{ matrix.node }}
        run: pio run --project-dir nodes/${{ matrix.node }}
```

Note: the `Create CI config.h` step fixes a latent bug — the same step is now applied to
`esp32-scanner` too, which previously relied on a locally committed `config.h` being
present in CI (it isn't, it's gitignored).

**Step 2: Commit**

```bash
git add .github/workflows/firmware.yml
git commit -m "Extend firmware CI to cover ttgo-lora32 node"
```

---

## Done

All tasks complete when:
- `pio run --project-dir nodes/ttgo-lora32` reports SUCCESS for both envs locally
- CI passes on push/PR
- Board flashes and serial monitor shows scan output
- OLED env flashes and display shows the scan layout after first 30s cycle

Flash command (CH340 auto-reset works — no manual bootloader entry):

```bash
~/.platformio/penv/bin/pio run --project-dir nodes/ttgo-lora32 -e ttgo-lora32-oled \
  -t upload --upload-port /dev/cu.usbserial-<id>
```

Find the port: `ls /dev/cu.*` — look for `usbserial` (CH340) rather than `usbmodem` (native USB).
