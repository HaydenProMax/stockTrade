from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from fund_signal.types import AssetSignal, FundAllocation


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
    source TEXT NOT NULL DEFAULT '',
    data_date TEXT NOT NULL DEFAULT '',
    drawdown REAL NOT NULL,
    daily_change REAL NOT NULL DEFAULT 0,
    days_since_peak INTEGER NOT NULL DEFAULT 0,
    duration_multiplier REAL NOT NULL DEFAULT 1,
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
    amount REAL NOT NULL DEFAULT 0,
    executed_amount REAL,
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
            self._ensure_column(connection, "signals", "source", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "signals", "data_date", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "signals", "daily_change", "REAL NOT NULL DEFAULT 0")
            self._ensure_column(connection, "signals", "days_since_peak", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(connection, "signals", "duration_multiplier", "REAL NOT NULL DEFAULT 1")
            self._ensure_column(connection, "allocations", "amount", "REAL NOT NULL DEFAULT 0")
            self._ensure_column(connection, "allocations", "executed_amount", "REAL")

    def start_run(self, run_date: str, mode: str) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO runs (run_date, mode, started_at, status)
                VALUES (?, ?, ?, ?)
                """,
                (run_date, mode, _now_text(), "running"),
            )
            return int(cursor.lastrowid)

    def finish_run(self, run_id: int, status: str, error_message: str | None = None) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE runs
                SET finished_at = ?, status = ?, error_message = ?
                WHERE id = ?
                """,
                (_now_text(), status, error_message, run_id),
            )

    def clear_run_outputs(self, run_date: str, mode: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM signals WHERE run_date = ? AND mode = ?",
                (run_date, mode),
            )
            connection.execute(
                "DELETE FROM allocations WHERE run_date = ? AND mode = ?",
                (run_date, mode),
            )

    def save_signals(self, run_date: str, mode: str, signals: list[AssetSignal]) -> None:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM signals WHERE run_date = ? AND mode = ?",
                (run_date, mode),
            )
            connection.executemany(
                """
                INSERT INTO signals (
                    run_date, mode, asset_group, source, data_date, drawdown,
                    daily_change, days_since_peak, duration_multiplier,
                    raw_units, final_units, trend_state, reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_date,
                        mode,
                        signal.asset_group,
                        signal.source,
                        signal.data_date.isoformat(),
                        signal.drawdown,
                        signal.daily_change,
                        signal.days_since_peak,
                        signal.duration_multiplier,
                        signal.raw_units,
                        signal.final_units,
                        signal.trend_state,
                        signal.reason,
                    )
                    for signal in signals
                ],
            )

    def save_allocations(self, run_date: str, mode: str, allocations: list[FundAllocation]) -> None:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM allocations WHERE run_date = ? AND mode = ?",
                (run_date, mode),
            )
            connection.executemany(
                """
                INSERT INTO allocations (
                    run_date, mode, asset_group, fund_code, fund_name,
                    units, amount, executed_amount, status, reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_date,
                        mode,
                        allocation.asset_group,
                        allocation.fund_code,
                        allocation.fund_name,
                        allocation.units,
                        allocation.amount,
                        allocation.executed_amount,
                        allocation.status,
                        allocation.reason,
                    )
                    for allocation in allocations
                ],
            )

    def monthly_spending(self, month_prefix: str) -> tuple[float, dict[str, float], dict[str, float]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT asset_group, fund_code, COALESCE(executed_amount, amount, 0)
                FROM allocations
                WHERE run_date LIKE ?
                  AND status LIKE 'assumed_executed%'
                """,
                (f"{month_prefix}-%",),
            ).fetchall()

        total = 0.0
        by_asset: dict[str, float] = {}
        by_fund: dict[str, float] = {}
        for asset_group, fund_code, amount in rows:
            value = float(amount or 0)
            total += value
            by_asset[asset_group] = by_asset.get(asset_group, 0.0) + value
            by_fund[fund_code] = by_fund.get(fund_code, 0.0) + value
        return total, by_asset, by_fund

    def notification_sent(self, run_date: str, mode: str, asset_group: str, signal_hash: str) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM notifications
                WHERE run_date = ?
                  AND mode = ?
                  AND asset_group = ?
                  AND signal_hash = ?
                  AND status = 'success'
                LIMIT 1
                """,
                (run_date, mode, asset_group, signal_hash),
            ).fetchone()
        return row is not None

    def save_notification(
        self,
        run_date: str,
        mode: str,
        asset_group: str,
        signal_hash: str,
        status: str,
        response_code: int | None = None,
        response_body: str | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO notifications (
                    run_date, mode, asset_group, signal_hash,
                    notified_at, status, response_code, response_body
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_date,
                    mode,
                    asset_group,
                    signal_hash,
                    _now_text(),
                    status,
                    response_code,
                    response_body,
                ),
            )

    @staticmethod
    def _ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")
