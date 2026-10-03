"""Isolated, offline fixtures. Nothing connects to OpenAI, Redis or production data."""
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.models.llm import Message, Usage
from src.models.plan import Plan
from src.models.tenant import Tenant
from src.services.audit import AuditLog
from src.services.budget import BudgetGate
from src.services.db import Database
from src.services.fakellm_inference import FakeLLM
from src.services.idempotency import IdempotencyStore
from src.services.moderation import PatternModerator
from src.services.rate_limit import RateLimiter
from src.services.request import RequestHandler
from src.services.tenant import TenantManager

MESSAGES = [Message(role="user", content="Explain API quotas in one sentence.")]

class Fixture:
    def __init__(self, *, llm=None, **overrides):
        self.db = Database()
        self.plan = replace(Plan("eval", "Offline evaluation", Decimal("100"),
                                 Decimal("80"), Decimal("0.02"), 100000,
                                 100000000, 1000), **overrides)
        self.tenants = TenantManager(self.db)
        self.keys = {}
        for name in ("alpha", "beta"):
            self.tenants.add_tenant(Tenant(name, name, plan_id=self.plan.id))
            self.keys[name] = self.tenants.issue_api_key(name)
        self.llm = llm or FakeLLM()
        self.gate = BudgetGate({self.plan.id: self.plan},
                               now=datetime(2026, 10, 1, tzinfo=timezone.utc), database=self.db)
        self.handler = RequestHandler(self.tenants, self.gate, self.llm, RateLimiter(),
                                      AuditLog(self.db), IdempotencyStore(self.db), PatternModerator())

    def call(self, tenant="alpha", *, messages=None, key=None):
        return self.handler.handle(self.keys[tenant], messages or MESSAGES, "fake", key)

    def tenant(self, name="alpha"):
        return self.tenants.get_tenant(name)

    def close(self):
        # Database currently has no public close method. Test-only resource cleanup.
        self.db._conn.close()
