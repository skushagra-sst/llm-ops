import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    is_active INTEGER NOT NULL,
    plan_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS api_keys (
    prefix TEXT PRIMARY KEY,
    secret_hash TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS ledger (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    plan_id TEXT NOT NULL,
    month TEXT NOT NULL,
    reserved_usd TEXT NOT NULL,
    reserved_tokens INTEGER NOT NULL,
    status TEXT NOT NULL,
    actual_usd TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cached_input_tokens INTEGER
);

CREATE TABLE IF NOT EXISTS idempotency (
    tenant_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    text TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cached_input_tokens INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT,
    key_prefix TEXT NOT NULL,
    model TEXT NOT NULL,
    outcome TEXT NOT NULL,
    cost_usd TEXT,
    request_text TEXT NOT NULL,
    response_text TEXT,
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS audit_tenant ON audit (tenant_id, id);

CREATE TABLE IF NOT EXISTS plans (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    monthly_budget_usd TEXT NOT NULL,
    soft_budget_usd TEXT NOT NULL,
    request_reserve_usd TEXT NOT NULL,
    requests_per_minute INTEGER NOT NULL,
    monthly_token_budget INTEGER NOT NULL,
    request_reserve_tokens INTEGER NOT NULL
);
"""

# Columns added after the first release. CREATE TABLE IF NOT EXISTS leaves older files without them.
_ADDED_COLUMNS = (
    ("api_keys", "created_at", "TEXT"),
    ("audit", "created_at", "TEXT"),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Database:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)
            for table, column, kind in _ADDED_COLUMNS:
                columns = {row["name"] for row in self._conn.execute(f"PRAGMA table_info({table})")}
                if column not in columns:
                    self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")

    @contextmanager
    def transaction(self):
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
            else:
                self._conn.execute("COMMIT")

    def read(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def write(self, sql: str, params: tuple = ()) -> None:
        with self._lock:
            self._conn.execute(sql, params)
