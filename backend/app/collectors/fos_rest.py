"""Brocade FabricOS REST API 수집기 (FOS 8.2+/9.x).

엔드포인트(요약):
  POST /rest/login                                  -> Authorization 토큰 발급
  POST /rest/logout                                 -> 세션 종료
  GET  /rest/running/brocade-chassis/chassis        -> 모델명
  GET  /rest/running/brocade-fibrechannel-switch/fibrechannel-switch
                                                    -> 스위치 이름/펌웨어
  GET  /rest/running/brocade-interface/fibrechannel -> 포트 목록/상태/속도

정직성 메모:
- operational-status(정수)와 속도/포트타입/WWN은 REST에서 안정적으로 얻는다.
- 대역폭 사용율(tx/rx %)은 REST의 octet 카운터 필드 명세가 펌웨어별로 달라
  실측 검증 전까지 None으로 둔다(추측값을 넣지 않는다). 데모 수집기에서만
  사용율을 합성한다. -> 향후 버전에서 카운터 델타 기반으로 구현 예정.
"""
from __future__ import annotations

from typing import Any

import httpx

from ..config import HTTP_TIMEOUT
from ..models import PortInfo, SwitchSnapshot
from .base import BaseCollector

# operational-status (정수) -> 문자열
_OP_STATUS = {2: "online", 3: "offline", 5: "faulty", 6: "testing"}

# port-type (정수) -> 문자열 (FOS 공통값, 미상은 type-N 으로 표기)
_PORT_TYPE = {
    0: "Unknown", 7: "E_Port", 10: "G_Port", 11: "U_Port",
    15: "F_Port", 16: "L_Port", 19: "EX_Port", 20: "D_Port", 30: "N_Port",
}


def _as_list(value: Any) -> list[dict]:
    """FOS 응답은 항목이 1개면 dict, 여러 개면 list로 올 수 있다."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _gbps(bits_per_sec: Any) -> float | None:
    try:
        v = float(bits_per_sec)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    return round(v / 1_000_000_000, 1)


class FOSRestCollector(BaseCollector):
    def __init__(self, switch: dict[str, Any]) -> None:
        super().__init__(switch)
        ip = self.ip or ""
        if ip.startswith(("http://", "https://")):
            self.base = ip.rstrip("/")
        else:
            self.base = f"https://{ip}".rstrip("/")

    async def collect(self) -> SwitchSnapshot:
        headers = {"Accept": "application/yang-data+json"}
        try:
            async with httpx.AsyncClient(
                timeout=HTTP_TIMEOUT, verify=self.verify_tls
            ) as client:
                token = await self._login(client)
                auth = {**headers, "Authorization": token}
                try:
                    name, fw = await self._switch_info(client, auth)
                    model = await self._chassis_model(client, auth)
                    ports = await self._ports(client, auth)
                finally:
                    await self._logout(client, auth)
            return SwitchSnapshot(
                reachable=True, name=name, model=model,
                fos_version=fw, ports=ports,
            )
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            msg = f"REST 오류 HTTP {code}"
            if code in (401, 403):
                msg = f"인증 실패(HTTP {code}) — 계정/권한 확인"
            return SwitchSnapshot(reachable=False, error=msg)
        except httpx.HTTPError as exc:
            return SwitchSnapshot(
                reachable=False, error=f"접속 실패: {exc!s}"
            )
        except Exception as exc:  # noqa: BLE001 - 외부 응답 방어
            return SwitchSnapshot(
                reachable=False, error=f"수집 실패: {exc!s}"
            )

    async def _login(self, client: httpx.AsyncClient) -> str:
        resp = await client.post(
            f"{self.base}/rest/login",
            auth=(self.username or "", self.password or ""),
        )
        resp.raise_for_status()
        token = resp.headers.get("Authorization")
        if not token:
            raise httpx.HTTPError("로그인 응답에 Authorization 토큰 없음")
        return token

    async def _logout(self, client: httpx.AsyncClient, auth: dict) -> None:
        try:
            await client.post(f"{self.base}/rest/logout", headers=auth)
        except httpx.HTTPError:
            pass  # 로그아웃 실패는 치명적이지 않음

    async def _switch_info(
        self, client: httpx.AsyncClient, auth: dict
    ) -> tuple[str | None, str | None]:
        url = (
            f"{self.base}/rest/running/brocade-fibrechannel-switch/"
            "fibrechannel-switch"
        )
        resp = await client.get(url, headers=auth)
        resp.raise_for_status()
        body = resp.json().get("Response", {})
        sw = _as_list(body.get("fibrechannel-switch"))
        if not sw:
            return None, None
        first = sw[0]
        return first.get("user-friendly-name") or first.get("name"), (
            first.get("firmware-version")
        )

    async def _chassis_model(
        self, client: httpx.AsyncClient, auth: dict
    ) -> str | None:
        url = f"{self.base}/rest/running/brocade-chassis/chassis"
        try:
            resp = await client.get(url, headers=auth)
            resp.raise_for_status()
        except httpx.HTTPError:
            return None  # 모델명은 부가정보 — 실패해도 진행
        body = resp.json().get("Response", {})
        ch = _as_list(body.get("chassis"))
        if not ch:
            return None
        return ch[0].get("product-name") or ch[0].get("vendor-part-number")

    async def _ports(
        self, client: httpx.AsyncClient, auth: dict
    ) -> list[PortInfo]:
        url = f"{self.base}/rest/running/brocade-interface/fibrechannel"
        resp = await client.get(url, headers=auth)
        resp.raise_for_status()
        body = resp.json().get("Response", {})
        ports: list[PortInfo] = []
        for idx, fc in enumerate(_as_list(body.get("fibrechannel"))):
            op = fc.get("operational-status")
            try:
                op_int = int(op)
            except (TypeError, ValueError):
                op_int = -1
            status = _OP_STATUS.get(op_int, "offline")

            pt = fc.get("port-type")
            try:
                ptype = _PORT_TYPE.get(int(pt), f"type-{pt}")
            except (TypeError, ValueError):
                ptype = None

            neighbor = fc.get("neighbor") or {}
            neighbor_wwn = None
            if isinstance(neighbor, dict):
                wwns = _as_list(neighbor.get("wwn"))
                if wwns:
                    neighbor_wwn = wwns[0] if isinstance(wwns[0], str) else None

            ports.append(
                PortInfo(
                    name=fc.get("name", str(idx)),
                    port_index=idx,
                    enabled=bool(fc.get("is-enabled-state", True)),
                    operational_status=status,
                    speed_gbps=_gbps(fc.get("speed")),
                    max_speed_gbps=_gbps(fc.get("max-speed")),
                    port_type=ptype,
                    wwn=fc.get("wwn"),
                    neighbor_wwn=neighbor_wwn,
                    tx_util_pct=None,  # REST 실측 미구현(정직)
                    rx_util_pct=None,
                )
            )
        return ports
