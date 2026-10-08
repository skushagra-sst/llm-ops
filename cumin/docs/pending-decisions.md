# Feature changes requiring owner approval

## Budget reservation does not cap actual usage (fixed)

Resolved for issue #1 with a request-specific worst-case reservation. Each
request's input is bounded by its byte length, its output is capped at 512
tokens, and that worst case is reserved before the model call. Usage is then
settled exactly as billed; anything above the hold is flagged as an overrun.
Unpriced models are refused. See "Hard-cap guarantee" in the README, the unit
tests in `tests/`, and the `worst_case_hold`, `output_cap` and over-cap
evaluation cases.

## Concurrent idempotency race (fixed)

Resolved for issue #2 with a database-backed claim on the tenant's key, taken
in one transaction before the rate limit, reservation or model call. The
owner's decisions: a duplicate that arrives while the first request is
running gets 409 with `Retry-After` straight away (it does not wait), and a
claim left by a crashed process is never taken over; that key answers 409
"outcome unknown, use a new key" permanently. Reusing a key for a different
request also gets 409. Claims are dropped on failures before the charge and
kept on failures after it. See "Idempotency" in the README,
`tests/test_idempotency.py`, and the `concurrent_idempotency` and `key_reuse`
evaluation cases.

## Per-request latency and response cost

The playground returns measured latency and cost, but audit stores no latency.
Public `/v1/summarize` returns usage and cumulative spend, not this request's
cost or latency. Benchmark samples now record both, but do not add production
observability. Approval is needed for a timing field, audit schema migration,
and API response changes. Existing historical rows must remain intact.

## Runtime versioned config is not yet wired

`config/v1/plans.snapshot.json` and `prompts/v1/summarize.snapshot.json` preserve
current defaults/template as versioned documentation. Runtime still reads the
Python defaults, the DB-backed PlanStore, and `_summary_messages` in app.py.
Connecting the snapshots to runtime requires feature-code edits and a policy
for DB plan edits and version attribution. Approval is required.

## Non-feature work still needed from the team

- Confirm the submission title/team/resume wording and public repo version.
- Committed pycache and the old "two project options" text were not removed
  or rewritten. No root README edits, deletion, or untracking was done.
- `run_eval.py`, `benchmark_load.py`, `benchmark_checked.py` and
  `benchmark_unchecked.py` call OpenAI and spend a small amount per run.
- Deployment is optional. No hosted service, tracing backend or Redis
  validation was set up.

## Update: latency persistence approved and implemented

The earlier latency gap above is retained as historical context. On October 3,
the owner approved issue 3 only. Audit now stores nullable handler-only latency;
public summary/usage and admin log JSON/CSV expose it. That change left budget
settlement and the idempotency flow unchanged (both were changed later for
issues #1 and #2). Existing audit rows remain NULL.
See the README's timing scope and `scripts/check_latency.py`.
