# esp_bot — ESP32-S3 TFT Display Project

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
nodes/pi-camera/         — Raspberry Pi camera node (future)
nodes/pi-lora-gateway/   — Raspberry Pi LoRa gateway (future)
server/                  — FastAPI backend + MQTT bridge (future)
web/                     — SvelteKit frontend (future)
```

## Key Decisions

- **Framework**: Arduino via PlatformIO (not ESP-IDF) for quick bring-up
- **Library**: TFT_eSPI (bodmer) — pins configured via `build_flags` in `platformio.ini`, not by editing `User_Setup.h`
- **USB Serial**: `ARDUINO_USB_CDC_ON_BOOT=1` enabled for native USB CDC on ESP32-S3
- **SPI speed**: 40 MHz write, 20 MHz read

## Build & Flash

```bash
# Enter bootloader: hold BOOT, press+release RESET, release BOOT
pio run --project-dir nodes/esp32-scanner -t upload --upload-port /dev/cu.usbmodem2101
pio device monitor --project-dir nodes/esp32-scanner
```

## Status

- [ ] Hardware wiring (use wiring diagram above)
- [x] PlatformIO project + TFT_eSPI configured
- [x] Test sketch written (color cycle + Hello World)
- [ ] Flash and verify on hardware
