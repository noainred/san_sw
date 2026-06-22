"""데모 수집기.

실제 Brocade 장비가 없는 환경에서 UI/집계 로직을 검증하기 위한 합성 데이터.
스위치 IP를 시드로 사용해 포트 수/배치는 안정적으로 유지하고, 사용율만
호출마다 약간 흔들리게 해 실데이터처럼 보이게 한다.

주의: 이건 합성 데이터다. 실제 측정값이 아니다.
"""
from __future__ import annotations

import hashlib
import random
from typing import Any

from ..models import PortInfo, SwitchSnapshot

_MODELS = [
    ("Brocade G620", 64, 32.0),
    ("Brocade G630", 128, 32.0),
    ("Brocade G720", 64, 64.0),
    ("Brocade 6510", 48, 16.0),
    ("Brocade X6-4", 256, 32.0),
]
_PORT_TYPES = ["F_Port", "F_Port", "F_Port", "E_Port", "U_Port"]


def _seed_int(text: str) -> int:
    return int(hashlib.sha256(text.encode()).hexdigest(), 16)


class DemoCollector:
    def __init__(self, switch: dict[str, Any]) -> None:
        self.switch = switch
        self.ip = switch.get("ip", "0.0.0.0")
        self.name = switch.get("name")

    async def collect(self) -> SwitchSnapshot:
        # 스위치마다 고정된 특성(모델/포트수/사용중 비율)
        base = random.Random(_seed_int(self.ip))
        model, port_count, max_speed = base.choice(_MODELS)
        used_ratio = base.uniform(0.35, 0.85)
        # 호출마다 달라지는 부분(사용율 흔들림)
        jitter = random.Random()

        ports: list[PortInfo] = []
        for i in range(port_count):
            roll = base.random()  # 포트별 고정 상태 결정
            crc = enc = linkf = los = None
            temp = volt = txp = rxp = None
            if roll < used_ratio:
                status = "online"
                speed = base.choice([s for s in (8.0, 16.0, 32.0, 64.0)
                                     if s <= max_speed])
                ptype = base.choice(_PORT_TYPES)
                tx = round(min(99.0, max(0.0, jitter.gauss(45, 22))), 1)
                rx = round(min(99.0, max(0.0, jitter.gauss(40, 20))), 1)
                neighbor = f"20:00:00:25:b5:{i:02x}:{base.randint(0,255):02x}:ab"
                # 누적 에러 카운터(대부분 0~소량, 일부 포트는 불량으로 급증)
                bad = base.random() < 0.06  # 약 6% 포트는 에러 다발/광신호 약함
                crc = jitter.randint(2000, 60000) if bad else jitter.randint(0, 5)
                enc = jitter.randint(500, 20000) if bad else jitter.randint(0, 3)
                linkf = jitter.randint(1, 12) if bad else 0
                los = jitter.randint(1, 8) if bad else 0
                # SFP DDM (정상범위: temp<70, volt 3.1~3.5, rx -3~-10dBm)
                temp = round(jitter.gauss(48, 6), 1)
                volt = round(jitter.gauss(3.3, 0.05), 2)
                txp = round(jitter.gauss(-2.5, 0.6), 1)
                rxp = round(jitter.gauss(-13.5, 1.2) if bad
                            else jitter.gauss(-4.5, 1.2), 1)
            elif roll < used_ratio + 0.05:
                status = "no_light"  # 케이블만 꽂힘/링크 없음 -> 비어있음 취급
                speed, ptype, tx, rx, neighbor = None, None, None, None, None
            else:
                status = "no_module"  # SFP 없음 -> 비어있음
                speed, ptype, tx, rx, neighbor = None, None, None, None, None

            ports.append(
                PortInfo(
                    name=f"{i // 32}/{i % 32}",
                    port_index=i,
                    enabled=status != "no_module",
                    operational_status=status,
                    speed_gbps=speed,
                    max_speed_gbps=max_speed,
                    port_type=ptype,
                    wwn=f"50:00:53:33:{i:02x}:{_seed_int(self.ip) % 256:02x}:00:01",
                    neighbor_wwn=neighbor,
                    tx_util_pct=tx,
                    rx_util_pct=rx,
                    crc_errors=crc,
                    enc_out_errors=enc,
                    link_failures=linkf,
                    loss_of_sync=los,
                    sfp_temp_c=temp,
                    sfp_voltage_v=volt,
                    sfp_tx_power_dbm=txp,
                    sfp_rx_power_dbm=rxp,
                )
            )

        return SwitchSnapshot(
            reachable=True,
            name=self.name or f"sw-{self.ip.replace('.', '-')}",
            model=model,
            fos_version=base.choice(["9.1.1", "9.2.0", "8.2.3c", "9.0.1a"]),
            ports=ports,
        )
