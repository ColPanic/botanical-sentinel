# TFT Optional Firmware Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the TFT display optional by splitting `platformio.ini` into two environments
and guarding all TFT code in `main.cpp` with `#ifdef HAS_TFT`.

**Architecture:** A shared `[env]` base section holds common settings; `[env:esp32-s3-devkitc-1]`
is the headless variant (no additions needed); `[env:esp32-s3-devkitc-1-tft]` extends the base
with TFT_eSPI, pin flags, and `-D HAS_TFT=1`. Four `#ifdef HAS_TFT` guards in `main.cpp` isolate
all display code; `renderDisplay()` gets an empty stub so call sites need no guard.

**Tech Stack:** C++17, PlatformIO, Arduino framework, TFT_eSPI (ILI9341, bodmer)

**Note on TDD:** Firmware has no unit test runner. The discipline here is: edit → compile
(`pio run`) → confirm both environments build clean → commit.

---

### Task 1: Restructure `platformio.ini` into shared base + two environments

**Files:**
- Modify: `nodes/esp32-scanner/platformio.ini`

**Step 1: Replace the entire file with the new two-environment structure**

```ini
; ── Shared base ───────────────────────────────────────────────────────────────
[env]
platform      = espressif32
board         = esp32-s3-devkitc-1
framework     = arduino
monitor_speed = 115200
upload_speed  = 921600

lib_deps =
    knolleary/PubSubClient @ ^2.8
    bblanchon/ArduinoJson @ ^7.0

build_flags =
    ; Enable USB CDC serial on boot (ESP32-S3 native USB)
    -D ARDUINO_USB_CDC_ON_BOOT=1
    ; MQTT packet buffer — default 256 is too small for 20-entry JSON payloads
    -D MQTT_MAX_PACKET_SIZE=4096

; ── Headless (no display) ─────────────────────────────────────────────────────
[env:esp32-s3-devkitc-1]
; Inherits everything from [env] — no additions needed.

; ── With TFT display (ILI9341, 240×320) ──────────────────────────────────────
[env:esp32-s3-devkitc-1-tft]
lib_deps =
    ${env.lib_deps}
    bodmer/TFT_eSPI @ ^2.5.43

build_flags =
    ${env.build_flags}
    -D HAS_TFT=1

    ; Tell TFT_eSPI to use these defines instead of User_Setup.h
    -D USER_SETUP_LOADED=1

    ; Driver
    -D ILI9341_DRIVER=1

    ; SPI pins (ESP32-S3 SPI2/FSPI defaults)
    -D TFT_MOSI=11
    -D TFT_SCLK=12
    -D TFT_MISO=13

    ; Control pins
    -D TFT_CS=15
    -D TFT_DC=2
    -D TFT_RST=4

    ; Display dimensions
    -D TFT_WIDTH=240
    -D TFT_HEIGHT=320

    ; SPI clock speeds
    -D SPI_FREQUENCY=40000000
    -D SPI_READ_FREQUENCY=20000000

    ; Fonts to include
    -D LOAD_GLCD=1
    -D LOAD_FONT2=1
    -D LOAD_FONT4=1
    -D LOAD_GFXFF=1
    -D SMOOTH_FONT=1

    ; ESP32-S3: force SPI_PORT=2 (FSPI peripheral index) instead of using
    ; FSPI enum which changed to SPI2_HOST=1 in Arduino-ESP32 3.x / ESP-IDF 5.x
    -D USE_FSPI_PORT
```

**Step 2: Verify both environments compile**

```bash
pio run --project-dir nodes/esp32-scanner
```

Expected output ends with two `[SUCCESS]` lines — one for each environment.

If the headless build fails with TFT-related errors, the guards in Task 2 haven't been
applied yet — that's expected at this point if you're doing tasks out of order. Come back
and verify after Task 2.

**Step 3: Commit**

```bash
git add nodes/esp32-scanner/platformio.ini
git commit -m "build(esp32-scanner): split into headless and TFT environments"
```

