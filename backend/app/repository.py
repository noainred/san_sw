"""DB 접근 계층(스위치/포트/샘플 CRUD).

동기 함수다. 비동기 호출부에서는 asyncio.to_thread로 감싸 사용한다.
"""
from __future__ import annotations

from typing import Any

from . import crypto
from .config import SAMPLE_RETENTION
from .db import get_conn, lock
from .models import PortInfo

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
                "password": crypto.encrypt(data.get("password")),
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
    if "password" in fields:
        fields["password"] = crypto.encrypt(fields["password"])
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
                wwn, neighbor_wwn, tx_util_pct, rx_util_pct,
                crc_errors, enc_out_errors, link_failures, loss_of_sync,
                sfp_temp_c, sfp_voltage_v, sfp_tx_power_dbm, sfp_rx_power_dbm,
                updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            [
                (
                    switch_id, p.name, p.port_index, 1 if p.enabled else 0,
                    p.operational_status, p.speed_gbps, p.max_speed_gbps,
                    p.port_type, p.wwn, p.neighbor_wwn,
                    p.tx_util_pct, p.rx_util_pct,
                    p.crc_errors, p.enc_out_errors, p.link_failures,
                    p.loss_of_sync, p.sfp_temp_c, p.sfp_voltage_v,
                    p.sfp_tx_power_dbm, p.sfp_rx_power_dbm,
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


# ------------------------------------------------------------ 비밀값 복호화

def decrypted_switch(row: dict[str, Any]) -> dict[str, Any]:
    """폴링 직전에 password를 평문으로 해석한 사본(로컬 암호화 또는 Vault).

    DB/응답에는 암호문 또는 vault 참조가 그대로 남는다.
    """
    from . import secrets  # 지연 import(순환 방지)

    out = dict(row)
    out["password"] = secrets.resolve_password(row.get("password"))
    return out


# ------------------------------------------------------------ 포트 카운터

def get_port_counters(switch_id: int) -> dict[str, dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT name, tx_octets, rx_octets, ts FROM port_counters "
        "WHERE switch_id = ?",
        (switch_id,),
    ).fetchall()
    return {
        r["name"]: {"tx_octets": r["tx_octets"], "rx_octets": r["rx_octets"],
                    "ts": r["ts"]}
        for r in rows
    }


def upsert_port_counters(
    switch_id: int, counters: list[tuple[str, int | None, int | None, float]]
) -> None:
    """counters: [(name, tx_octets, rx_octets, ts), ...]"""
    if not counters:
        return
    conn = get_conn()
    with lock():
        conn.executemany(
            """
            INSERT INTO port_counters (switch_id, name, tx_octets, rx_octets, ts)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(switch_id, name) DO UPDATE SET
                tx_octets = excluded.tx_octets,
                rx_octets = excluded.rx_octets,
                ts = excluded.ts
            """,
            [(switch_id, *c) for c in counters],
        )
        conn.commit()


# ------------------------------------------------------------ 전역 히스토리

def get_global_history(limit: int = 120) -> list[dict[str, Any]]:
    """모든 스위치 샘플을 분 단위로 묶어 전역 포트 사용율 추이를 만든다.

    한 분에 같은 스위치가 여러 번 폴링되면 '최신 1건'만 사용해(시점 스냅샷)
    절대값이 부풀려지지 않게 한다. 비율과 절대값 모두 정확.
    """
    conn = get_conn()
    rows = conn.execute(
        """
        WITH ranked AS (
            SELECT switch_id,
                   substr(ts, 1, 16) AS bucket,
                   used_ports, total_ports,
                   ROW_NUMBER() OVER (
                       PARTITION BY switch_id, substr(ts, 1, 16)
                       ORDER BY id DESC
                   ) AS rn
              FROM samples
        )
        SELECT bucket,
               SUM(used_ports)  AS used,
               SUM(total_ports) AS total
          FROM ranked
         WHERE rn = 1
         GROUP BY bucket
         ORDER BY bucket DESC
         LIMIT ?
        """,
        (limit,),
    ).fetchall()
    out = []
    for r in reversed(rows):
        total = r["total"] or 0
        used = r["used"] or 0
        out.append({
            "ts": r["bucket"],
            "used_ports": used,
            "total_ports": total,
            "occupancy_pct": round(used / total * 100, 1) if total else 0.0,
        })
    return out


# ----------------------------------------------------------------- 지오/지도

def set_switch_geo(switch_id: int, lat: float | None, lon: float | None) -> None:
    conn = get_conn()
    with lock():
        conn.execute(
            "UPDATE switches SET lat = ?, lon = ? WHERE id = ?",
            (lat, lon, switch_id),
        )
        conn.commit()


# --------------------------------------------------------------------- 사용자

def get_user(username: str) -> dict[str, Any] | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()
    return dict(row) if row else None


def list_users() -> list[dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, username, role, created_at FROM users ORDER BY username"
    ).fetchall()
    return [dict(r) for r in rows]


def create_user(username: str, password_hash: str, role: str) -> dict[str, Any]:
    conn = get_conn()
    with lock():
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, password_hash, role),
        )
        conn.commit()
    return get_user(username)  # type: ignore[return-value]


