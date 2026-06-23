"""FOS(FabricOS) 펌웨어 인벤토리 + EoL(End of Life) 추적.

정직성 메모: 아래 EoL 날짜는 *참고용 예시*다. 실제 지원종료일은 Broadcom
공식 공지로 반드시 확인해야 한다(여기 값은 자리표시자). 분류 로직은 정확하며,
EOL_TABLE만 최신화하면 된다.
"""
from __future__ import annotations

from collections import Counter
from datetime import date

# FOS major("x.y") -> 대략적 지원종료일(예시, 검증 필요)
EOL_TABLE: dict[str, str] = {
    "9.2": "2029-12-31",
    "9.1": "2028-12-31",
    "9.0": "2027-06-30",
    "8.2": "2026-12-31",
    "8.1": "2025-06-30",
    "7.4": "2023-12-31",
}


def _major(version: str | None) -> str | None:
    if not version:
        return None
    parts = version.strip().lstrip("v").split(".")
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        return f"{parts[0]}.{parts[1]}"
    return None


def classify(version: str | None, today: date | None = None) -> dict:
    """버전 -> {major, eol, status, days_left}.
    status: supported | eol_soon(180일 이내) | eol | unknown
    """
    today = today or date.today()
    major = _major(version)
    eol_str = EOL_TABLE.get(major) if major else None
    if not eol_str:
        return {"version": version, "major": major, "eol": None,
                "status": "unknown", "days_left": None}
    eol = date.fromisoformat(eol_str)
    days_left = (eol - today).days
    if days_left < 0:
        status = "eol"
    elif days_left <= 180:
        status = "eol_soon"
    else:
        status = "supported"
    return {"version": version, "major": major, "eol": eol_str,
            "status": status, "days_left": days_left}


def inventory(switches: list[dict], today: date | None = None) -> dict:
    """스위치 목록 -> 펌웨어 분포 + EoL 요약."""
    today = today or date.today()
    by_version: Counter = Counter()
    rows = []
    status_counts: Counter = Counter()
    for sw in switches:
        ver = sw.get("fos_version")
        by_version[ver or "unknown"] += 1
        c = classify(ver, today)
        status_counts[c["status"]] += 1
        rows.append({
            "switch_id": sw.get("id"),
            "name": sw.get("name"),
            "region": sw.get("region"),
            "dc": sw.get("dc"),
            **c,
        })
    return {
        "generated": today.isoformat(),
        "by_version": dict(by_version),
        "status_counts": dict(status_counts),
        "switches": rows,
        "note": "EoL 날짜는 예시값 — Broadcom 공식 공지로 검증 필요.",
    }
