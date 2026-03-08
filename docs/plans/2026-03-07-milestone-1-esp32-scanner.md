# Milestone 1: ESP32 Scanner Prototype Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restructure the repo for the full project, add GitHub CI, and build a repeating
passive WiFi + BLE scanner on the ESP32-S3 that displays results on the ILI9341 TFT.

**Architecture:** Single-loop Arduino sketch — WiFi passive scan (Arduino `WiFi.h`), then
BLE passive scan (`BLEDevice`/`BLEScan`), then `renderDisplay()` to TFT. Cycle repeats
every 30 seconds. No MQTT, no server, no vendor lookup in this milestone.

**Tech Stack:** C++17, Arduino via PlatformIO, TFT_eSPI (ILI9341), ESP32 Arduino
`WiFi.h`, ESP32 Arduino `BLEDevice`/`BLEScan`

**Note on TDD:** Firmware has no unit test runner. The equivalent discipline here is:
write code → compile check (`pio run`) → flash + manual serial/visual verification →
commit. Every task follows this pattern.

---

### Task 1: Restructure repo — move ESP32 files into nodes/esp32-scanner/

**Files:**
- Create: `nodes/esp32-scanner/src/main.cpp` (moved from `src/main.cpp`)
- Create: `nodes/esp32-scanner/platformio.ini` (moved from `platformio.ini`)
- Delete: `src/main.cpp`, `platformio.ini` (root-level originals)
- Create: `nodes/pi-camera/.gitkeep`
- Create: `nodes/pi-lora-gateway/.gitkeep`

**Step 1: Create directory and copy files**

```bash
mkdir -p nodes/esp32-scanner/src
cp src/main.cpp nodes/esp32-scanner/src/main.cpp
cp platformio.ini nodes/esp32-scanner/platformio.ini
```

**Step 2: Verify the new location builds**

```bash
pio run --project-dir nodes/esp32-scanner
```
Expected: `[SUCCESS]`

**Step 3: Remove root-level originals and create stub directories**

```bash
git rm src/main.cpp platformio.ini
rmdir src
mkdir -p nodes/pi-camera nodes/pi-lora-gateway
touch nodes/pi-camera/.gitkeep nodes/pi-lora-gateway/.gitkeep
```

**Step 4: Commit**

```bash
git add nodes/
git commit -m "refactor: move esp32 scanner into nodes/esp32-scanner/"
```

---

### Task 2: Add .gitignore

**Files:**
- Create: `.gitignore`

**Step 1: Write .gitignore**

```
# PlatformIO
nodes/**/.pio/
.pio/

# Python
__pycache__/
*.py[cod]
.venv/
*.egg-info/
dist/
.ruff_cache/
.ty_cache/

# Node
node_modules/
web/.svelte-kit/
web/build/

# Environment
.env
*.env.local

# IDE
.vscode/settings.json
.idea/

# macOS
.DS_Store
```

**Step 2: Verify ignored files disappear from git status**

```bash
git status
```
Expected: `.vscode/` no longer appears as untracked.

**Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: add .gitignore"
```

---

### Task 3: Add README.md

**Files:**
- Create: `README.md`

**Step 1: Write README.md**

```markdown
# esp_bot

Open-source IoT security and surveillance system for remote properties.

ESP32 and Raspberry Pi nodes passively scan for WiFi and Bluetooth devices, learn the
local RF environment, and alert on unknown devices. A home server aggregates data and
serves a web UI for device tagging and management.

## Hardware

| Node | Hardware | Role |
|------|----------|------|
| `esp32-scanner` | ESP32-S3-WROOM-1 + ILI9341 TFT | WiFi+BLE passive scan |
| `pi-camera` | Raspberry Pi 4-B + camera module | Motion detection, RTSP |
| `pi-lora-gateway` | Raspberry Pi 4-B + LoRa hat | LoRa → MQTT bridge |
| Server | x86_64 Linux (64 GB RAM) | MQTT, database, web UI |

## Repository Structure

```
nodes/      ESP32 and Raspberry Pi node code
server/     FastAPI backend + MQTT bridge
web/        SvelteKit frontend
docs/       Architecture and design docs
```

## Getting Started

See [docs/plans/2026-03-07-system-design.md](docs/plans/2026-03-07-system-design.md)
for full architecture.

### Build and flash the ESP32 scanner