def delete_user(username: str) -> bool:
    conn = get_conn()
    with lock():
        cur = conn.execute("DELETE FROM users WHERE username = ?", (username,))
        conn.commit()
    return cur.rowcount > 0


def count_users() -> int:
    conn = get_conn()
    return conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]


# --------------------------------------------------------------------- 감사

def add_audit(username: str | None, action: str, target: str | None = None,
              detail: str | None = None) -> None:
    conn = get_conn()
    with lock():
        conn.execute(
            "INSERT INTO audit_log (username, action, target, detail) "
            "VALUES (?, ?, ?, ?)",
            (username, action, target, detail),
        )
        conn.commit()


def list_audit(limit: int = 200) -> list[dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


# ------------------------------------------------------------------ 알림 규칙

def list_alert_rules(enabled_only: bool = False) -> list[dict[str, Any]]:
    conn = get_conn()
    sql = "SELECT * FROM alert_rules"
    if enabled_only:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY id"
    return [dict(r) for r in conn.execute(sql).fetchall()]


def create_alert_rule(data: dict[str, Any]) -> dict[str, Any]:
    conn = get_conn()
    with lock():
        cur = conn.execute(
            """INSERT INTO alert_rules (name, metric, comparator, threshold,
               severity, enabled) VALUES (?, ?, ?, ?, ?, ?)""",
            (data["name"], data["metric"], data.get("comparator", ">"),
             float(data.get("threshold", 0)), data.get("severity", "warning"),
             1 if data.get("enabled", True) else 0),
        )
        conn.commit()
        rid = cur.lastrowid
    row = conn.execute("SELECT * FROM alert_rules WHERE id = ?", (rid,)).fetchone()
    return dict(row)


def delete_alert_rule(rule_id: int) -> bool:
    conn = get_conn()
    with lock():
        cur = conn.execute("DELETE FROM alert_rules WHERE id = ?", (rule_id,))
        conn.commit()
    return cur.rowcount > 0


def add_alert(rule_id: int | None, switch_id: int | None, severity: str,
              message: str, value: float | None) -> None:
    conn = get_conn()
    with lock():
        conn.execute(
            """INSERT INTO alerts (rule_id, switch_id, severity, message, value)
               VALUES (?, ?, ?, ?, ?)""",
            (rule_id, switch_id, severity, message, value),
        )
        conn.commit()


def list_alerts(limit: int = 200) -> list[dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def recent_alert_exists(rule_id: int, switch_id: int | None,
                        within_seconds: int) -> bool:
    """동일 규칙·스위치의 최근 알림이 있으면 True(중복 발생 억제)."""
    conn = get_conn()
    row = conn.execute(
        """SELECT 1 FROM alerts
            WHERE rule_id = ? AND IFNULL(switch_id, -1) = IFNULL(?, -1)
              AND ts >= datetime('now', ?)
            LIMIT 1""",
        (rule_id, switch_id, f"-{int(within_seconds)} seconds"),
    ).fetchone()
    return row is not None


# -------------------------------------------------------------------- 토폴로지

def replace_isl(switch_id: int, links: list[dict[str, Any]]) -> None:
    conn = get_conn()
    with lock():
        conn.execute("DELETE FROM isl_links WHERE switch_id = ?", (switch_id,))
        conn.executemany(
            """INSERT INTO isl_links (switch_id, local_port, remote_wwn,
               remote_switch_id, speed_gbps) VALUES (?, ?, ?, ?, ?)""",
            [(switch_id, l.get("local_port"), l.get("remote_wwn"),
              l.get("remote_switch_id"), l.get("speed_gbps")) for l in links],
        )
        conn.commit()


def list_isl() -> list[dict[str, Any]]:
    conn = get_conn()
    return [dict(r) for r in conn.execute("SELECT * FROM isl_links").fetchall()]


# ------------------------------------------------------------------ 구성 백업

def add_config_backup(switch_id: int, filename: str, content: str) -> dict[str, Any]:
    conn = get_conn()
    with lock():
        cur = conn.execute(
            """INSERT INTO config_backups (switch_id, filename, size, content)
               VALUES (?, ?, ?, ?)""",
            (switch_id, filename, len(content), content),
        )
        conn.commit()
        bid = cur.lastrowid
    row = conn.execute(
        "SELECT id, switch_id, ts, filename, size FROM config_backups "
        "WHERE id = ?", (bid,)
    ).fetchone()
    return dict(row)


def list_config_backups(switch_id: int | None = None) -> list[dict[str, Any]]:
    conn = get_conn()
    if switch_id is not None:
        rows = conn.execute(
            "SELECT id, switch_id, ts, filename, size FROM config_backups "
            "WHERE switch_id = ? ORDER BY id DESC", (switch_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, switch_id, ts, filename, size FROM config_backups "
            "ORDER BY id DESC LIMIT 200"
        ).fetchall()
    return [dict(r) for r in rows]
