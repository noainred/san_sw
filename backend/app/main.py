"""FastAPI 진입점.

- /api/* : REST API
- /      : 웹 대시보드(정적 파일)
백그라운드 폴러를 lifespan으로 띄우고, 최초 기동 시(설정에 따라) 데모 스위치를
시드한 뒤 즉시 1회 폴링한다.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from . import alerts as alerts_mod
from . import auth
from . import firmware as firmware_mod
from . import metrics as metrics_mod
from . import reports as reports_mod
from . import repository as repo
from . import topology as topology_mod
from . import upgrade as upgrade_mod
from . import version as version_mod
from .auth import current_user, require_role
from .config import AUTH_ENABLED, FRONTEND_DIR, POLL_INTERVAL, SEED_DEMO
from .db import init_db
from .poller import poll_all, poll_switch, poller_loop
from .schemas import (
    AlertRuleCreate,
    LoginRequest,
    SwitchCreate,
    SwitchUpdate,
    UserCreate,
)
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


# 데모 스위치 지오좌표(지도용)
_DEMO_GEO = {
    "192.0.2.11": (37.5665, 126.9780), "192.0.2.12": (37.5665, 126.9780),
    "192.0.2.21": (35.6762, 139.6503), "198.51.100.11": (50.1109, 8.6821),
    "198.51.100.12": (50.1109, 8.6821), "203.0.113.11": (38.9072, -77.0369),
}


def _seed_demo() -> None:
    if repo.count_switches() > 0:
        return
    log.info("DB가 비어 있어 데모 스위치 %d대 시드(method=demo).",
             len(_DEMO_SWITCHES))
    for s in _DEMO_SWITCHES:
        row = repo.create_switch({**s, "method": "demo"})
        lat_lon = _DEMO_GEO.get(s["ip"])
        if lat_lon:
            repo.set_switch_geo(row["id"], lat_lon[0], lat_lon[1])
    repo.add_audit("system", "seed_demo",
                   detail=f"{len(_DEMO_SWITCHES)}대 데모 스위치 생성")


def _rebuild_demo_topology() -> None:
    """데모 스위치들에 대해 리전별 ISL 링을 만든다."""
    switches = repo.list_switches()
    if not any(s.get("method") == "demo" for s in switches):
        return
    links = topology_mod.build_demo_isl(switches)
    for sw in switches:
        repo.replace_isl(sw["id"], links.get(sw["id"], []))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    await asyncio.to_thread(auth.bootstrap_admin)
    await asyncio.to_thread(alerts_mod.seed_default_rules)
    await asyncio.to_thread(
        repo.add_audit, "system", "startup",
        detail=f"san_sw {version_mod.get_version()} (auth={'on' if AUTH_ENABLED else 'off'})")
    if SEED_DEMO:
        await asyncio.to_thread(_seed_demo)
        await asyncio.to_thread(_rebuild_demo_topology)
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
async def api_upgrade_apply(
    user: dict = Depends(require_role("admin"))
) -> dict[str, Any]:
    await asyncio.to_thread(repo.add_audit, user["username"], "upgrade_apply")
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


@app.get("/api/summary/history")
async def api_summary_history(limit: int = 120) -> dict[str, Any]:
    """전역 포트 사용율 추이(분 단위 버킷)."""
    history = await asyncio.to_thread(repo.get_global_history, limit)
    return {"history": history}


# --------------------------------------------------------------------- 스위치

@app.get("/api/switches")
async def api_list_switches() -> list[dict[str, Any]]:
    switches = await asyncio.to_thread(repo.list_switches)
    return [_switch_with_summary(s) for s in switches]


@app.post("/api/switches", status_code=201)
async def api_create_switch(
    payload: SwitchCreate, user: dict = Depends(require_role("operator"))
) -> dict[str, Any]:
    try:
        row = await asyncio.to_thread(repo.create_switch, payload.model_dump())
    except Exception as exc:  # UNIQUE 위반 등
        raise HTTPException(status_code=400, detail=f"생성 실패: {exc!s}")
    await asyncio.to_thread(
        repo.add_audit, user["username"], "create_switch",
        payload.ip, payload.name)
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
async def api_update_switch(
    switch_id: int, payload: SwitchUpdate,
    user: dict = Depends(require_role("operator")),
) -> dict[str, Any]:
    existing = await asyncio.to_thread(repo.get_switch, switch_id)
    if not existing:
        raise HTTPException(status_code=404, detail="스위치 없음")
    data = payload.model_dump(exclude_unset=True)
    lat, lon = data.pop("lat", None), data.pop("lon", None)
    row = await asyncio.to_thread(repo.update_switch, switch_id, data)
    if lat is not None or lon is not None:
        await asyncio.to_thread(repo.set_switch_geo, switch_id, lat, lon)
        row = await asyncio.to_thread(repo.get_switch, switch_id)
    await asyncio.to_thread(
        repo.add_audit, user["username"], "update_switch", existing["ip"], None)
    return _switch_with_summary(row)


@app.delete("/api/switches/{switch_id}")
async def api_delete_switch(
    switch_id: int, user: dict = Depends(require_role("operator"))
) -> dict[str, Any]:
    existing = await asyncio.to_thread(repo.get_switch, switch_id)
    ok = await asyncio.to_thread(repo.delete_switch, switch_id)
    if not ok:
        raise HTTPException(status_code=404, detail="스위치 없음")
    await asyncio.to_thread(
        repo.add_audit, user["username"], "delete_switch",
        existing["ip"] if existing else str(switch_id), None)
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


# --------------------------------------------------------------------- 인증

@app.get("/api/auth/config")
async def api_auth_config() -> dict[str, Any]:
    return {"auth_enabled": AUTH_ENABLED}


@app.post("/api/auth/login")
async def api_login(payload: LoginRequest) -> dict[str, Any]:
    if not AUTH_ENABLED:
        return {"token": auth.make_token("(auth-disabled)", "admin"),
                "username": "(auth-disabled)", "role": "admin",
                "note": "인증 비활성 상태"}
    user = await asyncio.to_thread(
        auth.authenticate, payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="계정 또는 비밀번호 오류")
    await asyncio.to_thread(repo.add_audit, user["username"], "login")
    return {"token": auth.make_token(user["username"], user["role"]),
            "username": user["username"], "role": user["role"]}


@app.get("/api/auth/me")
async def api_me(user: dict = Depends(current_user)) -> dict[str, Any]:
    return user


@app.get("/api/users")
async def api_list_users(user: dict = Depends(require_role("admin"))) -> list:
    return await asyncio.to_thread(repo.list_users)


@app.post("/api/users", status_code=201)
async def api_create_user(
    payload: UserCreate, user: dict = Depends(require_role("admin"))
) -> dict[str, Any]:
    if payload.role not in ("admin", "operator", "viewer"):
        raise HTTPException(status_code=400, detail="role 값 오류")
    try:
        created = await asyncio.to_thread(
            repo.create_user, payload.username,
            auth.hash_password(payload.password), payload.role)
    except Exception as exc:  # UNIQUE 등
        raise HTTPException(status_code=400, detail=f"생성 실패: {exc!s}")
    await asyncio.to_thread(
        repo.add_audit, user["username"], "create_user", payload.username,
        payload.role)
    return {"username": created["username"], "role": created["role"]}


@app.delete("/api/users/{username}")
async def api_delete_user(
    username: str, user: dict = Depends(require_role("admin"))
) -> dict[str, Any]:
    ok = await asyncio.to_thread(repo.delete_user, username)
    if not ok:
        raise HTTPException(status_code=404, detail="사용자 없음")
    await asyncio.to_thread(repo.add_audit, user["username"], "delete_user",
                            username)
    return {"deleted": True, "username": username}


# --------------------------------------------------------------------- 알림

@app.get("/api/alerts")
async def api_alerts(limit: int = 200) -> dict[str, Any]:
    return {"alerts": await asyncio.to_thread(repo.list_alerts, limit)}


@app.get("/api/alert-rules")
async def api_alert_rules() -> dict[str, Any]:
    return {"rules": await asyncio.to_thread(repo.list_alert_rules)}


@app.post("/api/alert-rules", status_code=201)
async def api_create_alert_rule(
    payload: AlertRuleCreate, user: dict = Depends(require_role("operator"))
) -> dict[str, Any]:
    rule = await asyncio.to_thread(repo.create_alert_rule, payload.model_dump())
    await asyncio.to_thread(repo.add_audit, user["username"],
                            "create_alert_rule", payload.name)
    return rule


@app.delete("/api/alert-rules/{rule_id}")
async def api_delete_alert_rule(
    rule_id: int, user: dict = Depends(require_role("operator"))
) -> dict[str, Any]:
    ok = await asyncio.to_thread(repo.delete_alert_rule, rule_id)
    if not ok:
        raise HTTPException(status_code=404, detail="규칙 없음")
    await asyncio.to_thread(repo.add_audit, user["username"],
                            "delete_alert_rule", str(rule_id))
    return {"deleted": True, "id": rule_id}


@app.post("/api/alerts/evaluate")
async def api_eval_alerts(
    user: dict = Depends(require_role("operator"))
) -> dict[str, Any]:
    fired = await alerts_mod.evaluate_and_notify()
    return {"fired": fired, "count": len(fired)}


# ------------------------------------------------------------- 펌웨어/토폴로지

@app.get("/api/firmware")
async def api_firmware() -> dict[str, Any]:
    switches = await asyncio.to_thread(repo.list_switches)
    return firmware_mod.inventory(switches)


@app.get("/api/topology")
async def api_topology() -> dict[str, Any]:
    switches = await asyncio.to_thread(repo.list_switches)
    isl = await asyncio.to_thread(repo.list_isl)
    return topology_mod.graph(switches, isl)


# ------------------------------------------------------------------ 리포트

@app.get("/api/reports/capacity")
async def api_report_capacity() -> dict[str, Any]:
    return await asyncio.to_thread(reports_mod.capacity_report)


@app.get("/api/reports/capacity.csv")
async def api_report_capacity_csv() -> Response:
    csv_text = await asyncio.to_thread(reports_mod.capacity_csv)
    return PlainTextResponse(
        csv_text, media_type="text/csv",
        headers={"Content-Disposition":
                 "attachment; filename=san_sw_capacity.csv"})


# --------------------------------------------------------------- 감사/백업

@app.get("/api/audit")
async def api_audit(limit: int = 200) -> dict[str, Any]:
    return {"audit": await asyncio.to_thread(repo.list_audit, limit)}


@app.get("/api/switches/{switch_id}/backups")
async def api_list_backups(switch_id: int) -> dict[str, Any]:
    return {"backups": await asyncio.to_thread(
        repo.list_config_backups, switch_id)}


@app.post("/api/switches/{switch_id}/backup", status_code=201)
async def api_backup_switch(
    switch_id: int, user: dict = Depends(require_role("operator"))
) -> dict[str, Any]:
    row = await asyncio.to_thread(repo.get_switch, switch_id)
    if not row:
        raise HTTPException(status_code=404, detail="스위치 없음")
    ports = await asyncio.to_thread(repo.get_ports, switch_id)
    # 실장비 configupload 대신, 현재 인벤토리 스냅샷을 백업으로 저장(데모/기록용).
    snapshot = json.dumps(
        {"switch": _public_switch(row), "ports": ports},
        ensure_ascii=False, indent=2)
    fname = f"{row.get('name') or row['ip']}-{int(time.time())}.json"
    backup = await asyncio.to_thread(
        repo.add_config_backup, switch_id, fname, snapshot)
    await asyncio.to_thread(repo.add_audit, user["username"],
                            "config_backup", fname)
    return backup


# ------------------------------------------------------------- Prometheus

@app.get("/metrics")
async def metrics() -> Response:
    text = await asyncio.to_thread(metrics_mod.render)
    return PlainTextResponse(text, media_type="text/plain; version=0.0.4")


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
