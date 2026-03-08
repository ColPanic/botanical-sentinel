# TFT Optional Firmware Design

## Goal

Make the TFT display optional in the ESP32 scanner firmware so nodes without a screen
can run the same codebase.

## Approach

Two PlatformIO environments in a shared-base `platformio.ini`, with compile-time guarding
in `main.cpp` via `#ifdef HAS_TFT`.

## platformio.ini Structure

```
[env]                          — shared: platform, board, framework, common lib_deps,
                                 common build_flags (MQTT buffer, USB CDC, ArduinoJson,
                                 PubSubClient)
[env:esp32-s3-devkitc-1]      — headless; inherits everything, no additions
[env:esp32-s3-devkitc-1-tft]  — adds bodmer/TFT_eSPI to lib_deps; adds TFT pin flags,
                                 display size, SPI speeds, font flags, USE_FSPI_PORT,
                                 and -D HAS_TFT=1 to build_flags
```

## main.cpp Guards

Three `#ifdef HAS_TFT` regions:

1. **Includes + global** — `#include <TFT_eSPI.h>` and `static TFT_eSPI tft`
2. **`renderDisplay()` body** — entire function body guarded; headless build gets an
   empty stub so the call site in `loop()` needs no guard
3. **TFT calls in `setup()` and `loop()`** — `tft.init()`, rotation, fill, and the
   "Scanning…" splash in `loop()` wrapped in `#ifdef HAS_TFT`

## CI

No changes. `pio run` without `-e` builds all environments, so both variants are
automatically verified on every push.

## Flash / Build

```bash
# Headless
pio run -e esp32-s3-devkitc-1 -t upload --upload-port /dev/cu.usbmodem2101

# With TFT
pio run -e esp32-s3-devkitc-1-tft -t upload --upload-port /dev/cu.usbmodem2101
```
