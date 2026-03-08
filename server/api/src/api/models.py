from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class NodeResponse(BaseModel):
    node_id: str
    node_type: str
    location: str | None
    last_seen: datetime
    firmware_ver: str


class DeviceResponse(BaseModel):
    mac: str
    device_type: str
    label: str | None
    tag: str
    first_seen: datetime
    last_seen: datetime
    vendor: str | None
    ssid: str | None


class ScanEventResponse(BaseModel):
    time: datetime
    node_id: str
    mac: str
    rssi: int
    scan_type: str
    ssid: str | None


class LabelUpdate(BaseModel):
    label: str


class TagUpdate(BaseModel):
    tag: str
