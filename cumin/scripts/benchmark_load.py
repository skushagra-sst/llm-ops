"""Load benchmark on gpt-4o-mini through RequestHandler with OpenAI moderation.

Each request summarizes the release_notes page from eval/cases.json with the
/v1/summarize prompt. Two tenants alternate requests. Latency is measured
around RequestHandler.handle; HTTP and URL fetching are excluded. Needs
OPENAI_API_KEY and spends a small amount on the OpenAI account.
"""
import argparse
import csv
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
import json
import math
import platform
import subprocess
import time
from eval_support import ROOT
from run_eval import MODEL, fixture
from src.app import summary_prompt

PAGE_CASE = "release_notes"


def page_messages():
    cases = json.loads((ROOT / "eval/cases.json").read_text())["summary"]
    case = next(c for c in cases if c["id"] == PAGE_CASE)
    return summary_prompt(case["url"], case["page"])


def measure(samples, concurrency, warmup, messages):
    f = fixture()
    try:
        for _ in range(warmup):
            f.call(messages=messages)
        before = f.gate.spent_usd("alpha")

        def once(index):
            tenant = "alpha" if index % 2 == 0 else "beta"
            start = time.perf_counter()
            try:
                result = f.call(tenant, messages=messages)
            except Exception as exc:
                return {"index": index, "tenant": tenant, "success": False,
                        "latency_ms": (time.perf_counter() - start) * 1000,
                        "error": f"{type(exc).__name__}: {exc}"}
            usage = result.completion.usage
            return {"index": index, "tenant": tenant, "success": True,
                    "latency_ms": (time.perf_counter() - start) * 1000,
                    "cost_usd": str(result.cost_usd), "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens, "cached_input_tokens": usage.cached_input_tokens}

        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            runs = list(pool.map(once, range(samples)))
        seconds = time.perf_counter() - start
        ok = [r for r in runs if r["success"]]
        latencies = sorted(r["latency_ms"] for r in ok)

        def percentile(p):
            return latencies[max(0, math.ceil(len(latencies) * p / 100) - 1)] if latencies else None

        total = sum((Decimal(r["cost_usd"]) for r in ok), Decimal(0))
        assert total == f.gate.spent_usd("alpha") + f.gate.spent_usd("beta") - before
        attribution = {}
        for tenant in ("alpha", "beta"):
            subset = [r for r in ok if r["tenant"] == tenant]
            attribution[tenant] = {"requests": len(subset),
                                   "cost_usd": str(sum((Decimal(r["cost_usd"]) for r in subset), Decimal(0)))}
        return {"samples": samples, "concurrency": concurrency, "warmup_discarded": warmup,
                "successes": len(ok), "failures": samples - len(ok), "elapsed_seconds": seconds,
                "latency_ms": {"p50": percentile(50), "p95": percentile(95), "p99": percentile(99)},
                "throughput_requests_per_second": len(ok) / seconds,
                "total_cost_usd": str(total),
                "cost_per_request_usd": str(total / len(ok)) if ok else None,
                "mean_input_tokens": sum(r["input_tokens"] for r in ok) / len(ok) if ok else None,
                "mean_output_tokens": sum(r["output_tokens"] for r in ok) / len(ok) if ok else None,
                "tenant_attribution": attribution, "runs": runs}
    finally:
        f.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=200)
    parser.add_argument("--concurrency", type=int, nargs="+", default=[1, 8])
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--output", type=type(ROOT), default=ROOT / "benchmarks/load_gpt-4o-mini.json")
    args = parser.parse_args()
    if not 20 <= args.samples <= 2000 or any(c < 1 or c > 32 for c in args.concurrency):
        parser.error("use 20-2000 samples and concurrency 1-32")
    messages = page_messages()
    report = {"version": "2.0.0", "model": MODEL,
              "measured_at": datetime.now(timezone.utc).isoformat(),
              "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "environment": {"python": platform.python_version(), "platform": platform.platform()},
              "path": "RequestHandler with OpenAIInference and OpenAIModerator; in-memory SQLite; local limiter",
              "excluded": ["HTTP/ASGI", "URL fetching", "Redis", "disk I/O"],
              "workload": f"summary prompt for eval case {PAGE_CASE}",
              "percentile_method": "nearest rank ceil(N*p/100), successful calls only",
              "scenarios": [measure(args.samples, c, args.warmup, messages) for c in args.concurrency]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    samples_path = args.output.with_name(args.output.stem + "_samples.csv")
    rows = []
    for scenario in report["scenarios"]:
        rows.extend({"concurrency": scenario["concurrency"], **run} for run in scenario.pop("runs"))
        scenario["raw_samples_file"] = samples_path.name
    with samples_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=sorted({key for row in rows for key in row}))
        writer.writeheader()
        writer.writerows(rows)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    for s in report["scenarios"]:
        print({k: s[k] for k in ("concurrency", "successes", "failures", "latency_ms",
                                 "throughput_requests_per_second", "cost_per_request_usd")})
    return int(any(s["failures"] for s in report["scenarios"]))


if __name__ == "__main__":
    raise SystemExit(main())
