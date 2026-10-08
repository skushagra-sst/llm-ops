from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import threading

import pytest

from src.models.llm import Usage
from src.models.tenant import Tenant
from src.services.budget import BudgetExceeded
from tests.conftest import NOVEMBER

USAGE = Usage(input_tokens=10, output_tokens=5)


def test_open_hold_counts_as_spend(make_gate, tenants):
    gate, plan = make_gate()
    gate.reserve(tenants.get_tenant("alpha"))
    assert gate.spent_usd("alpha") == plan.request_reserve_usd
    assert gate.spent_tokens("alpha") == plan.request_reserve_tokens


def test_reserves_fill_the_cap_exactly_then_block(make_gate, tenants):
    gate, plan = make_gate()
    alpha = tenants.get_tenant("alpha")
    for _ in range(5):
        gate.reserve(alpha)
    assert gate.spent_usd("alpha") == plan.monthly_budget_usd
    with pytest.raises(BudgetExceeded, match="cost"):
        gate.reserve(alpha)


def test_zero_budget_blocks_the_first_request(make_gate, tenants):
    gate, _ = make_gate(monthly_budget_usd=Decimal("0"), soft_budget_usd=Decimal("0"))
    with pytest.raises(BudgetExceeded):
        gate.reserve(tenants.get_tenant("alpha"))


def test_release_frees_the_budget(make_gate, tenants):
    gate, _ = make_gate(monthly_budget_usd=Decimal("0.02"))
    alpha = tenants.get_tenant("alpha")
    hold = gate.reserve(alpha)
    with pytest.raises(BudgetExceeded):
        gate.reserve(alpha)
    gate.release(hold)
    assert gate.spent_usd("alpha") == 0
    gate.reserve(alpha)


def test_release_twice_is_harmless(make_gate, tenants):
    gate, _ = make_gate()
    hold = gate.reserve(tenants.get_tenant("alpha"))
    gate.release(hold)
    gate.release(hold)
    assert gate.ledger("alpha")[0]["status"] == "released"


def test_settle_replaces_the_hold_with_actual_cost(make_gate, tenants):
    gate, _ = make_gate()
    hold = gate.reserve(tenants.get_tenant("alpha"))
    settlement = gate.settle(hold, Decimal("0.005"), USAGE)
    assert settlement.spent_usd == Decimal("0.005")
    assert settlement.spent_tokens == 15
    assert gate.spent_usd("alpha") == Decimal("0.005")
    assert gate.spent_tokens("alpha") == 15


def test_settled_cost_below_reserve_frees_room(make_gate, tenants):
    gate, _ = make_gate(monthly_budget_usd=Decimal("0.03"))
    alpha = tenants.get_tenant("alpha")
    gate.settle(gate.reserve(alpha), Decimal("0.005"), USAGE)
    gate.reserve(alpha)
    with pytest.raises(BudgetExceeded):
        gate.reserve(alpha)


def test_settle_rejects_negative_cost(make_gate, tenants):
    gate, _ = make_gate()
    hold = gate.reserve(tenants.get_tenant("alpha"))
    with pytest.raises(ValueError):
        gate.settle(hold, Decimal("-0.01"), USAGE)
    assert gate.ledger("alpha")[0]["status"] == "open"


def test_settle_twice_is_rejected(make_gate, tenants):
    gate, _ = make_gate()
    hold = gate.reserve(tenants.get_tenant("alpha"))
    gate.settle(hold, Decimal("0.005"), USAGE)
    with pytest.raises(RuntimeError):
        gate.settle(hold, Decimal("0.005"), USAGE)
    assert gate.spent_usd("alpha") == Decimal("0.005")


def test_settle_after_release_is_rejected(make_gate, tenants):
    gate, _ = make_gate()
    hold = gate.reserve(tenants.get_tenant("alpha"))
    gate.release(hold)
    with pytest.raises(RuntimeError):
        gate.settle(hold, Decimal("0.005"), USAGE)
    assert gate.spent_usd("alpha") == 0


def test_release_after_settle_is_rejected(make_gate, tenants):
    gate, _ = make_gate()
    hold = gate.reserve(tenants.get_tenant("alpha"))
    gate.settle(hold, Decimal("0.005"), USAGE)
    with pytest.raises(RuntimeError):
        gate.release(hold)
    assert gate.spent_usd("alpha") == Decimal("0.005")


def test_unknown_reservation_is_rejected(make_gate):
    gate, _ = make_gate()
    with pytest.raises(KeyError):
        gate.settle("missing", Decimal("0.005"), USAGE)


def test_token_cap_blocks_when_reserve_does_not_fit(make_gate, tenants):
    gate, _ = make_gate(monthly_token_budget=30, request_reserve_tokens=15)
    alpha = tenants.get_tenant("alpha")
    gate.settle(gate.reserve(alpha), Decimal("0.001"), USAGE)
    gate.settle(gate.reserve(alpha), Decimal("0.001"), USAGE)
    assert gate.spent_tokens("alpha") == 30
    with pytest.raises(BudgetExceeded, match="token"):
        gate.reserve(alpha)


