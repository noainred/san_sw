"""대역폭 사용율 계산(카운터 델타 기반).

순수 함수로 분리해 단위테스트 가능하게 한다.
"""
from __future__ import annotations


def bandwidth_util_pct(
    delta_octets: int | float,
    dt_seconds: float,
    speed_gbps: float | None,
) -> float | None:
    """octet 카운터 증가분으로 대역폭 사용율(%) 계산.

    - octet = 8 bit. bps = delta_octets*8 / dt.
    - 사용율 = bps / (speed_gbps * 1e9) * 100.
    - 카운터 리셋/래핑(delta<0), dt<=0, 속도 미상 등은 None 반환(추측 금지).
    - 0~100 범위로 클램프(라인레이트 초과 측정오차 방지).
    """
    if speed_gbps is None or speed_gbps <= 0:
        return None
    if dt_seconds <= 0:
        return None
    if delta_octets < 0:
        return None  # 카운터 리셋/래핑 의심 → 신뢰 불가
    bps = (delta_octets * 8) / dt_seconds
    capacity = speed_gbps * 1_000_000_000
    pct = bps / capacity * 100
    if pct < 0:
        return 0.0
    if pct > 100:
        return 100.0
    return round(pct, 1)
