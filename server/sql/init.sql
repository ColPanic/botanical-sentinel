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
    vendor      TEXT,
    ssid        TEXT
);

-- Idempotent migration for existing databases
ALTER TABLE devices ADD COLUMN IF NOT EXISTS ssid TEXT;

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

-- Idempotent coordinate migrations
ALTER TABLE nodes      ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION;
ALTER TABLE nodes      ADD COLUMN IF NOT EXISTS lon DOUBLE PRECISION;
ALTER TABLE scan_events ADD COLUMN IF NOT EXISTS node_lat DOUBLE PRECISION;
ALTER TABLE scan_events ADD COLUMN IF NOT EXISTS node_lon DOUBLE PRECISION;

CREATE TABLE IF NOT EXISTS position_estimates (
    time        TIMESTAMPTZ      NOT NULL,
    mac         TEXT             NOT NULL,
    lat         DOUBLE PRECISION NOT NULL,
    lon         DOUBLE PRECISION NOT NULL,
    accuracy_m  REAL,
    node_count  INTEGER          NOT NULL,
    method      TEXT             NOT NULL
);

SELECT create_hypertable('position_estimates', by_range('time'), if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS position_estimates_mac_time
    ON position_estimates (mac, time DESC);

SELECT add_retention_policy(
    'position_estimates',
    INTERVAL '30 days',
    if_not_exists => TRUE
);

ALTER TABLE nodes ADD COLUMN IF NOT EXISTS name TEXT;

-- Idempotent migration: track whether a node's location has been confirmed by a user or GPS fix
ALTER TABLE nodes ADD COLUMN IF NOT EXISTS location_confirmed BOOLEAN NOT NULL DEFAULT FALSE;
