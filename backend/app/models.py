"""수집기(collector)가 반환하는 도메인 모델.

DB 레코드와 분리된 순수 데이터 구조다. 수집 방식(REST/SNMP/SSH)이 달라도
이 형태로 정규화해서 상위 계층에 넘긴다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# 포트가 "사용중(트래픽 가능 상태)"으로 간주되는 물리 상태값들.
# Brocade physical-state 문자열 기준.
ONLINE_STATES = {"online", "in_sync"}

# 명백한 장애 상태.
ERROR_STATES = {
    "laser_flt",
    "port_flt",
    "hard_flt",
    "diag_flt",
    "faulty",
    "mod_inv",
}


@dataclass
class PortInfo:
    name: str  # 예: "0/12" (slot/port)
    port_index: int | None = None
    enabled: bool = True
    operational_status: str = "unknown"  # online/offline/no_module/no_light/...
    speed_gbps: float | None = None  # 현재 협상 속도(Gbps)
    max_speed_gbps: float | None = None  # 포트 최대 속도(Gbps)
    port_type: str | None = None  # E_Port/F_Port/...
    wwn: str | None = None
    neighbor_wwn: str | None = None
    tx_util_pct: float | None = None  # 송신 대역폭 사용율(%)
    rx_util_pct: float | None = None  # 수신 대역폭 사용율(%)
    # raw octet 카운터(누적). poller가 이전값과의 델타로 사용율을 계산한다.
    tx_octets: int | None = None
    rx_octets: int | None = None

    @property
    def is_used(self) -> bool:
        """장비가 붙어 온라인인 '사용중' 포트인지."""
        return self.operational_status in ONLINE_STATES

    @property
    def is_error(self) -> bool:
        return self.operational_status in ERROR_STATES

    @property
    def is_free(self) -> bool:
        """비어있는(미사용) 포트. 사용중도 장애도 아니면 비어있는 것으로 본다."""
        return not self.is_used and not self.is_error


@dataclass
class SwitchSnapshot:
    reachable: bool
    name: str | None = None
    model: str | None = None
    fos_version: str | None = None
    error: str | None = None
    ports: list[PortInfo] = field(default_factory=list)
