"""포트 사용율/집계 계산.

용어 정의(혼동 방지):
- '포트 사용율(occupancy)' = 사용중 포트 수 / 전체 포트 수 × 100.
  SAN 운영에서 "포트 사용율"은 보통 이 점유율을 뜻한다.
- '대역폭 사용율(utilization)' = 트래픽 / 포트 속도 × 100. 포트별 tx/rx.
  (현재 데모 수집기에서만 값 제공, REST 실측은 향후 버전)
- '사용중(used)' = operational online 포트.
- '비어있는(free)' = 사용중도 장애도 아닌 포트(no_module/no_light/offline 등).
- '장애(error)' = faulty 계열.
"""
from __future__ import annotations

from typing import Any, Iterable

from .models import PortInfo


def summarize_ports(ports: Iterable[PortInfo]) -> dict[str, Any]:
    """PortInfo 목록 -> 집계 요약."""
    total = used = free = error = 0
    util_values: list[float] = []
    for p in ports:
        total += 1
        if p.is_used:
            used += 1
        elif p.is_error:
            error += 1
        else:
            free += 1
        for v in (p.tx_util_pct, p.rx_util_pct):
            if v is not None:
                util_values.append(v)

    occupancy = round(used / total * 100, 1) if total else 0.0
    avg_util = round(sum(util_values) / len(util_values), 1) if util_values else None
    return {
        "total_ports": total,
        "used_ports": used,
        "free_ports": free,
        "error_ports": error,
        "occupancy_pct": occupancy,
        "avg_util_pct": avg_util,
    }


def summarize_port_rows(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """DB 포트 행(dict) 목록 -> 집계 요약."""
    ports = [
        PortInfo(
            name=r.get("name", ""),
            operational_status=r.get("operational_status") or "unknown",
            tx_util_pct=r.get("tx_util_pct"),
            rx_util_pct=r.get("rx_util_pct"),
        )
        for r in rows
    ]
    return summarize_ports(ports)


def empty_summary() -> dict[str, Any]:
    return {
        "total_ports": 0, "used_ports": 0, "free_ports": 0,
        "error_ports": 0, "occupancy_pct": 0.0, "avg_util_pct": None,
    }


def merge_summaries(summaries: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """여러 스위치 요약을 합산(전역/DC 롤업)."""
    agg = empty_summary()
    util_total = 0.0
    util_count = 0
    for s in summaries:
        agg["total_ports"] += s["total_ports"]
        agg["used_ports"] += s["used_ports"]
        agg["free_ports"] += s["free_ports"]
        agg["error_ports"] += s["error_ports"]
        if s.get("avg_util_pct") is not None:
            # 포트 수 가중 평균
            util_total += s["avg_util_pct"] * s["total_ports"]
            util_count += s["total_ports"]
    agg["occupancy_pct"] = (
        round(agg["used_ports"] / agg["total_ports"] * 100, 1)
        if agg["total_ports"] else 0.0
    )
    agg["avg_util_pct"] = (
        round(util_total / util_count, 1) if util_count else None
    )
    return agg
