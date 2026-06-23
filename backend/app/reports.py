"""용량 계획 리포트 (집계 + CSV).

- 스위치별 사용/여유 포트, 속도 분포, DC별 롤업.
- 사용율 추세(상승/하강/유지)는 전역 히스토리로 정성 판단한다.
  (과적합 예측을 지어내지 않는다 — 데이터가 적으면 'insufficient'.)
"""
from __future__ import annotations

import csv
import io
from collections import Counter, defaultdict
from typing import Any

from . import repository as repo
from .stats import merge_summaries, summarize_port_rows


def _trend() -> dict[str, Any]:
    hist = repo.get_global_history(500)
    if len(hist) < 4:
        return {"direction": "insufficient", "first_pct": None,
                "last_pct": None, "note": "추세 판단에 데이터 부족"}
    occ = [h["occupancy_pct"] for h in hist]
    third = max(1, len(occ) // 3)
    first_avg = sum(occ[:third]) / third
    last_avg = sum(occ[-third:]) / third
    diff = round(last_avg - first_avg, 1)
    direction = "rising" if diff > 1 else "falling" if diff < -1 else "stable"
    return {"direction": direction, "first_pct": round(first_avg, 1),
            "last_pct": round(last_avg, 1), "delta_pct": diff}


def capacity_report() -> dict[str, Any]:
    switches = repo.list_switches()
    speed_dist: Counter = Counter()
    summaries = []
    rows = []
    by_dc: dict[tuple, list] = defaultdict(list)

    for sw in switches:
        ports = repo.get_ports(sw["id"])
        s = summarize_port_rows(ports)
        summaries.append(s)
        by_dc[(sw["region"], sw["dc"])].append(s)
        for p in ports:
            if p.get("operational_status") in ("online", "in_sync") and \
                    p.get("speed_gbps"):
                speed_dist[f"{int(p['speed_gbps'])}G"] += 1
        rows.append({
            "switch_id": sw["id"], "name": sw.get("name"), "ip": sw["ip"],
            "region": sw["region"], "dc": sw["dc"],
            "model": sw.get("model"), "status": sw["status"],
            "total_ports": s["total_ports"], "used_ports": s["used_ports"],
            "free_ports": s["free_ports"], "error_ports": s["error_ports"],
            "occupancy_pct": s["occupancy_pct"],
        })

    return {
        "generated_utc": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "totals": merge_summaries(summaries),
        "speed_distribution": dict(sorted(
            speed_dist.items(), key=lambda kv: int(kv[0][:-1]))),
        "datacenters": [
            {"region": r, "dc": dc, "summary": merge_summaries(v)}
            for (r, dc), v in sorted(by_dc.items())
        ],
        "switches": rows,
        "trend": _trend(),
    }


def capacity_csv() -> str:
    report = capacity_report()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["switch_id", "name", "ip", "region", "dc", "model", "status",
                "total_ports", "used_ports", "free_ports", "error_ports",
                "occupancy_pct"])
    for r in report["switches"]:
        w.writerow([r["switch_id"], r["name"], r["ip"], r["region"], r["dc"],
                    r["model"], r["status"], r["total_ports"], r["used_ports"],
                    r["free_ports"], r["error_ports"], r["occupancy_pct"]])
    return buf.getvalue()
