"""SQLite 연결 및 스키마.

소규모 운영을 가정한다. 단일 연결을 공유하고(check_same_thread=False)
쓰기는 락으로 직렬화한다. 폴러/요청 모두 동기 호출이며, 비동기 컨텍스트에서
호출 시에는 repository 헬퍼를 통해 asyncio.to_thread로 감싼다.
"""
from __future__ import annotations

import sqlite3
import threading

from .config import DB_PATH

_conn: sqlite3.Connection | None = None
_lock = threading.RLock()


SCHEMA = """
CREATE TABLE IF NOT EXISTS switches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT,
    ip           TEXT NOT NULL UNIQUE,
    dc           TEXT NOT NULL DEFAULT 'default',
    region       TEXT NOT NULL DEFAULT 'global',
    method       TEXT NOT NULL DEFAULT 'fos_rest',   -- fos_rest | demo
    username     TEXT,
    password     TEXT,
    verify_tls   INTEGER NOT NULL DEFAULT 0,
    model        TEXT,
    fos_version  TEXT,
    status       TEXT NOT NULL DEFAULT 'unknown',     -- online|unreachable|unknown
    last_error   TEXT,
    last_polled  TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ports (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    switch_id           INTEGER NOT NULL REFERENCES switches(id) ON DELETE CASCADE,
    name                TEXT NOT NULL,
    port_index          INTEGER,
    enabled             INTEGER NOT NULL DEFAULT 1,
    operational_status  TEXT,
    speed_gbps          REAL,
    max_speed_gbps      REAL,
    port_type           TEXT,
    wwn                 TEXT,
    neighbor_wwn        TEXT,
    tx_util_pct         REAL,
    rx_util_pct         REAL,
    updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(switch_id, name)
);

CREATE TABLE IF NOT EXISTS samples (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    switch_id     INTEGER NOT NULL REFERENCES switches(id) ON DELETE CASCADE,
    ts            TEXT NOT NULL DEFAULT (datetime('now')),
    total_ports   INTEGER NOT NULL DEFAULT 0,
    used_ports    INTEGER NOT NULL DEFAULT 0,
    free_ports    INTEGER NOT NULL DEFAULT 0,
    error_ports   INTEGER NOT NULL DEFAULT 0,
    occupancy_pct REAL NOT NULL DEFAULT 0,
    avg_util_pct  REAL
);

-- 포트별 직전 octet 카운터(대역폭 사용율 델타 계산용). 포트당 1행 upsert.
CREATE TABLE IF NOT EXISTS port_counters (
    switch_id  INTEGER NOT NULL REFERENCES switches(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    tx_octets  INTEGER,
    rx_octets  INTEGER,
    ts         REAL NOT NULL,            -- unix epoch(초)
    PRIMARY KEY (switch_id, name)
);

-- 사용자/RBAC
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'viewer',   -- admin|operator|viewer
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 감사 로그(변경 이력)
CREATE TABLE IF NOT EXISTS audit_log (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       TEXT NOT NULL DEFAULT (datetime('now')),
    username TEXT,
    action   TEXT NOT NULL,
    target   TEXT,
    detail   TEXT
);

-- 알림 규칙
CREATE TABLE IF NOT EXISTS alert_rules (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    metric     TEXT NOT NULL,        -- occupancy_pct|error_ports|crc_errors|
                                     -- sfp_rx_power_dbm|switch_unreachable
    comparator TEXT NOT NULL DEFAULT '>',  -- > | < | >= | <= | ==
    threshold  REAL NOT NULL DEFAULT 0,
    severity   TEXT NOT NULL DEFAULT 'warning',  -- info|warning|critical
    enabled    INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 발생 알림 이력
CREATE TABLE IF NOT EXISTS alerts (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT NOT NULL DEFAULT (datetime('now')),
    rule_id   INTEGER,
    switch_id INTEGER,
    severity  TEXT NOT NULL DEFAULT 'warning',
    message   TEXT NOT NULL,
    value     REAL,
    resolved  INTEGER NOT NULL DEFAULT 0
);

-- ISL(스위치 간 E_Port 연결) 토폴로지
CREATE TABLE IF NOT EXISTS isl_links (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    switch_id       INTEGER NOT NULL REFERENCES switches(id) ON DELETE CASCADE,
    local_port      TEXT,
    remote_wwn      TEXT,
    remote_switch_id INTEGER,
    speed_gbps      REAL,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 구성 백업
CREATE TABLE IF NOT EXISTS config_backups (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    switch_id INTEGER NOT NULL REFERENCES switches(id) ON DELETE CASCADE,
    ts        TEXT NOT NULL DEFAULT (datetime('now')),
    filename  TEXT,
    size      INTEGER,
    content   TEXT
);

CREATE INDEX IF NOT EXISTS idx_ports_switch ON ports(switch_id);
CREATE INDEX IF NOT EXISTS idx_samples_switch_ts ON samples(switch_id, ts);
CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts(ts);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts);
CREATE INDEX IF NOT EXISTS idx_isl_switch ON isl_links(switch_id);
"""

# 기존 DB(이전 버전)에 새 컬럼을 추가하기 위한 마이그레이션 정의.
_COLUMN_MIGRATIONS = {
    "ports": {
        "crc_errors": "INTEGER",
        "enc_out_errors": "INTEGER",
        "link_failures": "INTEGER",
        "loss_of_sync": "INTEGER",
        "sfp_temp_c": "REAL",
        "sfp_voltage_v": "REAL",
        "sfp_tx_power_dbm": "REAL",
        "sfp_rx_power_dbm": "REAL",
    },
    "switches": {
        "lat": "REAL",
        "lon": "REAL",
    },
}


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        with _lock:
            if _conn is None:
                conn = sqlite3.connect(
                    str(DB_PATH), check_same_thread=False, timeout=30
                )
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA foreign_keys=ON;")
                _conn = conn
    return _conn


def _migrate_columns(conn: sqlite3.Connection) -> None:
    """기존 테이블에 누락된 컬럼을 ALTER로 추가(데이터 보존)."""
    for table, columns in _COLUMN_MIGRATIONS.items():
        existing = {
            r["name"] for r in conn.execute(f"PRAGMA table_info({table})")
        }
        for col, decl in columns.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


def init_db() -> None:
    conn = get_conn()
    with _lock:
        conn.executescript(SCHEMA)
        _migrate_columns(conn)
        conn.commit()


def lock() -> threading.RLock:
    return _lock
