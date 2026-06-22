"""백그라운드 폴러.

POLL_INTERVAL 주기로 모든 스위치를 수집해 DB에 반영한다. 수동 폴링
(API /poll)도 같은 poll_switch()를 재사용한다. DB 접근은 동기이므로
asyncio.to_thread로 감싸 이벤트 루프를 막지 않는다.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from . import repository as repo
from .collectors import get_collector
from .config import POLL_INTERVAL
from .stats import summarize_ports
from .util_calc import bandwidth_util_pct

log = logging.getLogger("sansw.poller")


def _apply_counter_utilization(
    switch_id: int, ports: list, now: float
) -> list[tuple[str, int | None, int | None, float]]:
    """raw octet 카운터가 있는 포트에 한해, 직전 카운터와의 델타로
    tx/rx 대역폭 사용율(%)을 채운다. 갱신할 카운터 목록을 반환한다.

    카운터가 없는 수집기(데모 등)는 그대로 둔다(데모는 util을 직접 제공).
    """
    has_counters = [
        p for p in ports if p.tx_octets is not None or p.rx_octets is not None
    ]
    if not has_counters:
        return []
    prev = repo.get_port_counters(switch_id)
    new_counters: list[tuple[str, int | None, int | None, float]] = []
    for p in has_counters:
        new_counters.append((p.name, p.tx_octets, p.rx_octets, now))
        old = prev.get(p.name)
        if not old or not p.speed_gbps:
            continue
        dt = now - (old.get("ts") or 0)
        if p.tx_octets is not None and old.get("tx_octets") is not None:
            p.tx_util_pct = bandwidth_util_pct(
                p.tx_octets - old["tx_octets"], dt, p.speed_gbps)
        if p.rx_octets is not None and old.get("rx_octets") is not None:
            p.rx_util_pct = bandwidth_util_pct(
                p.rx_octets - old["rx_octets"], dt, p.speed_gbps)
    return new_counters


async def poll_switch(switch: dict[str, Any]) -> dict[str, Any]:
    """스위치 1대 폴링 -> DB 반영 -> 요약 반환."""
    # 폴링 직전에만 비밀번호 복호화(DB/응답엔 암호문 유지)
    switch = await asyncio.to_thread(repo.decrypted_switch, switch)
    collector = get_collector(switch)
    snapshot = await collector.collect()

    if not snapshot.reachable:
        await asyncio.to_thread(
            repo.set_switch_status,
            switch["id"], "unreachable",
            last_error=snapshot.error,
        )
        return {"id": switch["id"], "ok": False, "error": snapshot.error}

    now = time.time()
    new_counters = await asyncio.to_thread(
        _apply_counter_utilization, switch["id"], snapshot.ports, now)

    await asyncio.to_thread(repo.replace_ports, switch["id"], snapshot.ports)
    summary = summarize_ports(snapshot.ports)
    await asyncio.to_thread(repo.add_sample, switch["id"], summary)
    if new_counters:
        await asyncio.to_thread(
            repo.upsert_port_counters, switch["id"], new_counters)
    await asyncio.to_thread(
        repo.set_switch_status,
        switch["id"], "online",
        model=snapshot.model,
        fos_version=snapshot.fos_version,
        name=snapshot.name,
        last_error=None,
    )
    return {"id": switch["id"], "ok": True, "summary": summary}


async def poll_all() -> list[dict[str, Any]]:
    switches = await asyncio.to_thread(repo.list_switches)
    if not switches:
        return []
    results = await asyncio.gather(
        *(poll_switch(sw) for sw in switches), return_exceptions=True
    )
    out: list[dict[str, Any]] = []
    for sw, res in zip(switches, results):
        if isinstance(res, Exception):
            log.warning("폴링 예외 switch=%s: %s", sw.get("ip"), res)
            out.append({"id": sw["id"], "ok": False, "error": str(res)})
        else:
            out.append(res)
    return out


async def poller_loop(stop_event: asyncio.Event) -> None:
    if POLL_INTERVAL <= 0:
        log.info("POLL_INTERVAL<=0 — 백그라운드 폴러 비활성(수동 폴링만).")
        return
    log.info("백그라운드 폴러 시작: 주기 %ss", POLL_INTERVAL)
    while not stop_event.is_set():
        try:
            await poll_all()
        except Exception as exc:  # noqa: BLE001 - 루프 보호
            log.exception("폴링 사이클 오류: %s", exc)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=POLL_INTERVAL)
        except asyncio.TimeoutError:
            pass
    log.info("백그라운드 폴러 종료.")
