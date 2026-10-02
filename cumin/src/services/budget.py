from __future__ import annotations

import secrets
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING
from datetime import datetime, timezone
from decimal import Decimal

from src.models.ledger import LedgerEntry
from src.models.llm import Completion, LLM, Message, Usage
from src.models.plan import PLANS, Plan
from src.models.tenant import Tenant
from src.services.db import Database

if TYPE_CHECKING:
    from src.services.plans import PlanStore


class BudgetExceeded(Exception):
    pass


@dataclass(frozen=True)
class Settlement:
    spent_usd: Decimal
    spent_tokens: int
    warning: bool


@dataclass(frozen=True)
class BudgetDecision:
    completion: Completion
    spent_usd: Decimal
    warning: bool


@dataclass(frozen=True)
class MonthUsage:
    request_count: int
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    spent_usd: Decimal
    spent_tokens: int


class BudgetGate:
    def __init__(
        self,
        plans: Mapping[str, Plan] | PlanStore | None = None,
        now: datetime | None = None,
        database: Database | None = None,
    ) -> None:
        self._plans = PLANS if plans is None else plans
        self._now = now
        self._db = database or Database()
        self._lock = threading.Lock()

    def reserve(self, tenant: Tenant) -> str:
        plan = self._plan(tenant)
        with self._lock:
            with self._db.transaction() as conn:
                month = self._month()
                spent = _spent_usd(conn, tenant.id, month)
                tokens = _spent_tokens(conn, tenant.id, month)
                if spent + plan.request_reserve_usd > plan.monthly_budget_usd:
                    raise BudgetExceeded("monthly cost budget exceeded")
                if tokens + plan.request_reserve_tokens > plan.monthly_token_budget:
                    raise BudgetExceeded("monthly token budget exceeded")
                entry_id = secrets.token_hex(8)
                conn.execute(
                    """
                    INSERT INTO ledger (
                        id, tenant_id, plan_id, month, reserved_usd, reserved_tokens, status
                    ) VALUES (?, ?, ?, ?, ?, ?, 'open')
                    """,
                    (
                        entry_id,
                        tenant.id,
                        plan.id,
                        month,
                        str(plan.request_reserve_usd),
                        plan.request_reserve_tokens,
                    ),
                )
                return entry_id

    def settle(self, reservation_id: str, actual_usd: Decimal, usage: Usage) -> Settlement:
        if actual_usd < 0:
            raise ValueError("actual cost cannot be negative")
        with self._lock:
            with self._db.transaction() as conn:
                entry = _entry(conn, reservation_id)
                if entry.status != "open":
                    raise RuntimeError("reservation is not open")
                conn.execute(
                    """
                    UPDATE ledger
                    SET status = 'settled', actual_usd = ?, input_tokens = ?,
                        output_tokens = ?, cached_input_tokens = ?
                    WHERE id = ?
                    """,
                    (
                        str(actual_usd),
                        usage.input_tokens,
                        usage.output_tokens,
                        usage.cached_input_tokens,
                        reservation_id,
                    ),
                )
                spent = _spent_usd(conn, entry.tenant_id, entry.month)
                tokens = _spent_tokens(conn, entry.tenant_id, entry.month)
        # Read the plan after the transaction: a database-backed plan store takes the same lock.
        plan = self._plans.get(entry.plan_id)
        return Settlement(
            spent_usd=spent,
            spent_tokens=tokens,
            warning=plan is not None and spent >= plan.soft_budget_usd,
        )

    def release(self, reservation_id: str) -> None:
        with self._lock:
            with self._db.transaction() as conn:
                entry = _entry(conn, reservation_id)
                if entry.status == "released":
                    return
                if entry.status != "open":
                    raise RuntimeError("reservation is not open")
                conn.execute("UPDATE ledger SET status = 'released' WHERE id = ?", (reservation_id,))

    def spent_usd(self, tenant_id: str) -> Decimal:
        with self._lock:
            with self._db.transaction() as conn:
                return _spent_usd(conn, tenant_id, self._month())

    def spent_tokens(self, tenant_id: str) -> int:
        with self._lock:
            with self._db.transaction() as conn:
                return _spent_tokens(conn, tenant_id, self._month())

    def month_usage(self, tenant_id: str) -> MonthUsage:
        with self._lock:
            with self._db.transaction() as conn:
                month = self._month()
                rows = conn.execute(
                    """
                    SELECT actual_usd, input_tokens, output_tokens, cached_input_tokens
                    FROM ledger
                    WHERE tenant_id = ? AND month = ? AND status = 'settled'
                    """,
                    (tenant_id, month),
                ).fetchall()
        request_count = 0
        input_tokens = 0
        output_tokens = 0
        cached_input_tokens = 0
        spent = Decimal(0)
        for row in rows:
            request_count += 1
            spent += Decimal(row["actual_usd"] or "0")
            input_tokens += row["input_tokens"] or 0
            output_tokens += row["output_tokens"] or 0
            cached_input_tokens += row["cached_input_tokens"] or 0
        return MonthUsage(
            request_count=request_count,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_input_tokens,
            spent_usd=spent,
            spent_tokens=input_tokens + output_tokens,
        )

    def ledger(self, tenant_id: str, limit: int = 40) -> list[dict]:
        rows = self._db.read(
            """
            SELECT id, month, status, reserved_usd, reserved_tokens, actual_usd,
                   input_tokens, output_tokens, cached_input_tokens, plan_id
            FROM ledger WHERE tenant_id = ? ORDER BY rowid DESC LIMIT ?
            """,
            (tenant_id, limit),
        )
        return [dict(row) for row in rows]

    def plan_for(self, tenant: Tenant) -> Plan:
        return self._plan(tenant)

    def guarded_complete(
        self,
        tenant: Tenant,
        llm: LLM,
        messages: list[Message],
        model: str,
    ) -> BudgetDecision:
        reservation_id = self.reserve(tenant)
        try:
            completion = llm.complete(messages, model)
            actual_usd = llm.cost_usd(completion.model, completion.usage)
        except Exception:
            self.release(reservation_id)
            raise
        settled = self.settle(reservation_id, actual_usd, completion.usage)
        return BudgetDecision(
            completion=completion,
            spent_usd=settled.spent_usd,
            warning=settled.warning,
        )

    def _plan(self, tenant: Tenant) -> Plan:
        plan = self._plans.get(tenant.plan_id)
        if plan is None:
            raise KeyError(f"No plan {tenant.plan_id}")
        return plan

    def _month(self) -> str:
        current = self._now or datetime.now(timezone.utc)
        return current.strftime("%Y-%m")


