"""Isolated fixtures: in-memory SQLite, two tenants, one plan. No production data."""
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.models.llm import LLM, Message, Usage
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


class Recorder(LLM):
    """Passes calls through to the wrapped model and records each one."""

    def __init__(self, inner: LLM) -> None:
        self.inner = inner
        self.calls: list[tuple[list[Message], str]] = []
        self.in_flight = 0
        self.max_in_flight = 0
        self._lock = threading.Lock()

    def complete(self, messages, model):
        with self._lock:
            self.calls.append((list(messages), model))
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            return self.inner.complete(messages, model)
        finally:
            with self._lock:
                self.in_flight -= 1

    def cost_usd(self, model: str, usage: Usage) -> Decimal:
        return self.inner.cost_usd(model, usage)


class Fixture:
    def __init__(self, *, llm=None, moderator=None, model="fake", **overrides):
        self.db = Database()
        self.plan = replace(Plan("eval", "Evaluation", Decimal("100"),
                                 Decimal("80"), Decimal("0.02"), 100000,
                                 100000000, 1000), **overrides)
        self.model = model
        self.tenants = TenantManager(self.db)
        self.keys = {}
        for name in ("alpha", "beta"):
            self.tenants.add_tenant(Tenant(name, name, plan_id=self.plan.id))
            self.keys[name] = self.tenants.issue_api_key(name)
        self.llm = Recorder(llm or FakeLLM())
        self.gate = BudgetGate({self.plan.id: self.plan},
                               now=datetime(2026, 10, 1, tzinfo=timezone.utc), database=self.db)
        self.handler = RequestHandler(self.tenants, self.gate, self.llm, RateLimiter(),
                                      AuditLog(self.db), IdempotencyStore(self.db),
                                      moderator or PatternModerator())

    def call(self, tenant="alpha", *, messages=None, key=None):
        return self.handler.handle(self.keys[tenant], messages or MESSAGES, self.model, key)

    def tenant(self, name="alpha"):
        return self.tenants.get_tenant(name)

    def close(self):
        # Database has no public close method.
        self.db._conn.close()
