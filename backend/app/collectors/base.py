"""수집기 추상 베이스.

수집 방식(REST/SNMP/SSH/데모)이 달라도 collect()는 항상 SwitchSnapshot을
돌려준다. 도달 실패 시 예외를 던지지 말고 reachable=False 스냅샷으로 보고한다.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..models import SwitchSnapshot


class BaseCollector(ABC):
    def __init__(self, switch: dict[str, Any]) -> None:
        self.switch = switch
        self.ip = switch.get("ip")
        self.username = switch.get("username")
        self.password = switch.get("password")
        self.verify_tls = bool(switch.get("verify_tls"))

    @abstractmethod
    async def collect(self) -> SwitchSnapshot:
        """스위치 1대의 현재 상태를 수집한다."""
        raise NotImplementedError
