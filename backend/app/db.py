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

CREATE INDEX IF NOT EXISTS idx_ports_switch ON ports(switch_id);
CREATE INDEX IF NOT EXISTS idx_samples_switch_ts ON samples(switch_id, ts);
"""


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


def init_db() -> None:
    conn = get_conn()
    with _lock:
        conn.executescript(SCHEMA)
        conn.commit()


def lock() -> threading.RLock:
    return _lock
