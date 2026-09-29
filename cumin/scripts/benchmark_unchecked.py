"""Latency and time-to-first-token for the unchecked inference path.

Latency is OpenAIInference.complete, which returns only after the full response.
Time to first token uses a streaming call on the same client, because complete
does not stream. One warmup call of each kind is discarded.
"""

import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.models.llm import Message
from src.services.openai_inference import OpenAIInference

MODEL = "gpt-4o-mini"
PROMPT = "In one sentence, explain what an API quota is."
WARMUP = 1
SAMPLES = 8
OUT = ROOT / "benchmarks" / "unchecked_baseline.json"


def percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((pct / 100) * (len(ordered) - 1)))
    return ordered[index]


def summarize(values: list[float]) -> dict[str, float]:
    return {
        "min_ms": min(values),
        "p50_ms": percentile(values, 50),
        "mean_ms": statistics.fmean(values),
        "p95_ms": percentile(values, 95),
        "max_ms": max(values),
    }


def measure_latency(inference: OpenAIInference) -> dict:
    messages = [Message(role="user", content=PROMPT)]
    started = time.perf_counter()
    completion = inference.complete(messages, MODEL)
    elapsed_ms = (time.perf_counter() - started) * 1000
    return {
        "latency_ms": elapsed_ms,
        "model": completion.model,
        "input_tokens": completion.usage.input_tokens,
        "output_tokens": completion.usage.output_tokens,
        "cached_input_tokens": completion.usage.cached_input_tokens,
        "cost_usd": str(inference.cost_usd(completion.model, completion.usage)),
    }


def measure_ttft(inference: OpenAIInference) -> dict:
    started = time.perf_counter()
    stream = inference._client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": PROMPT}],
        stream=True,
    )
    ttft_ms = None
    for chunk in stream:
        if not chunk.choices:
            continue
        if chunk.choices[0].delta.content:
            ttft_ms = (time.perf_counter() - started) * 1000
            break
    for _chunk in stream:
        pass
    total_ms = (time.perf_counter() - started) * 1000
    if ttft_ms is None:
        raise RuntimeError("stream produced no content")
    return {"ttft_ms": ttft_ms, "stream_total_ms": total_ms}


def main() -> None:
    inference = OpenAIInference()
    for _ in range(WARMUP):
        measure_latency(inference)
        measure_ttft(inference)

    latency_runs = [measure_latency(inference) for _ in range(SAMPLES)]
    ttft_runs = [measure_ttft(inference) for _ in range(SAMPLES)]

    report = {
        "label": "unchecked",
        "model": MODEL,
        "prompt": PROMPT,
        "samples": SAMPLES,
        "warmup_discarded": WARMUP,
        "latency": summarize([run["latency_ms"] for run in latency_runs]),
        "ttft": summarize([run["ttft_ms"] for run in ttft_runs]),
        "stream_total": summarize([run["stream_total_ms"] for run in ttft_runs]),
        "latency_runs": latency_runs,
        "ttft_runs": ttft_runs,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("latency", "ttft", "stream_total")}, indent=2))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
