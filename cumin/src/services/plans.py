from decimal import Decimal

from src.models.plan import PLANS, Plan
from src.services.db import Database


class PlanExists(Exception):
    pass


class PlanInUse(Exception):
    pass


class PlanStore:
    """Plans kept in SQLite. Seeded with the built-in plans the first time the table is empty."""

    def __init__(self, database: Database | None = None) -> None:
        self._db = database or Database()
        if not self._db.read("SELECT id FROM plans LIMIT 1"):
            for plan in PLANS.values():
                self._insert(plan)

    def list_plans(self) -> list[Plan]:
        rows = self._db.read("SELECT * FROM plans ORDER BY CAST(monthly_budget_usd AS REAL), name")
        return [_plan(row) for row in rows]

    def get(self, plan_id: str) -> Plan | None:
        rows = self._db.read("SELECT * FROM plans WHERE id = ?", (plan_id,))
        return _plan(rows[0]) if rows else None

    def __getitem__(self, plan_id: str) -> Plan:
        plan = self.get(plan_id)
        if plan is None:
            raise KeyError(plan_id)
        return plan

    def __contains__(self, plan_id: object) -> bool:
        return isinstance(plan_id, str) and self.get(plan_id) is not None

    def tenant_counts(self) -> dict[str, int]:
        rows = self._db.read("SELECT plan_id, COUNT(*) AS n FROM tenants GROUP BY plan_id")
        return {row["plan_id"]: row["n"] for row in rows}

    def create(self, plan: Plan) -> Plan:
        if plan.id in self:
            raise PlanExists(plan.id)
        self._insert(plan)
        return self[plan.id]

    def update(self, plan: Plan) -> Plan:
        self[plan.id]
        self._db.write(
            """
            UPDATE plans SET name = ?, monthly_budget_usd = ?, soft_budget_usd = ?, request_reserve_usd = ?,
                requests_per_minute = ?, monthly_token_budget = ?, request_reserve_tokens = ?
            WHERE id = ?
            """,
            (*_values(plan)[1:], plan.id),
        )
        return self[plan.id]

    def delete(self, plan_id: str) -> None:
        self[plan_id]
        if self.tenant_counts().get(plan_id):
            raise PlanInUse(plan_id)
        self._db.write("DELETE FROM plans WHERE id = ?", (plan_id,))

    def _insert(self, plan: Plan) -> None:
        self._db.write(
            """
            INSERT INTO plans (
                id, name, monthly_budget_usd, soft_budget_usd, request_reserve_usd,
                requests_per_minute, monthly_token_budget, request_reserve_tokens
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            _values(plan),
        )


def _values(plan: Plan) -> tuple:
    return (
        plan.id,
        plan.name,
        str(plan.monthly_budget_usd),
        str(plan.soft_budget_usd),
        str(plan.request_reserve_usd),
        plan.requests_per_minute,
        plan.monthly_token_budget,
        plan.request_reserve_tokens,
    )


def _plan(row) -> Plan:
    return Plan(
        id=row["id"],
        name=row["name"],
        monthly_budget_usd=Decimal(row["monthly_budget_usd"]),
        soft_budget_usd=Decimal(row["soft_budget_usd"]),
        request_reserve_usd=Decimal(row["request_reserve_usd"]),
        requests_per_minute=row["requests_per_minute"],
        monthly_token_budget=row["monthly_token_budget"],
        request_reserve_tokens=row["request_reserve_tokens"],
    )
