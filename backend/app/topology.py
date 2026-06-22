"""패브릭 토폴로지(ISL/E_Port 연결).

- build_demo_isl: 데모용으로 같은 리전 내 스위치를 링(ring) 형태로 연결한
  ISL 링크를 생성한다(실데이터가 아니라 합성 연결).
- graph: switches + isl_links -> 노드/엣지 그래프(프론트 시각화용).

실장비에서는 포트의 port_type=E_Port + neighbor_wwn를 다른 스위치의 wwn과
매칭해 ISL을 도출해야 한다(로드맵: 실데이터 매칭).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any


def build_demo_isl(switches: list[dict[str, Any]]) -> dict[int, list[dict]]:
    """리전별로 스위치들을 링으로 연결한 ISL 링크 맵 {switch_id: [link,...]}."""
    by_region: dict[str, list[dict]] = defaultdict(list)
    for sw in switches:
        by_region[sw.get("region", "global")].append(sw)

    links: dict[int, list[dict]] = defaultdict(list)
    for region, group in by_region.items():
        group = sorted(group, key=lambda s: s["id"])
        n = len(group)
        if n < 2:
            continue
        for i, sw in enumerate(group):
            nxt = group[(i + 1) % n]
            if n == 2 and i == 1:
                break  # 2대면 단일 링크
            links[sw["id"]].append({
                "local_port": f"E{i}",
                "remote_wwn": None,
                "remote_switch_id": nxt["id"],
                "speed_gbps": 32.0,
            })
    return links


def graph(switches: list[dict[str, Any]], isl: list[dict[str, Any]]) -> dict:
    """프론트 시각화용 노드/엣지."""
    nodes = [{
        "id": sw["id"],
        "name": sw.get("name") or sw.get("ip"),
        "region": sw.get("region"),
        "dc": sw.get("dc"),
        "status": sw.get("status"),
        "model": sw.get("model"),
    } for sw in switches]

    seen: set[tuple] = set()
    edges = []
    for link in isl:
        a = link.get("switch_id")
        b = link.get("remote_switch_id")
        if a is None or b is None:
            continue
        key = tuple(sorted((a, b)))
        if key in seen:
            continue
        seen.add(key)
        edges.append({
            "source": a, "target": b,
            "speed_gbps": link.get("speed_gbps"),
        })
    return {"nodes": nodes, "edges": edges}
