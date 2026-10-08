# Feature changes requiring owner approval

No feature code was changed while adding these deliverables.

## Budget reservation does not cap actual usage

`BudgetGate.reserve` protects admission using estimated per-request USD/tokens.
`settle` accepts larger actual usage without enforcing a bound. The regression
cases on gpt-4o-mini show $0.0000207 spent under a $0.000001 monthly cap, and
49 tokens under a 5-token cap. Production plans have larger reserves, but there is no enforced maximum
provider output proving usage stays within them.

Decision needed: enforce an input/output bound and reserve its worst-case cost;
define how to handle unavoidable provider costs above the reserve. Simply
rejecting a settlement after inference does not undo a paid provider call.
Feature work would touch budget/request/provider code. Approval is required.

## Concurrent idempotency race

`RequestHandler` checks cache, calls provider, settles and then saves a result.
Two in-flight requests with the same tenant/key can both miss and charge. The
regression starts two gpt-4o-mini requests together and observes two model
calls and two ledger entries.

Decision needed: atomically claim the tenant/key before inference, then wait
or return a conflict while in flight, with failure/recovery handling. A local
lock only covers one process; DB-backed ownership is needed across workers.
Approval is required before changing the handler/store/schema.

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
public summary/usage and admin log JSON/CSV expose it. Budget settlement and
idempotency flow are unchanged. Existing audit rows remain NULL.
See the README's timing scope and `scripts/check_latency.py`.
