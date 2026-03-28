"""SQLite-backed persistent storage.

Provides durable storage using aiosqlite for async operations,
with synchronous wrappers for the Storage interface.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from npa.storage.base import (
    NotFoundError,
    Storage,
    StorageEvent,
    Transaction,
    TxnMode,
)


class DiskTransaction(Transaction):
    """Transaction backed by SQLite with deferred writes."""

    def __init__(self, conn: sqlite3.Connection, mode: TxnMode) -> None:
        self._conn = conn
        self._mode = mode
        self._events: list[StorageEvent] = []

    def read(self, path: list[str]) -> Any:
        key = "/" + "/".join(path) if path else "/"
        cursor = self._conn.execute(
            "SELECT value FROM data WHERE key = ? OR key LIKE ? ORDER BY key",
            (key, key + "/%"),
        )
        rows = cursor.fetchall()
        if not rows:
            # Try reading as a prefix (return sub-tree)
            if key == "/":
                cursor2 = self._conn.execute("SELECT key, value FROM data ORDER BY key")
                all_rows = cursor2.fetchall()
                if not all_rows:
                    return {}
                return _build_tree(all_rows)
            raise NotFoundError(f"Path not found: {key}")

        if len(rows) == 1 and rows[0][0] is not None:
            # exact match
            cursor_exact = self._conn.execute("SELECT value FROM data WHERE key = ?", (key,))
            exact = cursor_exact.fetchone()
            if exact:
                return json.loads(exact[0])

        # Prefix match — build subtree
        cursor3 = self._conn.execute(
            "SELECT key, value FROM data WHERE key = ? OR key LIKE ? ORDER BY key",
            (key, key + "/%"),
        )
        return _build_tree(cursor3.fetchall(), prefix=key)

    def write(self, op: str, path: list[str], value: Any = None) -> None:
        key = "/" + "/".join(path) if path else "/"
        if op in ("add", "replace"):
            self._conn.execute(
                "INSERT OR REPLACE INTO data (key, value) VALUES (?, ?)",
                (key, json.dumps(value)),
            )
        elif op == "remove":
            self._conn.execute("DELETE FROM data WHERE key = ? OR key LIKE ?", (key, key + "/%"))
        self._events.append(StorageEvent(op=op, path=list(path), value=value))

    def commit(self) -> list[StorageEvent]:
        self._conn.commit()
        return list(self._events)

    def abort(self) -> None:
        self._conn.rollback()
        self._events.clear()


class DiskStorage(Storage):
    """SQLite-backed persistent storage.

    Schema:
        data(key TEXT PRIMARY KEY, value TEXT)
        policies(id TEXT PRIMARY KEY, raw TEXT)
    """

    def __init__(self, db_path: str | Path = "npa_data.db") -> None:
        self._db_path = str(db_path)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS data (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS policies (
                id TEXT PRIMARY KEY,
                raw TEXT NOT NULL,
                created_at REAL DEFAULT (julianday('now')),
                updated_at REAL DEFAULT (julianday('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_data_key ON data(key);
        """)
        self._conn.commit()

    def read(self, path: list[str]) -> Any:
        with self._lock:
            txn = self.begin(TxnMode.READ)
            return txn.read(path)

    def begin(self, mode: TxnMode = TxnMode.READ) -> DiskTransaction:
        return DiskTransaction(self._conn, mode)

    def list_policies(self) -> dict[str, str]:
        with self._lock:
            cursor = self._conn.execute("SELECT id, raw FROM policies")
            return dict(cursor.fetchall())

    def upsert_policy(self, policy_id: str, raw: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO policies (id, raw, updated_at) VALUES (?, ?, julianday('now'))",
                (policy_id, raw),
            )
            self._conn.commit()

    def delete_policy(self, policy_id: str) -> None:
        with self._lock:
            cursor = self._conn.execute("DELETE FROM policies WHERE id = ?", (policy_id,))
            if cursor.rowcount == 0:
                raise NotFoundError(f"Policy not found: {policy_id}")
            self._conn.commit()

    def get_policy(self, policy_id: str) -> str:
        with self._lock:
            cursor = self._conn.execute("SELECT raw FROM policies WHERE id = ?", (policy_id,))
            row = cursor.fetchone()
            if not row:
                raise NotFoundError(f"Policy not found: {policy_id}")
            return row[0]

    def close(self) -> None:
        self._conn.close()


def _build_tree(rows: list[tuple[str, str]], prefix: str = "") -> Any:
    """Build a nested dict from flat key-value rows."""
    if len(rows) == 1:
        key, val = rows[0]
        if key == prefix or key == prefix + "/":
            return json.loads(val)

    result: dict = {}
    for key, val in rows:
        # Strip prefix
        rel = key[len(prefix):].lstrip("/")
        if not rel:
            return json.loads(val)
        parts = rel.split("/")
        current = result
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        current[parts[-1]] = json.loads(val)
    return result
