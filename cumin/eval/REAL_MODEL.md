# Domain policy evals with real local inference

Review `domain_cases_v2.json` and the matching branches in `../scripts/run_open_model.py` before submission. Each case gets one point only when every assertion passes. Exceptions count as failures. Known bugs are not converted into expected passes. This evaluates service policy correctness, not generated-summary quality or broad safety.

## Measured run, October 8, 2026 (IST)

- Source feature commit: `481d75b98b16edb29aa38b6fa06a0723db809952` (main, PR #3 not merged).
- Model: Qwen2.5-0.5B-Instruct, bartowski Q4_K_M GGUF. Real autoregressive inference, not canned responses.
- Runtime: llama.cpp b11476, commit `988190680`; CPU only, 2 threads, 2 server slots, total context 2048. 2 vCPU Intel Xeon 2.60GHz, 1.9 GiB RAM.
- Temperature 0, seed 42, 32-token output limit, prompt cache disabled. One warmup request excluded. Short synthetic tenant-usage summaries only; no personal data.
- **12/15 (80%)** policy cases pass. Raw results: `real_qwen_eval_2026-10-08.json`.
- Failures: USD overshoot at an explicitly synthetic accounting tariff (76 tokens cost $0.000076 against $0.000001 cap), token overshoot (76 against 1-token cap), and concurrent same-key retry (2 real inference calls and 2 charges). No feature fixes applied.
- Invalid auth, zero budget and explicit injection tests deliberately prove *no* model invocation. Other cases use real model outputs and server-reported usage. Concurrency test uses a test-only barrier after the cache lookup to force the vulnerable overlap.
- USD accounting cases use a test-only $0.000001/token tariff to test meaningful nonzero arithmetic with real tokens. This is **not** the model's market price or an invoice. Normal local inference has API fee $0/request. Infrastructure/electricity/amortization cost is unmeasured, so all-in cost/request is unknown.

## Real-inference load measurements

`real_qwen_benchmark_2026-10-08.json` includes all request texts, token counts, timings and failures. Each load has 30 requests, all successful, unique user messages, no idempotency replay. Timing covers `RequestHandler`, policy checks, in-memory SQLite and loopback inference. It does **not** include the FastAPI HTTP route, admin UI, public network, Redis, persistent-disk storage or deployed capacity.

| Client concurrency | Successful | p50 | p95 | p99 | Throughput |
|---|---:|---:|---:|---:|---:|
| 1 | 30/30 | 1.613s | 1.878s | 1.973s | 0.717 req/s |
| 2 | 30/30 | 2.567s | 3.203s | 3.467s | 0.868 req/s |

Percentiles use nearest rank on successful requests. With 30 samples p99 is the maximum, not a reliable production tail estimate. Small CPU model, capped short outputs and one machine: do not generalize to larger models, long prompts or production. Some outputs reach the 32-token limit; summaries require separate human quality scoring. No quality score is claimed. Existing fake-load files are retained as historical policy-path microbenchmarks and must not be reported as real-model throughput.

## Reproduce

Download the GGUF from the pinned model revision and a compatible llama.cpp server, without API credits. Do not commit the model binary.

- Base model: https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct
- Quantized model: https://huggingface.co/bartowski/Qwen2.5-0.5B-Instruct-GGUF
- Revision: `41ba88dbac95fed2528c92514c131d73eb5a174b`
- File: `Qwen2.5-0.5B-Instruct-Q4_K_M.gguf`
- SHA256: `6eb923e7d26e9cea28811e1a8e852009b21242fb157b26149d3b188f3a8c8653`
- Runtime asset: https://github.com/ggml-org/llama.cpp/releases/download/b11476/llama-b11476-bin-ubuntu-x64.tar.gz

From `cumin/`:

```bash
uv sync --frozen
PYTHONDONTWRITEBYTECODE=1 uv run --frozen python scripts/run_open_model.py \
  --server /path/to/llama-server --model /path/to/model.gguf \
  --output eval/runs/qwen_cpu_new_run --samples 30
```

The output folder must not already exist: previous run history is never overwritten. The harness starts a server only on loopback port 8099 and terminates it on exit. Local test adapter lives in the script; application feature code is unchanged. Port 8099 must be free. The script returns nonzero when an eval or benchmark request fails, after saving results.

## Personal review sheet

- Confirm each scenario and its assertion matches the project's intended contract, not merely current behavior.
- Review the three failing cases and proposed fixes separately; never hide failures or clip measured accounting to make a cap pass.
- Add/edit cases you believe are missing, including rejected-output billing policy and cross-process retries.
- Check raw outputs for factual summary quality and truncation; no automatic quality score exists here.
- Record any edits and rerun the suite so the published cases and scores match.
- Decide whether the resulting set satisfies the course requirement. No certification is supplied by these files.