def _entry(conn, reservation_id: str) -> LedgerEntry:
    row = conn.execute("SELECT * FROM ledger WHERE id = ?", (reservation_id,)).fetchone()
    if row is None:
        raise KeyError(reservation_id)
    usage = None
    if row["input_tokens"] is not None:
        usage = Usage(
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            cached_input_tokens=row["cached_input_tokens"],
        )
    actual = row["actual_usd"]
    return LedgerEntry(
        id=row["id"],
        tenant_id=row["tenant_id"],
        plan_id=row["plan_id"],
        month=row["month"],
        reserved_usd=Decimal(row["reserved_usd"]),
        reserved_tokens=row["reserved_tokens"],
        status=row["status"],
        actual_usd=None if actual is None else Decimal(actual),
        usage=usage,
    )


def _spent_usd(conn, tenant_id: str, month: str) -> Decimal:
    total = Decimal(0)
    rows = conn.execute(
        "SELECT status, reserved_usd, actual_usd FROM ledger WHERE tenant_id = ? AND month = ?",
        (tenant_id, month),
    ).fetchall()
    for row in rows:
        if row["status"] == "open":
            total += Decimal(row["reserved_usd"])
        elif row["status"] == "settled" and row["actual_usd"] is not None:
            total += Decimal(row["actual_usd"])
    return total


def _spent_tokens(conn, tenant_id: str, month: str) -> int:
    total = 0
    rows = conn.execute(
        """
        SELECT status, reserved_tokens, input_tokens, output_tokens
        FROM ledger WHERE tenant_id = ? AND month = ?
        """,
        (tenant_id, month),
    ).fetchall()
    for row in rows:
        if row["status"] == "open":
            total += row["reserved_tokens"]
        elif row["status"] == "settled":
            total += (row["input_tokens"] or 0) + (row["output_tokens"] or 0)
    return total
