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
pnpm install
pnpm dev
```

## Workflow

- Branch from `main`, open a PR, all CI checks must pass before merge
- One logical change per commit, imperative mood subject line (≤72 chars)
- Never push directly to `main`

## Scanning policy

This project uses **passive RF scanning only**. Do not submit PRs that add active
probing, directed probe requests, or deauthentication frames.