def test_soft_warning_starts_at_the_threshold(make_gate, tenants):
    gate, _ = make_gate(soft_budget_usd=Decimal("0.01"))
    alpha = tenants.get_tenant("alpha")
    below = gate.settle(gate.reserve(alpha), Decimal("0.005"), USAGE)
    at = gate.settle(gate.reserve(alpha), Decimal("0.005"), USAGE)
    assert not below.warning
    assert at.warning


def test_spend_resets_in_a_new_month(make_gate, tenants):
    october, _ = make_gate(monthly_budget_usd=Decimal("0.02"))
    alpha = tenants.get_tenant("alpha")
    october.settle(october.reserve(alpha), Decimal("0.02"), USAGE)
    with pytest.raises(BudgetExceeded):
        october.reserve(alpha)
    november, _ = make_gate(now=NOVEMBER, monthly_budget_usd=Decimal("0.02"))
    assert november.spent_usd("alpha") == 0
    november.reserve(alpha)
    assert october.spent_usd("alpha") == Decimal("0.02")


def test_tenants_have_separate_budgets(make_gate, tenants):
    gate, _ = make_gate(monthly_budget_usd=Decimal("0.02"))
    gate.reserve(tenants.get_tenant("alpha"))
    with pytest.raises(BudgetExceeded):
        gate.reserve(tenants.get_tenant("alpha"))
    gate.reserve(tenants.get_tenant("beta"))
    assert gate.spent_usd("beta") == Decimal("0.02")


def test_unknown_plan_is_an_error(make_gate):
    gate, _ = make_gate()
    with pytest.raises(KeyError):
        gate.reserve(Tenant("ghost", "Ghost", plan_id="missing"))


def test_month_usage_counts_settled_requests_only(make_gate, tenants):
    gate, _ = make_gate()
    alpha = tenants.get_tenant("alpha")
    gate.settle(gate.reserve(alpha), Decimal("0.005"), Usage(10, 5, 4))
    gate.release(gate.reserve(alpha))
    gate.reserve(alpha)
    usage = gate.month_usage("alpha")
    assert usage.request_count == 1
    assert (usage.input_tokens, usage.output_tokens, usage.cached_input_tokens) == (10, 5, 4)
    assert usage.spent_usd == Decimal("0.005")


def test_concurrent_reserves_never_pass_the_cap(make_gate, tenants):
    gate, plan = make_gate()
    alpha = tenants.get_tenant("alpha")
    barrier = threading.Barrier(40)

    def reserve(_):
        barrier.wait(timeout=10)
        try:
            return gate.reserve(alpha)
        except BudgetExceeded:
            return None

    with ThreadPoolExecutor(max_workers=40) as pool:
        holds = list(pool.map(reserve, range(40)))
    assert sum(hold is not None for hold in holds) == 5
    assert gate.spent_usd("alpha") == plan.monthly_budget_usd


def test_request_worst_case_above_plan_reserve_is_held(make_gate, tenants):
    gate, _ = make_gate()
    gate.reserve(tenants.get_tenant("alpha"), usd=Decimal("0.05"), tokens=500)
    row = gate.ledger("alpha")[0]
    assert (Decimal(row["reserved_usd"]), row["reserved_tokens"]) == (Decimal("0.05"), 500)


def test_plan_reserve_is_the_minimum_hold(make_gate, tenants):
    gate, plan = make_gate()
    gate.reserve(tenants.get_tenant("alpha"), usd=Decimal("0.001"), tokens=1)
    row = gate.ledger("alpha")[0]
    assert Decimal(row["reserved_usd"]) == plan.request_reserve_usd
    assert row["reserved_tokens"] == plan.request_reserve_tokens


def test_worst_case_that_does_not_fit_is_refused(make_gate, tenants):
    gate, _ = make_gate()
    alpha = tenants.get_tenant("alpha")
    with pytest.raises(BudgetExceeded, match="cost"):
        gate.reserve(alpha, usd=Decimal("0.11"))
    with pytest.raises(BudgetExceeded, match="token"):
        gate.reserve(alpha, tokens=100_001)
    assert gate.ledger("alpha") == []


def test_cost_above_the_hold_is_recorded_truthfully(make_gate, tenants):
    gate, _ = make_gate(monthly_budget_usd=Decimal("0.02"))
    settlement = gate.settle(gate.reserve(tenants.get_tenant("alpha")), Decimal("0.03"), USAGE)
    row = gate.ledger("alpha")[0]
    assert settlement.overrun
    assert (Decimal(row["actual_usd"]), row["overrun"]) == (Decimal("0.03"), 1)
    assert gate.spent_usd("alpha") == Decimal("0.03")


def test_tokens_above_the_hold_are_recorded_truthfully(make_gate, tenants):
    gate, _ = make_gate(monthly_token_budget=10, request_reserve_tokens=10)
    settlement = gate.settle(gate.reserve(tenants.get_tenant("alpha")), Decimal("0.001"), USAGE)
    row = gate.ledger("alpha")[0]
    assert settlement.overrun
    assert (row["input_tokens"], row["output_tokens"], row["overrun"]) == (10, 5, 1)
    assert gate.spent_tokens("alpha") == 15


def test_usage_within_the_hold_is_not_an_overrun(make_gate, tenants):
    gate, _ = make_gate()
    settlement = gate.settle(gate.reserve(tenants.get_tenant("alpha")), Decimal("0.02"), USAGE)
    assert not settlement.overrun
    assert gate.ledger("alpha")[0]["overrun"] == 0
