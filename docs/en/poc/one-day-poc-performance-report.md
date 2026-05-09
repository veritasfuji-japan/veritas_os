# One-Day PoC Performance Benchmark Report

## Purpose

This is a **local HTTP PoC benchmark** for One-Day PoC endpoints.
It requires a running local/configured VERITAS API server and `VERITAS_API_KEY`.

This benchmark is **not** the same as the deterministic local performance metrics artifact.
For deterministic local non-HTTP artifact output, see:
`docs/en/benchmarks/local-performance-metrics.latest.md`.

## How to run

```bash
VERITAS_API_KEY=... python scripts/demo/one_day_poc_benchmark.py --runs 5 --warmup 1 --base-url http://127.0.0.1:8000 --out-json /tmp/one-day-poc-benchmark.json --out-md /tmp/one-day-poc-benchmark.md
```

## Interpretation boundaries (non-claims)

- This is a local HTTP PoC benchmark.
- It is not a production latency benchmark.
- It is not a production SLA.
- It is not third-party certified.
- It is not a customer environment measurement.
- External LLM/provider latency is not measured unless the configured local server explicitly invokes such providers.

## JSON output fields

The script emits a stable benchmark packet shape (`one_day_poc_benchmark.v1`) including:

- scenario and measurement timestamp
- run/warmup/timeout configuration
- sanitized environment metadata
- latency summaries (`min`, `p50`, `p95`, `p99`, `max`, `mean`, `stdev`)
- per-target success/failure counts
- limitations and sanitized failure metadata

## Related evidence pack

- For reviewer-facing PoC evidence collection and success/failure criteria, see `docs/en/poc/one-day-poc-evidence-pack.md`.
- This benchmark report is only one input into the evidence pack.
- It is not a production SLA, third-party certification, or customer environment measurement.
