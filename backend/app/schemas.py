"""API 요청/응답 스키마."""
from __future__ import annotations

from pydantic import BaseModel, Field


class SwitchCreate(BaseModel):
    ip: str = Field(..., description="스위치 관리 IP 또는 http(s):// URL")
    name: str | None = None
    dc: str = "default"
    region: str = "global"
    method: str = Field("fos_rest", description="fos_rest | demo")
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
