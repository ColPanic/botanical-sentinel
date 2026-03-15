# TTGO LoRa32 V1.1 Scanner Node — Design

## Context

The project already has an ESP32-S3 scanner node (`nodes/esp32-scanner/`) that does
WiFi + BLE scanning and publishes results over MQTT. This adds a second node for the
TTGO LoRa32 V1.1, which uses a different MCU family (ESP32 vs ESP32-S3) and has a
small SSD1306 OLED soldered on.

LoRa uplink is out of scope until the LoRa hat for the server arrives.

---

## Hardware

- **MCU**: ESP32 (Xtensa LX6, not S3)
- **USB serial**: CP2102 (auto-reset works — no manual bootloader entry needed)
- **Display**: SSD1306 OLED, 128×64, I2C
  - SDA = GPIO 21
  - SCL = GPIO 22
  - RST = GPIO 16
- **LoRa**: SX1278 (present on board, unused for now)

---

## Project Structure

```
nodes/ttgo-lora32/
  platformio.ini       — two envs: headless + oled
  src/
    main.cpp           — scan + publish + #ifdef HAS_OLED display
    config.h           — gitignored (WiFi/MQTT credentials, NODE_ID)
  .gitignore
```

New CI workflow `firmware-ttgo.yml` triggers on `nodes/ttgo-lora32/**`.

---

## PlatformIO Environments

| Env | Board | Extras |
|-----|-------|--------|
| `ttgo-lora32-headless` | `ttgo-lora32-v1` | base only |
| `ttgo-lora32-oled` | `ttgo-lora32-v1` | Adafruit_SSD1306 + GFX, `-D HAS_OLED=1` |

No `ARDUINO_USB_CDC_ON_BOOT` — CP2102 handles USB-serial.

---

## Display Layout (128×64, font size 1 = 6×8px)

```
W:8 B:5          #4
────────────────────
HomeNet    -62 ch6
Neighbor   -71 ch11
[hidden]   -85 ch1
────────────────────
AppleTV    -55
Phone      -67
────────────────────
12s ago
```

- Row 0: WiFi count, BLE count, scan number
- Rows 2–4: Top 3 WiFi networks (SSID ≤12 chars, RSSI, channel)
- Rows 6–7: Top 3 BLE devices (name/MAC ≤14 chars, RSSI)
- Row 7: Elapsed time since last scan

---

## Key Differences vs ESP32-S3 Node

| | ESP32-S3 DevKit | TTGO LoRa32 V1.1 |
|---|---|---|
| Board ID | `esp32-s3-devkitc-1` | `ttgo-lora32-v1` |
| USB serial | Native CDC (manual bootloader) | CP2102 (auto-reset) |
| `ARDUINO_USB_CDC_ON_BOOT` | Required | Not present |
| Display bus | SPI | I2C |
| Display driver | ILI9341 (TFT_eSPI) | SSD1306 (Adafruit) |
| Display resolution | 240×320 | 128×64 |

Scan logic, MQTT JSON payload shape, and `config.h` format are identical.

---

## config.h Shape (gitignored)

```cpp
#pragma once
#define WIFI_SSID      "your-ssid"
#define WIFI_PASSWORD  "your-password"
#define MQTT_HOST      "192.168.x.x"
#define MQTT_PORT      1883
#define NODE_ID        "ttgo-lora32-01"
#define FIRMWARE_VER   "0.1.0"
```
