# Cumin

**Multi-tenant LLM API with Cost Attribution & Quotas**

One of the two project options for Group 14 in the ML System Design & LLMOps course (Scaler School of Technology).

## The problem

When one LLM API serves many teams or customers (tenants), every call costs money in tokens. Without per-tenant tracking there is no way to know who spent what, and without limits one heavy tenant can burn through the budget or crowd out everyone else.

## What this project is about

An LLM API built for multiple tenants that:

- Identifies which tenant each request belongs to and keeps their usage separate.
- Attributes cost to each tenant based on their actual usage (tokens consumed, per model).
- Enforces per-tenant quotas so usage stays within agreed limits.

## Admin console

The console at `/admin` covers tenants, plans, and usage. The overview shows this month's spend, requests, and tokens across every tenant, with a daily activity chart.

![Admin overview](docs/screenshots/overview.png)

Each tenant page shows its plan, budget and rate-limit usage, cost per API key, the ledger, searchable request logs, and stored responses. The playground sends a real request through every gate on behalf of a tenant, and the Plans page creates and edits plans.

![Tenant page](docs/screenshots/tenant.png)

Build the console, then start the server. `CUMIN_PORT` sets the port (default `8000`).

```bash
cd web && npm install && npm run build && cd ..
uv run --env-file .env python main.py
```

## Baseline, before plan and budget checks

Measured on the unchecked path: `OpenAIInference.complete` has no auth, plan, or budget gate. Eight samples, one warmup discarded, model `gpt-4o-mini` (served as `gpt-4o-mini-2024-07-18`). Prompt: "In one sentence, explain what an API quota is." Each non-streaming call used 18 input tokens and 34–42 output tokens, with no cached input, at about `$0.000023`–`$0.000028`.

`complete` returns only after the full response, so that row is end-to-end latency. Time to first token is a streaming call with the same prompt, because `complete` does not stream.

| | Median | Mean | Min | Max |
|---|---:|---:|---:|---:|
| Full latency of `complete` | 1182 ms | 1127 ms | 872 ms | 1289 ms |
| Time to first token | 762 ms | 814 ms | 699 ms | 1083 ms |
| Streaming call, full response | 1080 ms | 1116 ms | 905 ms | 1374 ms |

Exact samples are in [benchmarks/unchecked_baseline.json](benchmarks/unchecked_baseline.json). Reproduce with:

```bash
uv run --env-file .env python scripts/benchmark_unchecked.py
```

## After auth, rate limit, and budget checks

Same prompt, model, and sample size. Latency is `RequestHandler.handle`: authenticate, rate-limit, classify the prompt, reserve budget, call the model, moderate the output, and settle. Time to first token runs those gates and then streams, because `handle` does not stream. Each non-streaming call used 18 input tokens and 31–40 output tokens, at about `$0.000021`–`$0.000027`.

| | Median | Mean | Min | Max |
|---|---:|---:|---:|---:|
| Full latency of `handle` | 985 ms | 1089 ms | 853 ms | 1520 ms |
| Time to first token | 808 ms | 758 ms | 609 ms | 1006 ms |
| Streaming call, full response | 1073 ms | 1070 ms | 899 ms | 1333 ms |

Exact samples are in [benchmarks/checked_baseline.json](benchmarks/checked_baseline.json). Reproduce with:

```bash
uv run --env-file .env python scripts/benchmark_checked.py
```

## Final-project implementation status

Cumin is the selected Group 14 implementation. Earlier sections and baseline
results are retained unchanged. This addition documents the current source
and new offline measurements; it does not claim the application is bug-free.

## Architecture and request flow

```text
Tenant client -> FastAPI POST /v1/summarize
  -> public-URL guard + page fetch + summary message construction
  -> RequestHandler: API-key authentication -> tenant-scoped replay lookup
  -> per-tenant rate limit -> input moderation
  -> BudgetGate: reserve USD + tokens -> inference -> output moderation
  -> settle actual model usage/cost -> save idempotent result -> audit
  -> summary, model usage, cumulative spend and soft-budget warning

Admin console -> token-protected /v1/admin/* -> tenant/plan management
  -> ledger + tenant/key cost attribution + audit/search + usage chart
```

**Design choices and limits**

- API keys are hashed in SQLite; tenant IDs scope ledger, replay and audit.
  Cost arithmetic uses Decimal and model usage, including cached input.
- Reserve/settle keeps admission checks and concurrent holds inside SQLite
  transactions. Failures/rejected output release holds. Actual costs above
  reserves are NOT bounded: see the failing regression cases below.
- A shared SQLite Database uses `BEGIN IMMEDIATE` and a lock. It keeps the
  prototype easy to run and inspect, but serializes operations and is not a
  claim of distributed throughput or large-scale suitability.
- The default in-memory limiter is a rolling 60-second window local to one
  process. `REDIS_URL` selects the Redis fixed-minute limiter, which shares
  rate counters but has different window semantics and boundary bursts.
  Redis does not replace the SQLite quota ledger. Redis was not tested here.
- Sequential idempotent retries avoid another model call/charge. Concurrent
  retries with the same key are not atomic and can double-charge.
- Pattern moderation is deterministic but narrow. The production launcher
  uses OpenAI inference/moderation. The new tests use local FakeLLM and pattern
  moderation only. Public URL fetching happens before handler authentication
  and replay lookup; these measurements do not include fetching.
- The dashboard provides costs, usage and audit logs. Playground responses
  include latency; audit now persists handler-only latency; no tracing backend was
  added. See [pending decisions](docs/pending-decisions.md).

## Offline evaluation and scoring

