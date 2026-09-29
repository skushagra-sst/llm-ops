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
uv run --env-file .env scripts/benchmark_unchecked.py
```
