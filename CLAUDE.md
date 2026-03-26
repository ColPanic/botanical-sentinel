# botanical-sentinel — ESP32-S3 TFT Display Project

## Hardware

- **MCU**: ESP32-S3-WROOM-1 DevKit
- **Display**: 2.8" TFT SPI 240x320 V1.2 (ILI9341 driver, has onboard SD card slot)
- **Reference photo**: `esp32_screen.jpg`

## Wiring (ESP32-S3 → ILI9341)

| GPIO | Display Pin | Notes |
|------|-------------|-------|
| 3.3V | VCC | |
| GND  | GND | |
| 11   | SDI / MOSI | SPI2 FSPI default |
| 12   | SCK / CLK  | SPI2 FSPI default |
| 13   | SDO / MISO | SPI2 FSPI default |
| 15   | CS         | TFT chip select |
| 2    | DC / RS    | Data/command |
| 4    | RESET      | |
| 3.3V | LED / BL   | Via 100Ω resistor |
| 5    | SD_CS      | SD card chip select |

SD card MOSI/MISO/SCK share the SPI bus (GPIO 11/12/13).

## Project Structure

```
nodes/esp32-scanner/     — ESP32-S3 scanner node (WiFi+BLE scan + TFT display)
  platformio.ini         — PlatformIO config (ESP32-S3 devkitc-1, Arduino framework)
  src/main.cpp           — Scanner sketch
nodes/ttgo-lora32/       — TTGO T-Beam V1.1 node (WiFi+BLE+GPS+LoRa + OLED)
server/mqtt_bridge/      — MQTT→TimescaleDB bridge
server/api/              — FastAPI REST API + WebSocket
web/                     — SvelteKit frontend (adapter-node)
```

## Key Decisions

- **Framework**: Arduino via PlatformIO (not ESP-IDF) for quick bring-up
- **Library**: TFT_eSPI (bodmer) — pins configured via `build_flags` in `platformio.ini`, not by editing `User_Setup.h`
- **USB Serial**: `ARDUINO_USB_CDC_ON_BOOT=1` enabled for native USB CDC on ESP32-S3
- **SPI speed**: 40 MHz write, 20 MHz read

## Build & Flash

```bash
# Enter bootloader: hold BOOT, press+release RESET, release BOOT

# Headless (no display)
pio run --project-dir nodes/esp32-scanner -e esp32-s3-devkitc-1-headless -t upload --upload-port /dev/cu.usbmodem2101

# With TFT display
pio run --project-dir nodes/esp32-scanner -e esp32-s3-devkitc-1-tft -t upload --upload-port /dev/cu.usbmodem2101

pio device monitor --project-dir nodes/esp32-scanner
```

## Server Stack

```bash
cd server
cp .env.example .env   # fill in DB_PASSWORD
docker compose up -d
```

Services: Mosquitto (1883), TimescaleDB (5432), mqtt_bridge, FastAPI (8000), web (3000).
Schema applied automatically from `sql/init.sql` on first TimescaleDB start.

## Web Stack

- SvelteKit (adapter-node) on port 3000, FastAPI on port 8000
- Vite dev proxy (`vite.config.ts`) forwards `/nodes`, `/devices`, `/scan`, `/positions` to FastAPI
- Proxy uses `bypass` to skip SvelteKit-internal `__data.json` requests — do not remove this
- Leaflet for maps; tooltips inject outside Svelte's scoped DOM — use `:global()` for tooltip CSS
- Verify before committing: `cd web && npm run check && npm run build`
- Pages: `/nodes`, `/devices`, `/scan`, `/map` (live WebSocket)

## Status

- [x] ESP32-S3 scanner node (WiFi+BLE scan, MQTT publish)
- [x] TTGO T-Beam node (WiFi+BLE+GPS, MQTT publish)
- [x] Server stack (Mosquitto, TimescaleDB, mqtt_bridge, FastAPI, SvelteKit)
- [x] Web dashboard (nodes, devices, scan, map with live WebSocket)
- [x] ESP32-S3 TFT display (WiFi+BLE scan + TFT rendering)
- [ ] LoRa uplink (waiting on hardware)
