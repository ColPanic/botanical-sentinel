from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator


class NodeResponse(BaseModel):
    node_id: str
    node_type: str
    location: str | None
    last_seen: datetime
    firmware_ver: str
    lat: float | None
    lon: float | None
    name: str | None


class NodeUpdate(BaseModel):
    name: Annotated[str, Field(max_length=100)] | None = None
    lat: float | None = None
    lon: float | None = None

    @field_validator("name", mode="before")
    @classmethod
    def _trim_name(cls, v: object) -> object:
        if isinstance(v, str):
            v = v.strip()
            return v if v else None
        return v

    @model_validator(mode="after")
    def _lat_lon_rules(self) -> "NodeUpdate":
        has_lat = self.lat is not None
        has_lon = self.lon is not None
        if has_lat != has_lon:
            raise ValueError("lat and lon must be provided together")
        if not has_lat and not has_lon:
            raise ValueError("lat and lon are required")
        return self


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
