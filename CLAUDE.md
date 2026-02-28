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

- `platformio.ini` — PlatformIO config (ESP32-S3 devkitc-1, Arduino framework)
- `src/main.cpp` — TFT test sketch

## Key Decisions

- **Framework**: Arduino via PlatformIO (not ESP-IDF) for quick bring-up
- **Library**: TFT_eSPI (bodmer) — pins configured via `build_flags` in `platformio.ini`, not by editing `User_Setup.h`
- **USB Serial**: `ARDUINO_USB_CDC_ON_BOOT=1` enabled for native USB CDC on ESP32-S3
- **SPI speed**: 40 MHz write, 20 MHz read

## Build & Flash

```bash
pio run -t upload && pio device monitor
```

## Status

- [ ] Hardware wiring (use wiring diagram above)
- [x] PlatformIO project + TFT_eSPI configured
- [x] Test sketch written (color cycle + Hello World)
- [ ] Flash and verify on hardware
