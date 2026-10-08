"""Latency and time-to-first-token for the checked request path.

Latency is RequestHandler.handle, which authenticates, rate-limits, bounds the
request's worst case, classifies the prompt, reserves that worst case, calls the
model with the output cap, moderates the output, and settles. Time to first
token runs those same gates, then streams with the same cap, because handle does
not stream. The stream reservation is released so it is not booked twice. One warmup
call of each kind is discarded.
"""

import json
import statistics
import sys
import time
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.models.llm import Message
from src.models.plan import Plan
from src.models.tenant import Tenant
from src.services.audit import AuditLog
from src.services.budget import BudgetGate
from src.services.idempotency import IdempotencyStore
from src.services.moderation import check_input
from src.services.openai_inference import OpenAIInference
from src.services.rate_limit import RateLimiter
from src.services.request import RequestHandler
from src.services.tenant import TenantManager

MODEL = "gpt-4o-mini"
PROMPT = "In one sentence, explain what an API quota is."
WARMUP = 1
SAMPLES = 8
OUT = ROOT / "benchmarks" / "checked_baseline.json"
BENCH_PLAN = Plan(
    id="bench",
    name="Bench",
    monthly_budget_usd=Decimal("5"),
    soft_budget_usd=Decimal("4"),
    request_reserve_usd=Decimal("0.05"),
    requests_per_minute=1000,
)


def percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((pct / 100) * (len(ordered) - 1)))
    return ordered[index]


def summarize(values: list[float]) -> dict[str, float]:
    return {
        "min_ms": min(values),
        "p50_ms": percentile(values, 50),
        "mean_ms": statistics.fmean(values),
        "p95_ms": percentile(values, 95),
        "max_ms": max(values),
    }


def build() -> tuple[RequestHandler, str]:
    tenants = TenantManager()
    tenants.add_tenant(Tenant(id="bench", name="Bench", plan_id="bench"))
    raw_key = tenants.issue_api_key("bench")
    handler = RequestHandler(
        tenants,
        BudgetGate({"bench": BENCH_PLAN}),
        OpenAIInference(),
        RateLimiter(),
        AuditLog(),
        IdempotencyStore(),
    )
    return handler, raw_key


def measure_latency(handler: RequestHandler, raw_key: str) -> dict:
    messages = [Message(role="user", content=PROMPT)]
    started = time.perf_counter()
    result = handler.handle(raw_key, messages, MODEL)
    elapsed_ms = (time.perf_counter() - started) * 1000
    completion = result.completion
    return {
        "latency_ms": elapsed_ms,
        "model": completion.model,
        "input_tokens": completion.usage.input_tokens,
        "output_tokens": completion.usage.output_tokens,
        "cached_input_tokens": completion.usage.cached_input_tokens,
        "cost_usd": str(handler.llm.cost_usd(completion.model, completion.usage)),
    }


def measure_ttft(handler: RequestHandler, raw_key: str) -> dict:
    messages = [Message(role="user", content=PROMPT)]
    started = time.perf_counter()
    tenant = handler.tenants.authenticate(raw_key)
    plan = handler.budget.plan_for(tenant)
    if not handler.limiter.allow(tenant.id, plan.requests_per_minute):
        raise RuntimeError("benchmark hit the rate limit")
    bound = handler.bound(messages, MODEL)
    check_input(messages)
    reservation_id = handler.budget.reserve(tenant, usd=bound.usd, tokens=bound.tokens)
    try:
        stream = handler.llm._client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": PROMPT}],
            max_completion_tokens=bound.output_tokens,
            stream=True,
        )
        ttft_ms = None
        for chunk in stream:
            if not chunk.choices:
                continue
            if chunk.choices[0].delta.content:
                ttft_ms = (time.perf_counter() - started) * 1000
                break
        for _chunk in stream:
            pass
        total_ms = (time.perf_counter() - started) * 1000
    finally:
        handler.budget.release(reservation_id)
    if ttft_ms is None:
        raise RuntimeError("stream produced no content")
    return {"ttft_ms": ttft_ms, "stream_total_ms": total_ms}


def main() -> None:
    handler, raw_key = build()
    for _ in range(WARMUP):
        measure_latency(handler, raw_key)
        measure_ttft(handler, raw_key)

    latency_runs = [measure_latency(handler, raw_key) for _ in range(SAMPLES)]
    ttft_runs = [measure_ttft(handler, raw_key) for _ in range(SAMPLES)]
    report = {
        "label": "checked",
        "model": MODEL,
        "prompt": PROMPT,
        "samples": SAMPLES,
        "warmup_discarded": WARMUP,
        "latency": summarize([run["latency_ms"] for run in latency_runs]),
        "ttft": summarize([run["ttft_ms"] for run in ttft_runs]),
        "stream_total": summarize([run["stream_total_ms"] for run in ttft_runs]),
        "latency_runs": latency_runs,
        "ttft_runs": ttft_runs,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("latency", "ttft", "stream_total")}, indent=2))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
