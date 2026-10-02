"""Show that concurrent reserves cannot pass a tenant's monthly budget."""

import sys
import threading
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.models.llm import Message
from src.models.plan import Plan
from src.models.tenant import Tenant
from src.services.budget import BudgetExceeded, BudgetGate
from src.services.fakellm_inference import FakeLLM

THREADS = 40


def burst_reserve() -> None:
    plan = Plan(
        id="burst",
        name="Burst",
        monthly_budget_usd=Decimal("0.10"),
        soft_budget_usd=Decimal("0.10"),
        request_reserve_usd=Decimal("0.02"),
        requests_per_minute=1000,
    )
    gate = BudgetGate({"burst": plan})
    tenant = Tenant(id="t", name="Burst", plan_id="burst")
    barrier = threading.Barrier(THREADS)
    reserved: list[str] = []
    lock = threading.Lock()

    def once() -> None:
        barrier.wait()
        try:
            reservation_id = gate.reserve(tenant)
        except BudgetExceeded:
            return
        with lock:
            reserved.append(reservation_id)

    threads = [threading.Thread(target=once) for _ in range(THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    spent = gate.spent_usd(tenant.id)
    if spent > plan.monthly_budget_usd:
        raise SystemExit(f"reserve burst exceeded budget: {spent}")
    if spent != len(reserved) * plan.request_reserve_usd:
        raise SystemExit(f"reserved {len(reserved)} but spent {spent}")
    if len(reserved) != 5:
        raise SystemExit(f"expected 5 holds, got {len(reserved)}")
    print(f"reserve burst ok: {len(reserved)} holds, spent ${spent}")


def burst_settle() -> None:
    plan = Plan(
        id="burst",
        name="Burst",
        monthly_budget_usd=Decimal("0.05"),
        soft_budget_usd=Decimal("0.05"),
        request_reserve_usd=Decimal("0.02"),
        requests_per_minute=1000,
    )
    gate = BudgetGate({"burst": plan})
    tenant = Tenant(id="t", name="Burst", plan_id="burst")
    llm = FakeLLM()
    barrier = threading.Barrier(THREADS)
    successes = 0
    lock = threading.Lock()

    def once() -> None:
        nonlocal successes
        barrier.wait()
        try:
            gate.guarded_complete(tenant, llm, [Message(role="user", content="hi")], "fake")
        except BudgetExceeded:
            return
        with lock:
            successes += 1

    threads = [threading.Thread(target=once) for _ in range(THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    spent = gate.spent_usd(tenant.id)
    expected = successes * Decimal("0.015")
    if spent > plan.monthly_budget_usd:
        raise SystemExit(f"settle burst exceeded budget: {spent}")
    if spent != expected:
        raise SystemExit(f"spent {spent}, expected {expected} from {successes} calls")
    print(f"settle burst ok: {successes} calls, spent ${spent}")


if __name__ == "__main__":
    burst_reserve()
    burst_settle()
