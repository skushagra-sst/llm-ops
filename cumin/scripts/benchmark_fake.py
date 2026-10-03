"""Measure offline RequestHandler overhead. Not HTTP or real-model performance."""
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
from eval_support import Fixture, ROOT


def measure(samples, concurrency):
    fixture = Fixture()
    try:
        for _ in range(10):
            fixture.call()
        before = fixture.gate.spent_usd("alpha")
        def once(index):
            start = time.perf_counter()
            tenant = "alpha" if index % 2 == 0 else "beta"
            try:
                result = fixture.call(tenant)
                return {"index": index, "tenant": tenant, "latency_ms": (time.perf_counter() - start) * 1000,
                        "cost_usd": str(result.cost_usd), "input_tokens": result.completion.usage.input_tokens,
                        "output_tokens": result.completion.usage.output_tokens, "success": True}
            except Exception as exc:
                return {"index": index, "tenant": tenant, "latency_ms": (time.perf_counter() - start) * 1000,
                        "success": False, "error": f"{type(exc).__name__}: {exc}"}
        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            runs = list(pool.map(once, range(samples)))
        seconds = time.perf_counter() - start
        successful = [r for r in runs if r["success"]]
        latencies = sorted(r["latency_ms"] for r in successful)
        def percentile(p):
            return latencies[max(0, math.ceil(len(latencies) * p / 100) - 1)] if latencies else None
        total = sum((Decimal(r["cost_usd"]) for r in successful), Decimal(0))
        attribution = {}
        for tenant in ("alpha", "beta"):
            subset = [r for r in successful if r["tenant"] == tenant]
            attribution[tenant] = {"measured_requests": len(subset), "measured_cost_usd": str(sum(
                (Decimal(r["cost_usd"]) for r in subset), Decimal(0))),
                "ledger_cost_usd_including_warmup": str(fixture.gate.spent_usd(tenant))}
        assert total == fixture.gate.spent_usd("alpha") + fixture.gate.spent_usd("beta") - before
        return {"samples": samples, "concurrency": concurrency, "warmup_discarded": 10,
                "successes": len(successful), "failures": samples - len(successful), "elapsed_seconds": seconds,
                "latency_ms": {"p50": percentile(50), "p95": percentile(95), "p99": percentile(99)},
                "throughput_successful_requests_per_second": len(successful) / seconds,
                "synthetic_total_cost_usd": str(total),
                "synthetic_cost_per_request_usd": str(total / len(successful)) if successful else None,
                "tenant_attribution": attribution, "runs": runs}
    finally:
        fixture.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=500)
    parser.add_argument("--concurrency", type=int, nargs="+", default=[1, 8])
    parser.add_argument("--output", type=type(ROOT), default=ROOT / "benchmarks/fake_load_v1.json")
    args = parser.parse_args()
    if not 100 <= args.samples <= 10000 or any(c < 1 or c > 100 for c in args.concurrency):
        parser.error("Use 100-10000 samples and concurrency 1-100")
    report = {"version": "1.0.0", "measured_at": datetime.now(timezone.utc).isoformat(),
              "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "environment": {"python": platform.python_version(), "platform": platform.platform()},
              "scope": "in-process RequestHandler; shared in-memory SQLite, pattern moderation, local limiter, FakeLLM",
              "excluded": ["HTTP/ASGI", "URL fetching", "network", "real inference", "OpenAI moderation", "Redis", "disk I/O"],
              "cost_note": "FakeLLM $0.001/token, 10 input + 5 output. Simulated ledger cost, not money spent or real model pricing.",
              "paid_api_calls": 0, "percentile_method": "nearest rank ceil(N*p/100), successful calls only",
              "scenarios": [measure(args.samples, c) for c in args.concurrency]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    samples_path = args.output.with_name(args.output.stem + "_samples.csv")
    for scenario in report["scenarios"]:
        rows.extend({"concurrency": scenario["concurrency"], **run} for run in scenario.pop("runs"))
        scenario["raw_samples_file"] = samples_path.name
    with samples_path.open("w", newline="") as stream:
        fields = sorted({key for row in rows for key in row})
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    args.output.write_text(json.dumps(report, indent=2) + "\n")
    for s in report["scenarios"]:
        print({k: s[k] for k in ("samples", "concurrency", "successes", "failures", "latency_ms", "throughput_successful_requests_per_second")})
    return int(any(s["failures"] for s in report["scenarios"]))

if __name__ == "__main__":
    raise SystemExit(main())
