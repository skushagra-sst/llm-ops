from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.models.plan import Plan
from src.models.tenant import Tenant
from src.services.budget import BudgetGate
from src.services.db import Database
from src.services.tenant import TenantManager

OCTOBER = datetime(2026, 10, 15, tzinfo=timezone.utc)
NOVEMBER = datetime(2026, 11, 1, tzinfo=timezone.utc)

BASE_PLAN = Plan(
    id="test",
    name="Test",
    monthly_budget_usd=Decimal("0.10"),
    soft_budget_usd=Decimal("0.08"),
    request_reserve_usd=Decimal("0.02"),
    requests_per_minute=1000,
    monthly_token_budget=100_000,
    request_reserve_tokens=100,
)


@pytest.fixture
def db():
    database = Database()
    yield database
    database._conn.close()


@pytest.fixture
def tenants(db):
    manager = TenantManager(db)
    for name in ("alpha", "beta"):
        manager.add_tenant(Tenant(name, name, plan_id=BASE_PLAN.id))
    return manager


@pytest.fixture
def make_gate(db):
    """Build a BudgetGate on the shared database with plan fields overridden."""
    def build(now=OCTOBER, **overrides):
        plan = replace(BASE_PLAN, **overrides)
        return BudgetGate({plan.id: plan}, now=now, database=db), plan
    return build
