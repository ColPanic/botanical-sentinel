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
| 15   | CS         | TFT chip select |
| 2    | DC / RS    | Data/command |
| 4    | RESET      | |
| 3.3V | LED / BL   | Via 100Ω resistor |
| 5    | SD_CS      | SD card chip select (unused) |

## Build & Flash

This board uses native USB only — no UART chip. Manual bootloader entry is required:

1. Hold **BOOT**, press+release **RESET**, release **BOOT**
2. Port re-enumerates as `/dev/cu.usbmodem2101` (bootloader mode)
3. Flash from the repo root:

```bash
pio run --project-dir nodes/esp32-scanner -t upload --upload-port /dev/cu.usbmodem2101
pio device monitor --project-dir nodes/esp32-scanner
```

Or from this directory:

```bash
pio run -t upload --upload-port /dev/cu.usbmodem2101
pio device monitor
```

## TFT Display Layout

```
┌────────────────────────────────┐
│ WiFi(12)              BLE(4)   │  header (white)
├────────────────────────────────┤
│ MyNetwork    -45dBm ch6        │  WiFi list (cyan/yellow)
│ Neighbor_2G  -72dBm ch1        │
│ ···                            │
├────────────────────────────────┤
│ iPhone        -61dBm           │  BLE list (green/yellow)
│ 7A:3F:..      -74dBm           │
├────────────────────────────────┤
│ Scan #4   28s ago              │  footer (grey)
└────────────────────────────────┘
```

Refreshes every 30 seconds. Shows "Scanning..." during the scan cycle (~10s).

## Known Issues

- **`-D USE_FSPI_PORT` required**: TFT_eSPI 2.5.43 crashes on ESP32-S3 with
  Arduino-ESP32 3.x without this flag. Already set in `platformio.ini`.
- **Classic Bluetooth not implemented**: BT Classic inquiry blocks for several
  seconds and is incompatible with the 30-second scan cycle. BLE only for now.
