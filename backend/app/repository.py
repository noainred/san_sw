"""DB 접근 계층(스위치/포트/샘플 CRUD).

동기 함수다. 비동기 호출부에서는 asyncio.to_thread로 감싸 사용한다.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from .config import SAMPLE_RETENTION
from .db import get_conn, lock
from .models import PortInfo, SwitchSnapshot

# ---------------------------------------------------------------- switches


def list_switches() -> list[dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM switches ORDER BY region, dc, name, ip"
    ).fetchall()
    return [dict(r) for r in rows]


def get_switch(switch_id: int) -> dict[str, Any] | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM switches WHERE id = ?", (switch_id,)
    ).fetchone()
    return dict(row) if row else None


def create_switch(data: dict[str, Any]) -> dict[str, Any]:
    conn = get_conn()
    with lock():
        cur = conn.execute(
            """
            INSERT INTO switches (name, ip, dc, region, method, username,
                                  password, verify_tls)
            VALUES (:name, :ip, :dc, :region, :method, :username,
                    :password, :verify_tls)
            """,
            {
                "name": data.get("name"),
                "ip": data["ip"],
                "dc": data.get("dc", "default"),
                "region": data.get("region", "global"),
                "method": data.get("method", "fos_rest"),
                "username": data.get("username"),
                "password": data.get("password"),
                "verify_tls": 1 if data.get("verify_tls") else 0,
            },
        )
        conn.commit()
        new_id = cur.lastrowid
    return get_switch(new_id)  # type: ignore[return-value]


def update_switch(switch_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
    allowed = {
        "name", "ip", "dc", "region", "method",
        "username", "password", "verify_tls",
    }
    fields = {k: v for k, v in data.items() if k in allowed and v is not None}
    if not fields:
        return get_switch(switch_id)
    if "verify_tls" in fields:
        fields["verify_tls"] = 1 if fields["verify_tls"] else 0
    conn = get_conn()
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    fields["id"] = switch_id
    with lock():
        conn.execute(f"UPDATE switches SET {sets} WHERE id = :id", fields)
        conn.commit()
    return get_switch(switch_id)


def delete_switch(switch_id: int) -> bool:
    conn = get_conn()
    with lock():
        cur = conn.execute("DELETE FROM switches WHERE id = ?", (switch_id,))
        conn.commit()
    return cur.rowcount > 0


def set_switch_status(
    switch_id: int,
    status: str,
    *,
    model: str | None = None,
    fos_version: str | None = None,
    name: str | None = None,
    last_error: str | None = None,
) -> None:
    conn = get_conn()
    with lock():
        conn.execute(
            """
            UPDATE switches
               SET status = ?,
                   model = COALESCE(?, model),
                   fos_version = COALESCE(?, fos_version),
                   name = COALESCE(?, name),
                   last_error = ?,
                   last_polled = datetime('now')
             WHERE id = ?
            """,
            (status, model, fos_version, name, last_error, switch_id),
        )
        conn.commit()


# ------------------------------------------------------------------- ports


def get_ports(switch_id: int) -> list[dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM ports WHERE switch_id = ? ORDER BY port_index, name",
        (switch_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def replace_ports(switch_id: int, ports: list[PortInfo]) -> None:
    """폴링 결과로 해당 스위치의 포트 목록을 통째로 갱신한다."""
    conn = get_conn()
    with lock():
        conn.execute("DELETE FROM ports WHERE switch_id = ?", (switch_id,))
        conn.executemany(
            """
            INSERT INTO ports (switch_id, name, port_index, enabled,
                operational_status, speed_gbps, max_speed_gbps, port_type,
                wwn, neighbor_wwn, tx_util_pct, rx_util_pct, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            [
                (
                    switch_id, p.name, p.port_index, 1 if p.enabled else 0,
                    p.operational_status, p.speed_gbps, p.max_speed_gbps,
                    p.port_type, p.wwn, p.neighbor_wwn,
                    p.tx_util_pct, p.rx_util_pct,
                )
                for p in ports
            ],
        )
        conn.commit()


# ----------------------------------------------------------------- samples


def add_sample(switch_id: int, summary: dict[str, Any]) -> None:
    conn = get_conn()
    with lock():
        conn.execute(
            """
            INSERT INTO samples (switch_id, total_ports, used_ports,
                free_ports, error_ports, occupancy_pct, avg_util_pct)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                switch_id,
                summary["total_ports"],
                summary["used_ports"],
                summary["free_ports"],
                summary["error_ports"],
                summary["occupancy_pct"],
                summary.get("avg_util_pct"),
            ),
        )
        # 보관 개수 초과분 정리(소규모: 스위치별 최근 N개만 유지)
        conn.execute(
            """
            DELETE FROM samples
             WHERE switch_id = ?
               AND id NOT IN (
                   SELECT id FROM samples WHERE switch_id = ?
                   ORDER BY id DESC LIMIT ?
               )
            """,
            (switch_id, switch_id, SAMPLE_RETENTION),
        )
        conn.commit()


def get_samples(switch_id: int, limit: int = 200) -> list[dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM samples WHERE switch_id = ? ORDER BY id DESC LIMIT ?",
        (switch_id, limit),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


def count_switches() -> int:
    conn = get_conn()
    return conn.execute("SELECT COUNT(*) AS c FROM switches").fetchone()["c"]
