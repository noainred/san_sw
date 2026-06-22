"""Prometheus exposition (텍스트 포맷).

GET /metrics 에서 스크래핑한다. 의존성 없이 표준 텍스트 포맷을 직접 생성한다.
"""
from __future__ import annotations

from . import repository as repo
from .stats import merge_summaries, summarize_port_rows


def _esc(v: str) -> str:
    return (v or "").replace("\\", "\\\\").replace('"', '\\"')


def render() -> str:
    switches = repo.list_switches()
    per = []
    for sw in switches:
        ports = repo.get_ports(sw["id"])
        per.append((sw, summarize_port_rows(ports)))
    g = merge_summaries([s for _, s in per])

    lines: list[str] = []

    def metric(name: str, help_: str, samples: list[tuple[str, float]]):
        lines.append(f"# HELP {name} {help_}")
        lines.append(f"# TYPE {name} gauge")
        for labels, value in samples:
            lines.append(f"{name}{labels} {value}")

    metric("sansw_switches_total", "등록된 스위치 수",
           [("", len(switches))])
    metric("sansw_ports_total", "전체 포트 수", [("", g["total_ports"])])
    metric("sansw_ports_used", "사용중 포트 수", [("", g["used_ports"])])
    metric("sansw_ports_free", "비어있는 포트 수", [("", g["free_ports"])])
    metric("sansw_ports_error", "장애 포트 수", [("", g["error_ports"])])
    metric("sansw_occupancy_pct", "전역 포트 점유율(%)",
           [("", g["occupancy_pct"])])

    up_samples = []
    occ_samples = []
    used_samples = []
    for sw, s in per:
        lbl = (f'{{switch="{_esc(sw.get("name") or sw["ip"])}",'
               f'region="{_esc(sw.get("region"))}",dc="{_esc(sw.get("dc"))}"}}')
        up_samples.append((lbl, 1 if sw.get("status") == "online" else 0))
        occ_samples.append((lbl, s["occupancy_pct"]))
        used_samples.append((lbl, s["used_ports"]))
    metric("sansw_switch_up", "스위치 온라인 여부(1/0)", up_samples)
    metric("sansw_switch_occupancy_pct", "스위치 점유율(%)", occ_samples)
    metric("sansw_switch_used_ports", "스위치 사용중 포트", used_samples)

    return "\n".join(lines) + "\n"
