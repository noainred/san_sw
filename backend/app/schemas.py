"""API 요청/응답 스키마."""
from __future__ import annotations

from pydantic import BaseModel, Field


class SwitchCreate(BaseModel):
    ip: str = Field(..., description="스위치 관리 IP 또는 http(s):// URL")
    name: str | None = None
    dc: str = "default"
    region: str = "global"
    method: str = Field("fos_rest", description="fos_rest | snmp | demo")
    username: str | None = None
    password: str | None = None
    verify_tls: bool = False


class SwitchUpdate(BaseModel):
    ip: str | None = None
    name: str | None = None
    dc: str | None = None
    region: str | None = None
    method: str | None = None
    username: str | None = None
    password: str | None = None
    verify_tls: bool | None = None
    lat: float | None = None
    lon: float | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = Field("viewer", description="admin | operator | viewer")


class AlertRuleCreate(BaseModel):
    name: str
    metric: str = Field(..., description="occupancy_pct|error_ports|crc_errors|"
                                         "sfp_rx_power_dbm|switch_unreachable")
    comparator: str = Field(">", description="> | < | >= | <= | ==")
    threshold: float = 0
    severity: str = Field("warning", description="info|warning|critical")
    enabled: bool = True
