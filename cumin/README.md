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
