"""FastAPI 진입점.

- /api/* : REST API
- /      : 웹 대시보드(정적 파일)
백그라운드 폴러를 lifespan으로 띄우고, 최초 기동 시(설정에 따라) 데모 스위치를
시드한 뒤 즉시 1회 폴링한다.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import repository as repo
from . import upgrade as upgrade_mod
from . import version as version_mod
from .config import FRONTEND_DIR, POLL_INTERVAL, SEED_DEMO
from .db import init_db
from .poller import poll_all, poll_switch, poller_loop
from .schemas import SwitchCreate, SwitchUpdate
from .stats import merge_summaries, summarize_port_rows

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("sansw")

_DEMO_SWITCHES = [
    # 문서용(TEST-NET) IP — 실제 장비 아님이 한눈에 보이도록.
    {"name": "seoul-sw01", "ip": "192.0.2.11", "dc": "Seoul-DC1", "region": "APAC"},
    {"name": "seoul-sw02", "ip": "192.0.2.12", "dc": "Seoul-DC1", "region": "APAC"},
    {"name": "tokyo-sw01", "ip": "192.0.2.21", "dc": "Tokyo-DC", "region": "APAC"},
    {"name": "fra-sw01", "ip": "198.51.100.11", "dc": "Frankfurt-DC", "region": "EMEA"},
    {"name": "fra-sw02", "ip": "198.51.100.12", "dc": "Frankfurt-DC", "region": "EMEA"},
    {"name": "iad-sw01", "ip": "203.0.113.11", "dc": "Virginia-DC", "region": "AMER"},
]


def _seed_demo() -> None:
    if repo.count_switches() > 0:
        return
    log.info("DB가 비어 있어 데모 스위치 %d대 시드(method=demo).",
             len(_DEMO_SWITCHES))
    for s in _DEMO_SWITCHES:
        repo.create_switch({**s, "method": "demo"})


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if SEED_DEMO:
        await asyncio.to_thread(_seed_demo)
    stop_event = asyncio.Event()
    # 최초 1회 즉시 폴링(데이터 빠르게 채우기) + 주기 폴러
    asyncio.create_task(poll_all())
    task = asyncio.create_task(poller_loop(stop_event))
    try:
        yield
    finally:
        stop_event.set()
        task.cancel()


app = FastAPI(title="san_sw — Brocade SAN Switch Manager",
              version=version_mod.get_version(), lifespan=lifespan)


# ---------------------------------------------------------- 직렬화 헬퍼

def _public_switch(row: dict[str, Any]) -> dict[str, Any]:
    """비밀번호 등 민감 필드를 제외한 스위치 표현."""
    out = {k: v for k, v in row.items() if k != "password"}
    out["has_credentials"] = bool(row.get("username") and row.get("password"))
    return out


def _switch_with_summary(row: dict[str, Any]) -> dict[str, Any]:
    ports = repo.get_ports(row["id"])
    data = _public_switch(row)
    data["summary"] = summarize_port_rows(ports)
    return data


# --------------------------------------------------------------- 버전/업그레이드

@app.get("/api/version")
async def api_version() -> dict[str, Any]:
    return {"version": version_mod.get_version(),
            "poll_interval": POLL_INTERVAL}


@app.get("/api/upgrade/check")
async def api_upgrade_check() -> dict[str, Any]:
    return await version_mod.check_latest()


@app.post("/api/upgrade/apply")
async def api_upgrade_apply() -> dict[str, Any]:
    return await upgrade_mod.apply_upgrade()


# ----------------------------------------------------------------- 요약/대시보드

@app.get("/api/summary")
async def api_summary() -> dict[str, Any]:
    switches = await asyncio.to_thread(repo.list_switches)
    per_switch = [_switch_with_summary(s) for s in switches]

    by_region: dict[str, list] = defaultdict(list)
    by_dc: dict[tuple, list] = defaultdict(list)
    status_counts = defaultdict(int)
    for s in per_switch:
        by_region[s["region"]].append(s["summary"])
        by_dc[(s["region"], s["dc"])].append(s["summary"])
        status_counts[s["status"]] += 1

    return {
        "version": version_mod.get_version(),
        "switch_count": len(per_switch),
        "status_counts": dict(status_counts),
        "global": merge_summaries(s["summary"] for s in per_switch),
        "regions": [
            {"region": r, "switch_count": len(v),
             "summary": merge_summaries(v)}
            for r, v in sorted(by_region.items())
        ],
        "datacenters": [
            {"region": r, "dc": dc, "switch_count": len(v),
             "summary": merge_summaries(v)}
            for (r, dc), v in sorted(by_dc.items())
        ],
    }


# --------------------------------------------------------------------- 스위치

@app.get("/api/switches")
async def api_list_switches() -> list[dict[str, Any]]:
    switches = await asyncio.to_thread(repo.list_switches)
    return [_switch_with_summary(s) for s in switches]


@app.post("/api/switches", status_code=201)
async def api_create_switch(payload: SwitchCreate) -> dict[str, Any]:
    try:
        row = await asyncio.to_thread(repo.create_switch, payload.model_dump())
    except Exception as exc:  # UNIQUE 위반 등
        raise HTTPException(status_code=400, detail=f"생성 실패: {exc!s}")
    # 추가 즉시 1회 폴링해 데이터 채움(실패해도 레코드는 생성됨)
    try:
        await poll_switch(row)
        row = await asyncio.to_thread(repo.get_switch, row["id"])
    except Exception as exc:  # noqa: BLE001
        log.warning("신규 스위치 폴링 실패: %s", exc)
    return _switch_with_summary(row)


@app.get("/api/switches/{switch_id}")
async def api_get_switch(switch_id: int) -> dict[str, Any]:
    row = await asyncio.to_thread(repo.get_switch, switch_id)
    if not row:
        raise HTTPException(status_code=404, detail="스위치 없음")
    data = _switch_with_summary(row)
    data["ports"] = await asyncio.to_thread(repo.get_ports, switch_id)
    return data


@app.put("/api/switches/{switch_id}")
async def api_update_switch(switch_id: int, payload: SwitchUpdate) -> dict[str, Any]:
    existing = await asyncio.to_thread(repo.get_switch, switch_id)
    if not existing:
        raise HTTPException(status_code=404, detail="스위치 없음")
    row = await asyncio.to_thread(
        repo.update_switch, switch_id,
        payload.model_dump(exclude_unset=True),
    )
    return _switch_with_summary(row)


@app.delete("/api/switches/{switch_id}")
async def api_delete_switch(switch_id: int) -> dict[str, Any]:
    ok = await asyncio.to_thread(repo.delete_switch, switch_id)
    if not ok:
        raise HTTPException(status_code=404, detail="스위치 없음")
    return {"deleted": True, "id": switch_id}


@app.get("/api/switches/{switch_id}/ports")
async def api_switch_ports(switch_id: int) -> dict[str, Any]:
    row = await asyncio.to_thread(repo.get_switch, switch_id)
    if not row:
        raise HTTPException(status_code=404, detail="스위치 없음")
    ports = await asyncio.to_thread(repo.get_ports, switch_id)
    return {"switch_id": switch_id, "ports": ports,
            "summary": summarize_port_rows(ports)}


@app.get("/api/switches/{switch_id}/samples")
async def api_switch_samples(switch_id: int, limit: int = 200) -> dict[str, Any]:
    row = await asyncio.to_thread(repo.get_switch, switch_id)
    if not row:
        raise HTTPException(status_code=404, detail="스위치 없음")
    samples = await asyncio.to_thread(repo.get_samples, switch_id, limit)
    return {"switch_id": switch_id, "samples": samples}


@app.post("/api/switches/{switch_id}/poll")
async def api_poll_switch(switch_id: int) -> dict[str, Any]:
    row = await asyncio.to_thread(repo.get_switch, switch_id)
    if not row:
        raise HTTPException(status_code=404, detail="스위치 없음")
    return await poll_switch(row)


@app.post("/api/poll")
async def api_poll_all() -> dict[str, Any]:
    results = await poll_all()
    return {"polled": len(results), "results": results}


# ----------------------------------------------------------------- 정적/프론트

if (FRONTEND_DIR / "static").exists():
    app.mount(
        "/static",
        StaticFiles(directory=str(FRONTEND_DIR / "static")),
        name="static",
    )


@app.get("/")
async def index() -> Any:
    idx = FRONTEND_DIR / "index.html"
    if idx.exists():
        return FileResponse(str(idx))
    return JSONResponse(
        {"app": "san_sw", "version": version_mod.get_version(),
         "note": "프론트엔드가 없습니다. /docs 에서 API를 확인하세요."}
    )


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "version": version_mod.get_version()}
