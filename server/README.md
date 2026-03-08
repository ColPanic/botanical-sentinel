# server

Docker Compose stack: Mosquitto MQTT broker, TimescaleDB, and mqtt_bridge subscriber.

## Quickstart

```bash
cp .env.example .env
# Set DB_PASSWORD in .env
docker compose up -d
```

## Verify data is flowing

```bash
docker compose exec timescaledb psql -U botanical -c \
  "SELECT time, node_id, mac, scan_type, rssi FROM scan_events ORDER BY time DESC LIMIT 10;"
```

## Services

| Service | Port | Purpose |
|---------|------|---------|
| mosquitto | 1883 | MQTT broker |
| timescaledb | 5432 | PostgreSQL + TimescaleDB |
| mqtt_bridge | — | MQTT → DB subscriber |

## mqtt_bridge development

```bash
cd mqtt_bridge
uv venv --python python3.13 && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest -v
```