Candidate fixtures: [eval/cases.json](eval/cases.json).
Runner: [scripts/run_eval.py](scripts/run_eval.py).
Method and limits: [eval/README.md](eval/README.md).
Recorded results: [eval/results.json](eval/results.json).

**13/16 invariants passed (81.25%)** on the recorded source commit. All three
regressions count as failures: actual USD beyond reserve/cap, actual tokens
beyond reserve/cap, and concurrent same-key double-charging. This is policy
correctness evaluation, not a summary-quality or broad security score.
The fixtures are assistant-authored candidates. Team review/editing is still
required for the course's hand-written evaluation requirement.

## Offline load benchmark (FakeLLM)

Each scenario has 500 measured requests and 10 discarded warmups. Nearest-rank
p50/p95/p99, successful requests only. Two tenants alternate requests. Measured
on the execution environment recorded in the JSON, through RequestHandler and
shared in-memory SQLite, not through HTTP. No provider, fetching, Redis, disk
I/O, real moderation, or deployment is included. This measures local policy
path overhead, not production end-to-end model latency or capacity.

| Concurrency | Requests | Success | p50 ms | p95 ms | p99 ms | req/s | Synthetic cost/request |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 500 | 500/500 | 0.516 | 0.922 | 0.978 | 1749.6 | $0.015 |
| 8 | 500 | 500/500 | 5.362 | 11.055 | 15.311 | 1435.1 | $0.015 |

[Raw samples, environment and tenant attribution](benchmarks/fake_load_v1.json).
Each tenant made 250 measured calls for $3.750 simulated ledger cost in each
scenario. Alpha additionally has $0.150 of discarded warmup calls. FakeLLM
uses 10 input + 5 output tokens at $0.001/token: **no money was spent**.
These costs must not be presented as real OpenAI cost per request. The eight
real-model baseline samples above are historical and cannot establish p99.

Reproduce from `cumin/` without `.env` or credentials:

```bash
uv sync --frozen
PYTHONDONTWRITEBYTECODE=1 uv run --frozen python scripts/run_eval.py
PYTHONDONTWRITEBYTECODE=1 uv run --frozen python scripts/benchmark_fake.py --samples 500 --concurrency 1 8
```

The eval command intentionally exits 1 until the reported feature regressions
are fixed. It writes all results before exiting. Do not substitute a passing
subset for the full score. Existing `benchmark_checked.py` and
`benchmark_unchecked.py` call OpenAI and are not part of this offline run.

## Versioned prompt and plan references

[Prompt v1](prompts/v1/summarize.snapshot.json) and
[plan defaults v1](config/v1/plans.snapshot.json) are additive snapshots of
current code. They are **not runtime-loaded config**. Wiring them into feature
code or changing behavior requires owner approval; DB plan edits may differ.

## Resume description (draft for team review)

Built Cumin, a multi-tenant LLM API with per-tenant and per-key cost attribution,
USD/token quota reservations, rate limiting, moderation, audit logs and a React
admin console. Added a reproducible offline policy suite and 500-request
benchmarks at two concurrency levels, with explicit regression reporting and
no paid model calls.

## Submission caveats

Live deployment is optional and was not done. Human ownership of the evaluation
set, actual summary-quality scoring if applicable, runtime config wiring, and the three feature regressions remain open.
[Required decisions and unchanged-code evidence](docs/pending-decisions.md).

## Latency persistence (owner-approved issue 3)

Audit `latency_ms` is nullable and measures **handler-only time**: authentication,
replay lookup, limits, moderation, reservation, inference and settlement up to
recording the outcome. It excludes HTTP transport, URL fetching and the audit
insert itself. Response `handler_latency_ms` measures the same handler path
through return, including the final audit write, so it can be slightly larger.
This scope is consistent for completed, replayed, unauthenticated, rate-limited,
budget-blocked, input/output-rejected and provider-error outcomes already
recorded by the handler. A replay records its current lookup time, not the
original call's duration. Unexpected failures outside those existing audited
paths and URL-fetch errors are not newly traced by this change.

Public summary now includes per-call `cost_usd` and `handler_latency_ms`.
Usage events and admin log JSON/CSV expose nullable timing. Playground retains
its existing `latency_ms` (URL fetch + handler) alongside the explicitly named
handler metric. Historical audit rows migrate to NULL, never an invented zero.
No historical records are deleted. No dashboard UI rewrite was needed; timing
is available in the log API/export rather than a new chart.

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --frozen python scripts/check_latency.py
```

The timing/migration checks pass. The original policy suite remains 13/16:
USD/token overshoot and concurrent idempotency are still failing and deliberately
unchanged pending the owner's later decision.

### Post-latency regression run

The original load table above is the pre-latency snapshot (source commit in its
JSON). After adding latency persistence, a separate run at source commit
`36c8c3b` still completed 1000/1000 calls:

| Concurrency | Requests | p50 ms | p95 ms | p99 ms | req/s |
|---:|---:|---:|---:|---:|---:|
| 1 | 500 | 0.575 | 1.074 | 1.375 | 1657.9 |
| 8 | 500 | 5.311 | 13.415 | 18.607 | 1257.4 |

[Post-change report](benchmarks/fake_load_after_latency_v1.json) and
[raw CSV samples](benchmarks/fake_load_after_latency_v1_samples.csv).
Same synthetic $0.015/request; no actual spend. Differences reflect both
instrumentation and run-to-run noise, not a controlled causal overhead study.
[Post-change policy results](eval/latency_regression_results.json) remain 13/16,
with the same three failed cases corresponding to the two unresolved bugs.
