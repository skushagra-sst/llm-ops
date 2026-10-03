# Offline policy evaluation v1

`cases.json` is an assistant-authored candidate set, not a claim that the team
hand-wrote it. Team members must review, edit and take ownership of the final
set and scoring method before submitting it under the course requirement.
This set evaluates API policy/cost correctness, not the quality of generated
summaries. A human-written summary-quality set and human scoring are still
needed if the team evaluates that feature.

From `cumin/`:

```bash
uv sync --frozen
PYTHONDONTWRITEBYTECODE=1 uv run --frozen python scripts/run_eval.py
PYTHONDONTWRITEBYTECODE=1 uv run --frozen python scripts/benchmark_fake.py
```

No `.env`, API key, network, paid model, production DB or Redis is used. Each
case uses isolated in-memory SQLite and closes it. A mock SDK response checks
usage parsing and the repository's existing price arithmetic without calling
OpenAI. Those rates are a pinned code fixture, not verified current pricing.

## Scoring

Each named policy invariant scores one point, including known regressions.
The pass rate is `passed / total`. All failures count; exit status is 1 if
any case fails. Exceptions from worker futures are propagated and counted as
failures. The set is intentionally small and does not prove security.

Current results: **13/16 (81.25%)**. Three failures are retained as failing
regressions rather than marked expected/pass:

- Actual USD can exceed the reservation and therefore the monthly cap.
- Actual token usage can exceed the reservation and therefore the token cap.
- Concurrent same-key retries can both call the provider and charge.

See [results.json](results.json) and [pending decisions](../docs/pending-decisions.md).
Pattern moderation checks only known patterns, not broad safety or jailbreak
resistance. Tenant checks cover service-layer audit/cache/ledger scoping, not
HTTP authorization or full admin UI access control. Redis, cross-process
concurrency, persistent-disk performance, URL-fetch guard, real LLM output
quality, and live deployment are not evaluated by this suite.
