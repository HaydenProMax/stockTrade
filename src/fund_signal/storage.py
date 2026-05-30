from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL,
    mode TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL,
    mode TEXT NOT NULL,
    asset_group TEXT NOT NULL,
    signal_hash TEXT NOT NULL,
    notified_at TEXT,
    status TEXT NOT NULL,
    response_code INTEGER,
    response_body TEXT,
    UNIQUE (run_date, mode, asset_group, signal_hash)
);

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL,
    mode TEXT NOT NULL,
    asset_group TEXT NOT NULL,
    drawdown REAL NOT NULL,
    raw_units REAL NOT NULL,
    final_units REAL NOT NULL,
    trend_state TEXT NOT NULL,
    reason TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS allocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL,
    mode TEXT NOT NULL,
    asset_group TEXT NOT NULL,
    fund_code TEXT NOT NULL,
    fund_name TEXT NOT NULL,
    units REAL NOT NULL,
    status TEXT NOT NULL,
    reason TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    fund_code TEXT NOT NULL,
    asset_group TEXT NOT NULL,
    suggested_u REAL NOT NULL,
    executed_u REAL,
    executed_amount REAL,
    nav REAL,
    status TEXT NOT NULL,
    notes TEXT
);
"""


class Storage:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def init_schema(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
