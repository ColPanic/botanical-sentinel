from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass
class ScanEvent:
    node_id: str
    mac: str
    rssi: int
    scan_type: str
    ssid: str | None
    time: datetime


def extract_node_id(topic: str) -> str:
    """Extract node ID from topic string 'nodes/{node_id}/...'."""
    parts = topic.split("/")
    return parts[1] if len(parts) >= 2 else "unknown"


def parse_wifi(node_id: str, payload: bytes) -> list[ScanEvent]:
    """Parse a nodes/{id}/scan/wifi MQTT payload into ScanEvents."""
    items: list[dict] = json.loads(payload)
    now = datetime.now(UTC)
    events = []
    for item in items:
        bssid = item.get("bssid", "").strip().upper()
        if not bssid:
            continue
        ssid = item.get("ssid") or None
        events.append(ScanEvent(
            node_id=node_id,
            mac=bssid,
            rssi=int(item["rssi"]),
            scan_type="wifi",
            ssid=ssid,
            time=now,
        ))
    return events


def parse_ble(node_id: str, payload: bytes) -> list[ScanEvent]:
    """Parse a nodes/{id}/scan/bt MQTT payload into ScanEvents."""
    items: list[dict] = json.loads(payload)
    now = datetime.now(UTC)
    events = []
    for item in items:
        mac = item.get("mac", "").strip().upper()
        if not mac:
            continue
        events.append(ScanEvent(
            node_id=node_id,
            mac=mac,
            rssi=int(item["rssi"]),
            scan_type="ble",
            ssid=None,
            time=now,
        ))
    return events