Requires [PlatformIO](https://platformio.org/). See
[nodes/esp32-scanner/README.md](nodes/esp32-scanner/README.md) for wiring and
bootloader instructions.

```bash
pio run --project-dir nodes/esp32-scanner -t upload --upload-port /dev/cu.usbmodem2101
pio device monitor --project-dir nodes/esp32-scanner
```

## Scanning approach

This project uses **passive RF scanning only** — listening for WiFi probe requests,
beacon frames, and BLE advertisements. No active probing or deauthentication.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT
```

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add project README"
```

---

### Task 4: Add CONTRIBUTING.md and GitHub templates

**Files:**
- Create: `CONTRIBUTING.md`
- Create: `.github/PULL_REQUEST_TEMPLATE.md`
- Create: `.github/ISSUE_TEMPLATE/bug.md`
- Create: `.github/ISSUE_TEMPLATE/feature.md`

**Step 1: Write CONTRIBUTING.md**

```markdown
# Contributing

## ESP32 nodes

Requires [PlatformIO](https://platformio.org/).

```bash
pio run --project-dir nodes/esp32-scanner          # build
pio run --project-dir nodes/esp32-scanner -t upload \
    --upload-port /dev/cu.usbmodem2101              # flash
pio device monitor --project-dir nodes/esp32-scanner  # serial
```

## Server (Python)

Requires Python 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
cd server
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest -q
```

## Web (SvelteKit)

Requires Node 22.

```bash
cd web
npm install
npm run dev
```

## Workflow

- Branch from `main`, open a PR, all CI checks must pass before merge
- One logical change per commit, imperative mood subject line (≤72 chars)
- Never push directly to `main`

## Scanning policy

This project uses **passive RF scanning only**. Do not submit PRs that add active
probing, directed probe requests, or deauthentication frames.
```

**Step 2: Write .github/PULL_REQUEST_TEMPLATE.md**

```markdown
## What this does

<!-- Describe what the code does now, not what you changed -->

## Test plan

- [ ]
- [ ]

## Checklist

- [ ] CI passes
- [ ] No active scanning added (passive only)
```

**Step 3: Write .github/ISSUE_TEMPLATE/bug.md**

```markdown
---
name: Bug report
about: Something isn't working
---

**Component:** (esp32-scanner / pi-camera / server / web)

**What happened:**

**Expected behavior:**

**Steps to reproduce:**

**Firmware version / commit SHA:**
```

**Step 4: Write .github/ISSUE_TEMPLATE/feature.md**

```markdown
---
name: Feature request
about: New capability or improvement
---

**Component:** (firmware / server / web)

**Problem it solves:**

**Proposed approach:**
```

**Step 5: Commit**

```bash
git add CONTRIBUTING.md .github/
git commit -m "docs: add CONTRIBUTING, PR template, issue templates"
```

---

### Task 5: Add GitHub Actions CI for ESP32 firmware

**Files:**
- Create: `.github/workflows/firmware.yml`

**Step 1: Write firmware.yml**

```yaml
name: Firmware

on:
  pull_request:
    paths:
      - 'nodes/esp32-**/**'
      - '.github/workflows/firmware.yml'
  push:
    branches: [main]
    paths:
      - 'nodes/esp32-**/**'

jobs:
  build:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        node: [esp32-scanner]
    steps:
      - uses: actions/checkout@v4

      - uses: actions/cache@v4
        with:
          path: ~/.platformio
          key: >-
            pio-${{ matrix.node }}-
            ${{ hashFiles(format('nodes/{0}/platformio.ini', matrix.node)) }}

      - uses: actions/setup-python@v5
        with:
          python-version: '3.13'

      - name: Install PlatformIO
        run: pip install platformio

      - name: Build ${{ matrix.node }}
        run: pio run --project-dir nodes/${{ matrix.node }}
```

**Step 2: Verify locally**

```bash
pio run --project-dir nodes/esp32-scanner
```
Expected: `[SUCCESS]`

**Step 3: Commit**

```bash
git add .github/workflows/firmware.yml
git commit -m "ci: add PlatformIO build check for ESP32 nodes"
```

---

### Task 6: Implement WiFi passive scan with serial output

**Files:**
- Modify: `nodes/esp32-scanner/src/main.cpp`

Replace the existing color-cycle sketch entirely. Build the scanner up in stages,
verifying compilation at each step.

**Step 1: Write new main.cpp (WiFi scan only, no BLE, no display yet)**

```cpp
#include <Arduino.h>
#include <TFT_eSPI.h>
#include <WiFi.h>

// ── Constants ────────────────────────────────────────────────────────────────

static constexpr uint32_t SCAN_INTERVAL_MS = 30000;
static constexpr uint8_t  MAX_WIFI         = 20;

// ── Types ─────────────────────────────────────────────────────────────────────

struct WifiResult {
    char    ssid[33];   // 32 chars + null terminator
    uint8_t bssid[6];
    int32_t rssi;
    uint8_t channel;
};

// ── State ─────────────────────────────────────────────────────────────────────

static TFT_eSPI tft;
static WifiResult wifiResults[MAX_WIFI];
static uint8_t    wifiCount  = 0;
static uint32_t   scanCount  = 0;

// ── WiFi scan ─────────────────────────────────────────────────────────────────

static void scanWifi() {
    int found = WiFi.scanNetworks(/*async=*/false, /*show_hidden=*/true);
    if (found < 0) found = 0;

    wifiCount = static_cast<uint8_t>(found > MAX_WIFI ? MAX_WIFI : found);

    for (uint8_t i = 0; i < wifiCount; i++) {
        String ssid = WiFi.SSID(i);
        strncpy(wifiResults[i].ssid, ssid.c_str(), 32);
        wifiResults[i].ssid[32] = '\0';
        memcpy(wifiResults[i].bssid, WiFi.BSSID(i), 6);
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

// ── Arduino entry points ──────────────────────────────────────────────────────

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("=== esp_bot scanner node ===");

    tft.init();
    tft.setRotation(1);   // landscape: 320×240, USB connector on right
    tft.fillScreen(TFT_BLACK);

    WiFi.mode(WIFI_STA);
    WiFi.disconnect();
}

void loop() {
    // Subtract SCAN_INTERVAL_MS from 0 (uint32_t underflow) so the first
    // scan fires immediately without a 30-second wait on boot.
    static uint32_t lastScan = static_cast<uint32_t>(0) - SCAN_INTERVAL_MS;

    if (millis() - lastScan >= SCAN_INTERVAL_MS) {
        lastScan = millis();
        scanCount++;
        Serial.printf("\n--- Scan #%lu ---\n", scanCount);
        scanWifi();
    }
}
```

**Step 2: Compile check**

```bash
pio run --project-dir nodes/esp32-scanner
```
Expected: `[SUCCESS]`

**Step 3: Flash and verify serial output**

```
# Enter bootloader: hold BOOT, press+release RESET, release BOOT
# Port re-enumerates as /dev/cu.usbmodem2101
pio run --project-dir nodes/esp32-scanner \
    -t upload --upload-port /dev/cu.usbmodem2101
pio device monitor --project-dir nodes/esp32-scanner
```

Expected serial:
```
=== esp_bot scanner node ===

--- Scan #1 ---
[WiFi] 8 networks
  MyNetwork                         -45 dBm  ch6
  Neighbor_2G                       -72 dBm  ch1
  [hidden]                          -81 dBm  ch6
```

**Step 4: Commit**

```bash
git add nodes/esp32-scanner/src/main.cpp
git commit -m "feat(esp32-scanner): add WiFi passive scan with serial output"
```

---

### Task 7: Add BLE passive scan with serial output

**Files:**
- Modify: `nodes/esp32-scanner/src/main.cpp`

**Step 1: Add BLE includes after existing includes**

```cpp
#include <BLEAdvertisedDevice.h>
#include <BLEDevice.h>
#include <BLEScan.h>
```

**Step 2: Add BleResult struct and storage after WifiResult**

```cpp
static constexpr uint8_t MAX_BLE = 20;

struct BleResult {
    char    name[32];
    char    mac[18];   // "AA:BB:CC:DD:EE:FF\0"
    int32_t rssi;
};

static BleResult bleResults[MAX_BLE];
static uint8_t   bleCount = 0;
```

**Step 3: Add scanBle() function after scanWifi()**

```cpp
static void scanBle() {
    BLEScan* pScan = BLEDevice::getScan();
    pScan->setActiveScan(false);   // passive — never sends scan requests
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
```

**Step 4: Initialize BLEDevice in setup() (call once only)**

Add after `WiFi.disconnect()`:

```cpp
BLEDevice::init("");
```

**Step 5: Call scanBle() in loop() after scanWifi()**

```cpp
scanWifi();
scanBle();
```

**Step 6: Compile check**

```bash
pio run --project-dir nodes/esp32-scanner
```
Expected: `[SUCCESS]`

**Step 7: Flash and verify serial output**

Flash as in Task 6. Expected additional output:
```
[BLE] 3 devices
  iPhone                           -61 dBm
  7A:3F:CC:DD:EE:FF                -74 dBm
```

**Step 8: Commit**

```bash
git add nodes/esp32-scanner/src/main.cpp
git commit -m "feat(esp32-scanner): add BLE passive scan with serial output"
```

---

### Task 8: Implement TFT display layout

**Files:**
- Modify: `nodes/esp32-scanner/src/main.cpp`

Display is 320×240 in landscape (rotation=1). Font 2 rows are 16px tall.

```
y=0..19    Header:  "WiFi(N)               BLE(N)"
y=20       Divider
y=22..149  WiFi list — up to 8 rows (8 × 16px = 128px)
y=150      Divider
y=152..215 BLE list  — up to 4 rows (4 × 16px = 64px)
y=222      Divider
y=224..239 Footer:  "Scan #N   Xs ago"
```

**Step 1: Add renderDisplay() before setup()**

```cpp
static void renderDisplay(uint32_t scanStartMs) {
    tft.fillScreen(TFT_BLACK);

    // ── Header ────────────────────────────────────────────────────────────────
    char buf[40];

    snprintf(buf, sizeof(buf), "WiFi(%u)", wifiCount);
    tft.setTextDatum(TL_DATUM);
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
    tft.drawString(buf, 4, 4, 2);

    snprintf(buf, sizeof(buf), "BLE(%u)", bleCount);
    tft.setTextDatum(TR_DATUM);
    tft.drawString(buf, 316, 4, 2);

    tft.drawFastHLine(0, 20, 320, TFT_DARKGREY);

    // ── WiFi list ─────────────────────────────────────────────────────────────
    tft.setTextDatum(TL_DATUM);
    static constexpr uint8_t WIFI_ROWS = 8;
    uint8_t wRows = wifiCount < WIFI_ROWS ? wifiCount : WIFI_ROWS;

    for (uint8_t i = 0; i < wRows; i++) {
        int16_t y = 22 + i * 16;

        // SSID — truncate at 20 chars
        const char* raw = wifiResults[i].ssid[0]
            ? wifiResults[i].ssid : "[hidden]";
        char ssidBuf[21];
        strncpy(ssidBuf, raw, 20);
        ssidBuf[20] = '\0';

        tft.setTextColor(TFT_CYAN, TFT_BLACK);
        tft.drawString(ssidBuf, 4, y, 2);

        // RSSI + channel — right-aligned
        snprintf(buf, sizeof(buf), "%ddBm ch%u",
            wifiResults[i].rssi, wifiResults[i].channel);
        tft.setTextColor(TFT_YELLOW, TFT_BLACK);
        tft.setTextDatum(TR_DATUM);
        tft.drawString(buf, 316, y, 2);
        tft.setTextDatum(TL_DATUM);
    }

    if (wifiCount > WIFI_ROWS) {
        tft.setTextColor(TFT_DARKGREY, TFT_BLACK);
        tft.drawString("...", 4, 22 + WIFI_ROWS * 16, 2);
    }

    tft.drawFastHLine(0, 150, 320, TFT_DARKGREY);

    // ── BLE list ──────────────────────────────────────────────────────────────
    static constexpr uint8_t BLE_ROWS = 4;
    uint8_t bRows = bleCount < BLE_ROWS ? bleCount : BLE_ROWS;

    for (uint8_t i = 0; i < bRows; i++) {
        int16_t y = 152 + i * 16;

        const char* raw = bleResults[i].name[0]
            ? bleResults[i].name : bleResults[i].mac;
        char nameBuf[21];
        strncpy(nameBuf, raw, 20);
        nameBuf[20] = '\0';

        tft.setTextColor(TFT_GREEN, TFT_BLACK);
        tft.drawString(nameBuf, 4, y, 2);

        snprintf(buf, sizeof(buf), "%ddBm", bleResults[i].rssi);
        tft.setTextColor(TFT_YELLOW, TFT_BLACK);
        tft.setTextDatum(TR_DATUM);
        tft.drawString(buf, 316, y, 2);
        tft.setTextDatum(TL_DATUM);
    }

    tft.drawFastHLine(0, 222, 320, TFT_DARKGREY);

    // ── Footer ────────────────────────────────────────────────────────────────
    uint32_t elapsedSec = (millis() - scanStartMs) / 1000;
    snprintf(buf, sizeof(buf), "Scan #%lu   %lus ago",
        scanCount, static_cast<unsigned long>(elapsedSec));
    tft.setTextColor(TFT_DARKGREY, TFT_BLACK);
    tft.drawString(buf, 4, 225, 2);
}
```

**Step 2: Update loop() to show "Scanning..." and call renderDisplay()**

Replace the loop() body:

```cpp
void loop() {
    static uint32_t lastScan = static_cast<uint32_t>(0) - SCAN_INTERVAL_MS;

    if (millis() - lastScan >= SCAN_INTERVAL_MS) {
        // Show "Scanning..." splash while working
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
    }
}
```

**Step 3: Compile check**

```bash
pio run --project-dir nodes/esp32-scanner
```
Expected: `[SUCCESS]`

**Step 4: Flash and verify on hardware**

```bash
pio run --project-dir nodes/esp32-scanner \
    -t upload --upload-port /dev/cu.usbmodem2101
pio device monitor --project-dir nodes/esp32-scanner
```

Expected behavior:
- Display shows "Scanning..." for ~5–10 seconds (WiFi scan + 5s BLE scan)
- Results appear: cyan WiFi list (left) + yellow RSSI/channel (right)
- Green BLE list below divider
- Grey footer: "Scan #1   0s ago"
- Footer elapsed counter increments each cycle

**Step 5: Commit**

```bash
git add nodes/esp32-scanner/src/main.cpp
git commit -m "feat(esp32-scanner): render WiFi and BLE scan results on TFT"
```

---

### Task 9: Add node README

**Files:**
- Create: `nodes/esp32-scanner/README.md`

**Step 1: Write README**

```markdown
# esp32-scanner

Passive WiFi + BLE scanner node with ILI9341 TFT display.

Scans every 30 seconds and displays results in a live dashboard.
All results are also printed to serial at 115200 baud.

## Hardware

- **MCU:** ESP32-S3-WROOM-1 DevKit
- **Display:** 2.8" ILI9341 TFT SPI 240×320 V1.2

## Wiring (ESP32-S3 → ILI9341)

| GPIO | Display Pin | Notes |
|------|-------------|-------|
| 3.3V | VCC | |
| GND  | GND | |
| 11   | SDI / MOSI | SPI2 FSPI |
| 12   | SCK / CLK  | SPI2 FSPI |
| 13   | SDO / MISO | SPI2 FSPI |
| 15   | CS         | |
| 2    | DC / RS    | |
| 4    | RESET      | |
| 3.3V | LED / BL   | Via 100Ω resistor |

## Build & Flash

This board uses native USB only — no UART chip. Manual bootloader entry required:

1. Hold **BOOT**, press+release **RESET**, release **BOOT**
2. Port re-enumerates as `/dev/cu.usbmodem2101`
3. Flash:

```bash
pio run -t upload --upload-port /dev/cu.usbmodem2101
pio device monitor
```

Run from the `nodes/esp32-scanner/` directory, or from the repo root:

```bash
pio run --project-dir nodes/esp32-scanner -t upload \
    --upload-port /dev/cu.usbmodem2101
```

## TFT Layout

```
┌────────────────────────────────┐
│ WiFi(12)              BLE(4)   │  header
├────────────────────────────────┤
│ MyNetwork    -45dBm ch6        │
│ Neighbor_2G  -72dBm ch1        │
│ ···                            │
├────────────────────────────────┤
│ iPhone        -61dBm           │
│ 7A:3F:..      -74dBm           │
├────────────────────────────────┤
│ Scan #4   28s ago              │  footer
└────────────────────────────────┘
```

## Known Issues

- TFT_eSPI 2.5.43 on Arduino-ESP32 3.x requires `-D USE_FSPI_PORT` in
  `platformio.ini`. Already present. See `platformio.ini` for details.
- Classic Bluetooth inquiry is not implemented — it blocks for several seconds
  and is incompatible with the 30-second scan cycle.
```

**Step 2: Commit**

```bash
git add nodes/esp32-scanner/README.md
git commit -m "docs(esp32-scanner): add node README with wiring and flash instructions"
```

---

## Summary

After all tasks complete:

| What | State |
|------|-------|
| Repo structure | `nodes/`, `server/` (stub), `web/` (stub) |
| GitHub CI | PlatformIO build on every PR touching `nodes/esp32-**` |
| ESP32 scanner | Passive WiFi + BLE scan every 30s, TFT display, serial mirror |
| Documentation | Root README, CONTRIBUTING, PR template, issue templates, node README |

**Next milestone:** MQTT publish from the scanner node + server Docker Compose stack
(Mosquitto + TimescaleDB + FastAPI).
