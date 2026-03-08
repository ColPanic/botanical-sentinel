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
server/     FastAPI backend + MQTT bridge  (planned)
web/        SvelteKit frontend             (planned)
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