---

### Task 2: Guard TFT code in `main.cpp` with `#ifdef HAS_TFT`

**Files:**
- Modify: `nodes/esp32-scanner/src/main.cpp`

There are four regions to guard. Apply them in order.

---

**Region 1 — include and global object**

Find these two lines (near the top of the file):

```cpp
#include <TFT_eSPI.h>
```

and (in the `// ── State ──` section):

```cpp
static TFT_eSPI tft;
```

Wrap each separately:

```cpp
#ifdef HAS_TFT
#include <TFT_eSPI.h>
#endif
```

```cpp
#ifdef HAS_TFT
static TFT_eSPI tft;
#endif
```

---

**Region 2 — `renderDisplay()` function body**

Find the function signature:

```cpp
static void renderDisplay(uint32_t scanStartMs) {
```

Wrap the entire body in `#ifdef HAS_TFT`, and add an empty `#else` stub so the call
site in `loop()` compiles without needing its own guard:

```cpp
static void renderDisplay(uint32_t scanStartMs) {
#ifdef HAS_TFT
    tft.fillScreen(TFT_BLACK);

    // ── Header ────────────────────────────────────────────────────────────────
    char buf[40];
    // ... (all existing body lines, unchanged) ...
    tft.drawString(buf, 4, 225, 2);
#else
    (void)scanStartMs;
#endif
}
```

Keep every existing line inside the `#ifdef` block — only the outer wrapper changes.

---

**Region 3 — `setup()` TFT initialisation**

Find these three lines inside `setup()`:

```cpp
    tft.init();
    tft.setRotation(1);
    tft.fillScreen(TFT_BLACK);
```

Wrap them:

```cpp
#ifdef HAS_TFT
    tft.init();
    tft.setRotation(1);
    tft.fillScreen(TFT_BLACK);
#endif
```

---

**Region 4 — `loop()` "Scanning…" splash**

Find these four lines inside the `if (millis() - lastScan >= SCAN_INTERVAL_MS)` block:

```cpp
        tft.fillScreen(TFT_BLACK);
        tft.setTextDatum(MC_DATUM);
        tft.setTextColor(TFT_WHITE, TFT_BLACK);
        tft.drawString("Scanning...", 160, 120, 4);
```

Wrap them:

```cpp
#ifdef HAS_TFT
        tft.fillScreen(TFT_BLACK);
        tft.setTextDatum(MC_DATUM);
        tft.setTextColor(TFT_WHITE, TFT_BLACK);
        tft.drawString("Scanning...", 160, 120, 4);
#endif
```

The `renderDisplay(lastScan)` call that follows does **not** need a guard — the stub
handles it.

---

**Step 5: Verify both environments compile clean**

```bash
pio run --project-dir nodes/esp32-scanner
```

Expected: two `[SUCCESS]` lines. No warnings about undeclared `tft` or missing TFT
symbols in the headless build.

**Step 6: Commit**

```bash
git add nodes/esp32-scanner/src/main.cpp
git commit -m "feat(esp32-scanner): make TFT display optional via HAS_TFT flag"
```

---

### Task 3: Update CLAUDE.md flash commands

**Files:**
- Modify: `CLAUDE.md`

The existing flash command doesn't specify an environment. Update the **Build & Flash**
section to show both variants:

```markdown
## Build & Flash

```bash
# Enter bootloader: hold BOOT, press+release RESET, release BOOT

# Headless (no display)
pio run --project-dir nodes/esp32-scanner -e esp32-s3-devkitc-1 -t upload --upload-port /dev/cu.usbmodem2101

# With TFT display
pio run --project-dir nodes/esp32-scanner -e esp32-s3-devkitc-1-tft -t upload --upload-port /dev/cu.usbmodem2101

pio device monitor --project-dir nodes/esp32-scanner
```
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update flash commands for headless and TFT environments"
```
