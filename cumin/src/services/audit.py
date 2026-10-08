import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from src.services.db import Database, utc_now

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_API_KEY = re.compile(r"\b[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{10,}\b")

BLOCKED = ("rate_limited", "budget_exceeded", "injection", "moderated", "error", "unauthenticated", "unsupported_model", "idempotency_conflict")

_KINDS = {
    "completed": ("outcome = 'completed'", ()),
    "blocked": (f"outcome IN ({', '.join('?' for _ in BLOCKED)})", BLOCKED),
    "replay": ("outcome = 'idempotent_replay'", ()),
    "admin": ("model = 'admin'", ()),
}


def redact(text: str) -> str:
    text = _EMAIL.sub("[email]", text)
    return _API_KEY.sub("[api-key]", text)


@dataclass(frozen=True)
class AuditEvent:
    tenant_id: str | None
    key_prefix: str
    model: str
    outcome: str
    cost_usd: Decimal | None
    request_text: str
    response_text: str | None
    id: int | None = None
    created_at: str | None = None
    latency_ms: float | None = None


@dataclass(frozen=True)
class LogFilter:
    kind: str | None = None
    key_prefix: str | None = None
    text: str | None = None
    since: date | None = None
    until: date | None = None


class AuditLog:
    def __init__(self, database: Database | None = None) -> None:
        self._db = database or Database()

    @property
    def events(self) -> list[AuditEvent]:
        return self.for_tenant(None)

    def for_tenant(self, tenant_id: str | None, limit: int = 50) -> list[AuditEvent]:
        if tenant_id is None:
            rows = self._db.read("SELECT * FROM audit ORDER BY id ASC")
        else:
            rows = self._db.read(
                "SELECT * FROM audit WHERE tenant_id = ? ORDER BY id DESC LIMIT ?",
                (tenant_id, limit),
            )
        return [_event(row) for row in rows]

    def search(
        self,
        tenant_id: str,
        log_filter: LogFilter,
        limit: int,
        offset: int = 0,
    ) -> tuple[int, list[AuditEvent]]:
        where, params = _where(tenant_id, log_filter)
        total = self._db.read(f"SELECT COUNT(*) AS n FROM audit WHERE {where}", params)[0]["n"]
        rows = self._db.read(
            f"SELECT * FROM audit WHERE {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        )
        return total, [_event(row) for row in rows]

    def daily(self, tenant_id: str | None, start: date, end: date) -> list[dict]:
        sql = "SELECT substr(created_at, 1, 10) AS day, outcome, cost_usd FROM audit WHERE created_at >= ? AND created_at < ?"
        params: tuple = (start.isoformat(), (end + timedelta(days=1)).isoformat())
        if tenant_id is not None:
            sql += " AND tenant_id = ?"
            params = (*params, tenant_id)
        spend: dict[str, Decimal] = defaultdict(Decimal)
        requests: dict[str, int] = defaultdict(int)
        blocked: dict[str, int] = defaultdict(int)
        for row in self._db.read(sql, params):
            if row["outcome"] == "completed":
                requests[row["day"]] += 1
                spend[row["day"]] += Decimal(row["cost_usd"] or "0")
            elif row["outcome"] in BLOCKED:
                blocked[row["day"]] += 1
        days = []
        current = start
        while current <= end:
            key = current.isoformat()
            days.append(
                {
                    "date": key,
                    "spend_usd": str(spend[key]),
                    "requests": requests[key],
                    "blocked": blocked[key],
                }
            )
            current += timedelta(days=1)
        return days

    def key_usage(self, tenant_id: str) -> dict[str, dict]:
        rows = self._db.read(
            """
            SELECT key_prefix, outcome, cost_usd, created_at FROM audit
            WHERE tenant_id = ? AND model != 'admin' AND key_prefix != ''
            """,
            (tenant_id,),
        )
        usage: dict[str, dict] = {}
        for row in rows:
            entry = usage.setdefault(
                row["key_prefix"],
                {"requests": 0, "spend_usd": Decimal(0), "last_used": None},
            )
            if row["outcome"] == "completed":
                entry["requests"] += 1
                entry["spend_usd"] += Decimal(row["cost_usd"] or "0")
            if row["created_at"] and (entry["last_used"] is None or row["created_at"] > entry["last_used"]):
                entry["last_used"] = row["created_at"]
        return usage

    def record(
        self,
        *,
        tenant_id: str | None,
        key_prefix: str,
        model: str,
        outcome: str,
        cost_usd: Decimal | None,
        request_text: str,
        response_text: str | None,
        latency_ms: float | None = None,
    ) -> None:
        self._db.write(
            """
            INSERT INTO audit (
                tenant_id, key_prefix, model, outcome, cost_usd, request_text, response_text, created_at, latency_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tenant_id,
                key_prefix,
                model,
                outcome,
                None if cost_usd is None else str(cost_usd),
                redact(request_text),
                None if response_text is None else redact(response_text),
                utc_now(),
                latency_ms,
            ),
        )


def _where(tenant_id: str, log_filter: LogFilter) -> tuple[str, tuple]:
    clauses = ["tenant_id = ?"]
    params: list = [tenant_id]
    if log_filter.kind:
        clause, kind_params = _KINDS[log_filter.kind]
        clauses.append(clause)
        params.extend(kind_params)
    if log_filter.key_prefix:
        clauses.append("key_prefix = ?")
        params.append(log_filter.key_prefix)
    if log_filter.text:
        pattern = "%" + log_filter.text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        clauses.append("(request_text LIKE ? ESCAPE '\\' OR response_text LIKE ? ESCAPE '\\')")
        params.extend([pattern, pattern])
    if log_filter.since:
        clauses.append("created_at >= ?")
        params.append(log_filter.since.isoformat())
    if log_filter.until:
        clauses.append("created_at < ?")
        params.append((log_filter.until + timedelta(days=1)).isoformat())
    return " AND ".join(clauses), tuple(params)


def _event(row) -> AuditEvent:
    cost = row["cost_usd"]
    return AuditEvent(
        tenant_id=row["tenant_id"],
        key_prefix=row["key_prefix"],
        model=row["model"],
        outcome=row["outcome"],
        cost_usd=None if cost is None else Decimal(cost),
        request_text=row["request_text"],
        response_text=row["response_text"],
        id=row["id"],
        created_at=row["created_at"],
        latency_ms=row["latency_ms"],
    )
