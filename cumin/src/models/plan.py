from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Plan:
    id: str
    name: str
    monthly_budget_usd: Decimal
    soft_budget_usd: Decimal
    request_reserve_usd: Decimal
    requests_per_minute: int = 60
    monthly_token_budget: int = 10_000_000
    request_reserve_tokens: int = 1_000


PLANS: dict[str, Plan] = {
    "zero": Plan(
        id="zero",
        name="Zero",
        monthly_budget_usd=Decimal("0.00"),
        soft_budget_usd=Decimal("0.00"),
        request_reserve_usd=Decimal("0.05"),
        requests_per_minute=10,
        monthly_token_budget=0,
        request_reserve_tokens=1,
    ),
    "free": Plan(
        id="free",
        name="Free",
        monthly_budget_usd=Decimal("1.00"),
        soft_budget_usd=Decimal("0.80"),
        request_reserve_usd=Decimal("0.05"),
        requests_per_minute=60,
        monthly_token_budget=500_000,
        request_reserve_tokens=8_000,
    ),
    "pro": Plan(
        id="pro",
        name="Pro",
        monthly_budget_usd=Decimal("50.00"),
        soft_budget_usd=Decimal("40.00"),
        request_reserve_usd=Decimal("0.25"),
        requests_per_minute=600,
        monthly_token_budget=20_000_000,
        request_reserve_tokens=16_000,
    ),
}
