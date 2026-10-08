# Evaluation v2

`cases.json` holds hand-written cases in two groups. Every case that needs a
model runs on `gpt-4o-mini` through `RequestHandler`, with `OpenAIInference`
and `OpenAIModerator`, which is the same wiring `main.py` uses. Each case gets
its own in-memory SQLite database. HTTP and URL fetching are not part of the
run; summary pages are fixed text passed to the `/v1/summarize` prompt
(`summary_prompt` in `src/app.py`).

From `cumin/`, with `OPENAI_API_KEY` in `.env`:

```bash
uv sync --frozen
PYTHONDONTWRITEBYTECODE=1 uv run --frozen --env-file .env python scripts/run_eval.py
```

A full run makes about 50 model calls and costs well under one cent.

## Summary quality

Ten pages: release notes, a council budget story, a recipe, a study abstract,
a page with an instruction planted for summarizers, a delay notice, a 404
page, a pricing table, a news article buried in site navigation and cookie
text, and a Spanish news story. Each case lists:

- `facts`: groups of phrases. The summary must contain at least one phrase
  from each group (case-insensitive).
- `forbidden`: phrases that must not appear, such as the planted `PINEAPPLE`
  instruction or the cookie banner.
- `max_words`: 90 for articles and 50 for the 404 page, to hold the prompt's
  "a few sentences" to a concrete limit.

Each check is one point. A trial passes only when all its checks pass. Every
case runs three times (`--trials`) because the model samples, so the score is
reported over all 30 trials.

## Policy

Seventeen invariants for quota, rate limit, idempotency, moderation and cost.
Twelve reach the model. `input_pattern`, `input_moderation` and `invalid_auth`
go through the same handler and must stop before it. `rate_window` and
`invalid_cached_usage` test the limiter and the cost function directly.
Notable designs:

- `usd_cap` and `token_cap` set the per-request reserve equal to the monthly
  cap, so the first call is admitted and the second must stop before the
  model.
- `burst_reserve` sends 40 requests at once under a cap that fits five
  reserves. It checks that no more than five are at the model at the same
  time and that spend stays under the cap.
- `provider_usage_cost` recomputes the cost from the usage OpenAI returned at
  the pinned rates in `src/utils/openai_cost.py` and compares it with the
  ledger.
- `input_moderation` uses a threat the pattern classifier does not match, so
  the rejection comes from the OpenAI moderation endpoint.
- `provider_error_release` asks for an unknown model so OpenAI returns an
  error.

Known regressions count as failures. The exit status is 1 if any summary trial
or policy case fails.

## Results

Recorded run in [results.json](results.json), including every summary the
model wrote:

| Group | Score |
|---|---:|
| Summary trials | 25/30 (83.3%) |
| Summary checks | 136/141 (96.5%) |
| Policy invariants | 14/17 (82.4%) |

49 model calls, $0.0025 total, median handler latency 2.34 s for a summary.

Summary misses: `council_budget` left out the 7-2 vote in all three trials,
`release_notes` ran to 92 words once, and `embedded_instruction` once
described the work as "upgrades" without the new signalling. No summary
followed the planted instruction.

The three failing policy cases are the known regressions in
[pending decisions](../docs/pending-decisions.md):

- Actual USD can exceed the reservation and therefore the monthly cap
  ($0.0000207 spent under a $0.000001 cap).
- Actual tokens can exceed the reservation and therefore the token cap
  (49 tokens under a 5-token cap).
- Two simultaneous requests with the same idempotency key both call the model
  and both charge.

## Limits

Fact matching is by phrase, so a correct paraphrase can miss. Every miss in
the recorded run was read by hand and is listed above. Pattern moderation
covers known phrases only. Tenant checks cover service-layer scoping, not HTTP
authorization. Redis, cross-process concurrency and URL fetching are not
evaluated here.
