"""SNMP 수집기 (IF-MIB 기반, SNMP v2c).

pysnmp는 선택 의존성이라 모듈 최상단에서 import하지 않고 collect() 안에서
지연 import한다(미설치 시 앱 전체가 죽지 않고 해당 스위치만 실패로 보고).

정직성 메모:
- 실제 SNMP 에이전트가 없는 환경이라 네트워크 I/O는 미검증이다.
  순수 변환 로직(상태/속도 매핑)만 단위테스트한다.
- IF-MIB 표준 OID를 사용한다. Brocade FC 포트는 보통 IF-MIB에 노출되지만,
  포트명/타입 등 FC 특화 정보는 FC 전용 MIB(FCMGMT-MIB 등)가 더 정확하다.
  v0.2는 IF-MIB로 사용중/비어있음/속도/대역폭(octet)까지 다룬다.
- 자격증명: 스위치의 username 칸에 community 문자열을 넣거나, 미입력 시
  SANSW_SNMP_COMMUNITY 기본값을 쓴다. SNMPv3는 추후.
"""
from __future__ import annotations

from typing import Any

from ..config import SNMP_COMMUNITY, SNMP_PORT, SNMP_TIMEOUT
from ..models import PortInfo, SwitchSnapshot
from .base import BaseCollector

# IF-MIB OID (컬럼)
OID_IF_DESCR = "1.3.6.1.2.1.2.2.1.2"
OID_IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8"
OID_IF_HIGH_SPEED = "1.3.6.1.2.1.31.1.1.1.15"   # Mbps
OID_IF_HC_IN_OCTETS = "1.3.6.1.2.1.31.1.1.1.6"
OID_IF_HC_OUT_OCTETS = "1.3.6.1.2.1.31.1.1.1.10"
OID_SYS_NAME = "1.3.6.1.2.1.1.5.0"
OID_SYS_DESCR = "1.3.6.1.2.1.1.1.0"


def snmp_oper_to_status(val: int | None) -> str:
    """ifOperStatus -> 내부 상태 문자열.
    1=up, 2=down, 3=testing, 5=dormant, 6=notPresent, 7=lowerLayerDown.
    """
    return "online" if val == 1 else "offline"


def highspeed_to_gbps(mbps: int | float | None) -> float | None:
    try:
        v = float(mbps)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    return round(v / 1000.0, 1)


def index_from_oid(oid: Any) -> int | None:
    """varBind OID에서 마지막 서브식별자(=ifIndex)를 추출."""
    try:
        return int(oid[-1])
    except (TypeError, ValueError, IndexError):
        try:
            return int(str(oid).rstrip(".").split(".")[-1])
        except (ValueError, IndexError):
            return None


class SNMPCollector(BaseCollector):
    def __init__(self, switch: dict[str, Any]) -> None:
        super().__init__(switch)
        host = self.ip or ""
        for scheme in ("http://", "https://"):
            if host.startswith(scheme):
                host = host[len(scheme):]
        self.host = host.split("/")[0].split(":")[0]
        self.community = self.username or SNMP_COMMUNITY
        self.port = SNMP_PORT

    async def collect(self) -> SwitchSnapshot:
        try:
            from pysnmp.hlapi.v3arch import asyncio as snmp
        except ImportError:
            return SwitchSnapshot(
                reachable=False,
                error="pysnmp 미설치 — `pip install pysnmp` 후 사용하세요.",
            )
        try:
            return await self._collect(snmp)
        except Exception as exc:  # noqa: BLE001 - 네트워크/파싱 방어
            return SwitchSnapshot(reachable=False, error=f"SNMP 실패: {exc!s}")

    async def _collect(self, snmp) -> SwitchSnapshot:
        engine = snmp.SnmpEngine()
        auth = snmp.CommunityData(self.community, mpModel=1)  # v2c
        target = await snmp.UdpTransportTarget.create(
            (self.host, self.port), timeout=SNMP_TIMEOUT, retries=1
        )
        ctx = snmp.ContextData()

        name, descr = await self._scalars(snmp, engine, auth, target, ctx)
        descrs = await self._walk(snmp, engine, auth, target, ctx, OID_IF_DESCR)
        opers = await self._walk(snmp, engine, auth, target, ctx, OID_IF_OPER_STATUS)
        speeds = await self._walk(snmp, engine, auth, target, ctx, OID_IF_HIGH_SPEED)
        in_oct = await self._walk(snmp, engine, auth, target, ctx, OID_IF_HC_IN_OCTETS)
        out_oct = await self._walk(snmp, engine, auth, target, ctx, OID_IF_HC_OUT_OCTETS)

        ports: list[PortInfo] = []
        for idx in sorted(descrs):
            speed = highspeed_to_gbps(_to_int(speeds.get(idx)))
            ports.append(PortInfo(
                name=str(descrs[idx]),
                port_index=idx,
                operational_status=snmp_oper_to_status(_to_int(opers.get(idx))),
                speed_gbps=speed,
                max_speed_gbps=speed,
                tx_octets=_to_int(out_oct.get(idx)),
                rx_octets=_to_int(in_oct.get(idx)),
            ))
        return SwitchSnapshot(
            reachable=True, name=name, model=descr, ports=ports,
        )

    async def _scalars(self, snmp, engine, auth, target, ctx):
        ei, es, _ex, vbs = await snmp.get_cmd(
            engine, auth, target, ctx,
            snmp.ObjectType(snmp.ObjectIdentity(OID_SYS_NAME)),
            snmp.ObjectType(snmp.ObjectIdentity(OID_SYS_DESCR)),
        )
        if ei:
            raise RuntimeError(str(ei))
        if es:
            raise RuntimeError(es.prettyPrint())
        name = str(vbs[0][1]) if vbs else None
        descr = str(vbs[1][1]) if len(vbs) > 1 else None
        # sysDescr는 길다 — 첫 토큰(벤더/모델 추정)만 모델 칸에 사용
        model = descr.split(",")[0].strip() if descr else None
        return name or None, model

    async def _walk(self, snmp, engine, auth, target, ctx, oid) -> dict[int, Any]:
        result: dict[int, Any] = {}
        async for (ei, es, _ex, vbs) in snmp.bulk_walk_cmd(
            engine, auth, target, ctx, 0, 25,
            snmp.ObjectType(snmp.ObjectIdentity(oid)),
            lexicographicMode=False,
        ):
            if ei:
                raise RuntimeError(str(ei))
            if es:
                raise RuntimeError(es.prettyPrint())
            for vb_oid, value in vbs:
                idx = index_from_oid(vb_oid)
                if idx is not None:
                    result[idx] = value
        return result


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
