"""임계치 알림: 규칙 평가 + 채널 발송(Webhook/Slack).

지원 metric:
- occupancy_pct       : 스위치 포트 점유율(%)
- error_ports         : 스위치 장애 포트 수
- crc_errors          : 스위치 내 포트 CRC 에러 최대값(누적)
- sfp_rx_power_dbm     : 스위치 내 SFP 수신광 최소값(낮을수록 위험, '<' 사용)
- switch_unreachable   : 도달불가면 1

중복 억제: 동일 규칙·스위치는 5분 내 재발생을 막는다.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from . import repository as repo
from .config import ALERT_WEBHOOK_URL, HTTP_TIMEOUT
from .stats import summarize_port_rows

log = logging.getLogger("sansw.alerts")
_DEDUP_WINDOW = 300  # 초


def _cmp(value: float, comparator: str, threshold: float) -> bool:
    if comparator == ">":
        return value > threshold
    if comparator == "<":
        return value < threshold
    if comparator == ">=":
        return value >= threshold
    if comparator == "<=":
        return value <= threshold
    if comparator == "==":
        return value == threshold
    return False


def _switch_metrics(sw: dict[str, Any], ports: list[dict]) -> dict[str, float]:
    s = summarize_port_rows(ports)
    crc_max = max((p.get("crc_errors") or 0 for p in ports), default=0)
    rx_vals = [p["sfp_rx_power_dbm"] for p in ports
               if p.get("sfp_rx_power_dbm") is not None]
    m: dict[str, float] = {
        "occupancy_pct": float(s["occupancy_pct"]),
        "error_ports": float(s["error_ports"]),
        "crc_errors": float(crc_max),
        "switch_unreachable": 1.0 if sw.get("status") == "unreachable" else 0.0,
    }
    if rx_vals:
        m["sfp_rx_power_dbm"] = float(min(rx_vals))
    return m


async def _notify(message: str, severity: str) -> None:
    if not ALERT_WEBHOOK_URL:
        return
    payload = {"text": f":rotating_light: san_sw [{severity}] {message}"}
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            await client.post(ALERT_WEBHOOK_URL, json=payload)
    except httpx.HTTPError as exc:
        log.warning("알림 webhook 발송 실패: %s", exc)


async def evaluate_and_notify() -> list[dict[str, Any]]:
    rules = repo.list_alert_rules(enabled_only=True)
    if not rules:
        return []
    switches = repo.list_switches()
    fired: list[dict[str, Any]] = []
    for sw in switches:
        ports = repo.get_ports(sw["id"])
        metrics = _switch_metrics(sw, ports)
        for rule in rules:
            val = metrics.get(rule["metric"])
            if val is None:
                continue
            if not _cmp(val, rule["comparator"], rule["threshold"]):
                continue
            if repo.recent_alert_exists(rule["id"], sw["id"], _DEDUP_WINDOW):
                continue
            msg = (f"{sw.get('name') or sw['ip']}: {rule['metric']} "
                   f"{rule['comparator']} {rule['threshold']} (현재 {val})")
            repo.add_alert(rule["id"], sw["id"], rule["severity"], msg, val)
            await _notify(msg, rule["severity"])
            fired.append({"rule": rule["name"], "switch_id": sw["id"],
                          "severity": rule["severity"], "message": msg})
    if fired:
        log.info("알림 %d건 발생", len(fired))
    return fired


def seed_default_rules() -> None:
    """규칙이 하나도 없으면 합리적 기본 규칙을 만든다."""
    if repo.list_alert_rules():
        return
    defaults = [
        {"name": "포트 점유율 90% 초과", "metric": "occupancy_pct",
         "comparator": ">", "threshold": 90, "severity": "warning"},
        {"name": "장애 포트 발생", "metric": "error_ports",
         "comparator": ">", "threshold": 0, "severity": "critical"},
        {"name": "CRC 에러 다발", "metric": "crc_errors",
         "comparator": ">", "threshold": 1000, "severity": "warning"},
        {"name": "SFP 수신광 약함(<-15dBm)", "metric": "sfp_rx_power_dbm",
         "comparator": "<", "threshold": -15, "severity": "warning"},
        {"name": "스위치 도달불가", "metric": "switch_unreachable",
         "comparator": ">=", "threshold": 1, "severity": "critical"},
    ]
    for d in defaults:
        repo.create_alert_rule(d)
