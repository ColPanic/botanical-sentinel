from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class NodeResponse(BaseModel):
    node_id: str
    node_type: str
    location: str | None
    last_seen: datetime
    firmware_ver: str
    lat: float | None
    lon: float | None


class PositionResponse(BaseModel):
    time: datetime
    mac: str
    lat: float
    lon: float
    accuracy_m: float | None
    node_count: int
    method: str
    label: str | None
    tag: str
    vendor: str | None
    device_type: str


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
