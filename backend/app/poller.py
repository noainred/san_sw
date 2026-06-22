"""백그라운드 폴러.

POLL_INTERVAL 주기로 모든 스위치를 수집해 DB에 반영한다. 수동 폴링
(API /poll)도 같은 poll_switch()를 재사용한다. DB 접근은 동기이므로
asyncio.to_thread로 감싸 이벤트 루프를 막지 않는다.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from . import repository as repo
from .collectors import get_collector
from .config import POLL_INTERVAL
from .stats import summarize_ports

log = logging.getLogger("sansw.poller")


async def poll_switch(switch: dict[str, Any]) -> dict[str, Any]:
    """스위치 1대 폴링 -> DB 반영 -> 요약 반환."""
    collector = get_collector(switch)
    snapshot = await collector.collect()

    if not snapshot.reachable:
        await asyncio.to_thread(
            repo.set_switch_status,
            switch["id"], "unreachable",
            last_error=snapshot.error,
        )
        return {"id": switch["id"], "ok": False, "error": snapshot.error}

    await asyncio.to_thread(repo.replace_ports, switch["id"], snapshot.ports)
    summary = summarize_ports(snapshot.ports)
    await asyncio.to_thread(repo.add_sample, switch["id"], summary)
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
