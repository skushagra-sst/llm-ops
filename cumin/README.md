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
  uses OpenAI inference/moderation, and so do the evaluation and load
  benchmark. Public URL fetching happens before handler authentication and
  replay lookup; these measurements do not include fetching.
- The dashboard provides costs, usage and audit logs. Playground responses
  include latency; audit now persists handler-only latency; no tracing backend was
  added. See [pending decisions](docs/pending-decisions.md).

## Unit tests

`tests/` covers `BudgetGate` and the budget path through `RequestHandler`:
holds, exact cap boundaries, release, settlement errors, token caps, the soft
warning, monthly reset, tenant separation, concurrent reserves, and billing
around moderation, provider errors and replays. They use a local fake model,
so they need no API key. The three known regressions are marked `xfail`
(strict), so the suite fails once one is fixed and its marker should be removed.

```bash
uv sync --frozen
uv run --frozen pytest
```

## Evaluation

Hand-written cases in [eval/cases.json](eval/cases.json), run on `gpt-4o-mini`
by [scripts/run_eval.py](scripts/run_eval.py) through `RequestHandler` with
OpenAI inference and moderation. Method and limits are in
[eval/README.md](eval/README.md); every summary and score from the recorded
run is in [eval/results.json](eval/results.json).

- **Summary quality:** ten pages, each with required facts, forbidden phrases
  and a word limit, run three times each. **25/30 trials** passed and
  **136/141 checks** passed. The model never followed the instruction planted
  in a page. Misses: the council vote count left out (three times), one
  summary over the word limit, and one that omitted the new signalling.
- **Policy:** **14/17 invariants** passed. The three failures are the known
  regressions: actual USD above the reservation and cap, actual tokens above
  the reservation and cap, and concurrent same-key requests charging twice.

The run made 49 model calls for $0.0025. The command exits 1 while any case
fails and writes all results first.

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --frozen --env-file .env python scripts/run_eval.py
```

## Load benchmark

[scripts/benchmark_load.py](scripts/benchmark_load.py) sends the summary
prompt for the `release_notes` eval page to `gpt-4o-mini` through
`RequestHandler` with OpenAI moderation, using in-memory SQLite and the local
limiter. HTTP and URL fetching are excluded. Each scenario has 200 measured
requests after three discarded warmups, with two tenants alternating.
Percentiles are nearest-rank over successful requests.

| Concurrency | Success | p50 | p95 | p99 | req/s | Cost/request |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 200/200 | 2373 ms | 2837 ms | 3415 ms | 0.41 | $0.000097 |
| 8 | 200/200 | 2409 ms | 3240 ms | 6964 ms | 3.03 | $0.000096 |

Requests averaged 183 input and about 115 output tokens. At concurrency 8,
throughput rises about 7x while the median holds, and the tail grows. Each
tenant was billed for its own 100 requests in each scenario (about $0.0097
each). The latency is mostly OpenAI: the model call plus two moderation
calls per request. Raw samples are in
[benchmarks/load_gpt-4o-mini.json](benchmarks/load_gpt-4o-mini.json) and
[benchmarks/load_gpt-4o-mini_samples.csv](benchmarks/load_gpt-4o-mini_samples.csv).

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --frozen --env-file .env python scripts/benchmark_load.py --samples 200 --concurrency 1 8
```

## Submission caveats

Live deployment is optional and was not done. Runtime config wiring and the
three feature regressions remain open.
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

The timing and migration checks pass. USD/token overshoot and concurrent
idempotency are still failing in the evaluation and deliberately unchanged
pending the owner's decision.
