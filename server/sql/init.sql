CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS nodes (
    node_id      TEXT PRIMARY KEY,
    node_type    TEXT        NOT NULL,
    location     TEXT,
    last_seen    TIMESTAMPTZ NOT NULL DEFAULT now(),
    firmware_ver TEXT        NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS devices (
    mac         TEXT PRIMARY KEY,
    device_type TEXT        NOT NULL,
    label       TEXT,
    tag         TEXT        NOT NULL DEFAULT 'unknown',
    first_seen  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen   TIMESTAMPTZ NOT NULL DEFAULT now(),
    vendor      TEXT
);

CREATE TABLE IF NOT EXISTS scan_events (
    time      TIMESTAMPTZ NOT NULL,
    node_id   TEXT        NOT NULL,
    mac       TEXT        NOT NULL,
    rssi      INTEGER     NOT NULL,
    scan_type TEXT        NOT NULL,
    ssid      TEXT
);

SELECT create_hypertable('scan_events', by_range('time'), if_not_exists => TRUE);

SELECT add_retention_policy(
    'scan_events',
    INTERVAL '90 days',
    if_not_exists => TRUE
);

CREATE TABLE IF NOT EXISTS commands (
    id           SERIAL      PRIMARY KEY,
    node_id      TEXT        NOT NULL,
    command_type TEXT        NOT NULL,
    payload      JSONB       NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    executed_at  TIMESTAMPTZ
);
