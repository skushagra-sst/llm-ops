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

Twenty-one invariants for quota, rate limit, idempotency, moderation and
cost. Thirteen reach the model. `input_pattern`, `input_moderation`,
`unsupported_model`, `invalid_auth` and the two over-cap cases go through the
same handler and must stop before it. `rate_window` and `invalid_cached_usage`
test the limiter and the cost function directly. Notable designs:

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
- `provider_error_release` sends an invalid message role so OpenAI returns an
  error after the hold is taken.
- `worst_case_hold` sets a tiny plan reserve, so the hold is the request's own
  worst case. It checks that OpenAI's input tokens fit the byte bound, output
  fits the cap, the cost fits the hold, and the ledger stores OpenAI's numbers
  unchanged.
- `output_cap` asks for a 1,500-word essay with a 16-token cap and checks that
  OpenAI stops at 16 output tokens.
- `actual_cost_over_reserve` and `actual_tokens_over_reserve` set caps below
  the request's worst case ($0.000001 and 5 tokens) and check that it is
  refused before the model, so neither cap can be passed.
- `concurrent_idempotency` releases two requests with the same key at once.
  It checks for one model call and one charge, that one request completed
  and the other was refused as in progress (or replayed, if it arrived after
  the first finished), and that a later retry replays.
- `key_reuse` completes a request, then sends a different prompt with the
  same key and checks that it is refused without a model call or charge.

Known regressions count as failures. The exit status is 1 if any summary trial
or policy case fails.

## Results

Recorded run in [results.json](results.json), including every summary the
model wrote:

| Group | Score |
|---|---:|
| Summary trials | 26/30 (86.7%) |
| Summary checks | 137/141 (97.2%) |
| Policy invariants | 21/21 (100%) |

49 model calls, $0.0026 total, median handler latency 2.50 s for a summary.

Summary misses: `release_notes` went over the 90-word limit in two trials
(96 and 100 words) and `council_budget` left out the 7-2 vote in two. No
summary followed the planted instruction. Earlier runs missed the council
vote in all three trials, or had one summary that omitted the signalling;
results vary run to run because the model samples.

Budget bounds measured on OpenAI: 18 input tokens billed against a bound of
57, 42 output tokens against the 512 cap, and $0.000028 billed against a
$0.00032 hold. With a 16-token cap, OpenAI returned exactly 16 output tokens.

In `concurrent_idempotency`, one request completed and the other was refused
as in progress while the first was at OpenAI; one model call, one charge.

## Limits

Fact matching is by phrase, so a correct paraphrase can miss. Every miss in
the recorded run was read by hand and is listed above. Pattern moderation
covers known phrases only. Tenant checks cover service-layer scoping, not HTTP
authorization. Redis, cross-process concurrency and URL fetching are not
evaluated here; cross-process idempotency claims are covered by the unit
tests.
