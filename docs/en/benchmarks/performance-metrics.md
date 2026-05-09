# Performance Metrics

## Purpose

This document defines the deterministic local performance harness for VERITAS OS.
It is intended to make performance measurement reproducible before publishing
business-facing numbers.

## What this benchmark measures

- Deterministic local harness execution time.
- Lightweight local function-path timing for:
  - canonical JSON serialization
  - SHA-256 hashing
  - drift vector scoring
  - operator message construction

## What it does not measure

- This is a deterministic local harness.
- It does not call external LLM providers.
- It does not measure end-to-end production latency.
- It does not measure cloud deployment latency.
- It does not claim production SLA.
- It is not third-party certified.

## How to run

```bash
python scripts/benchmarks/run_performance_metrics.py --iterations 100 --output /tmp/veritas-performance-metrics.json
```

## JSON output schema

The harness outputs `performance_metrics.v1` JSON with:

- metadata (`schema_version`, `generated_at`, `scenario`)
- environment details
- run controls (`iterations`, `warmup`)
- aggregate timing metrics (`mean_ms`, `median_ms`, `p95_ms`, `p99_ms`, etc.)
- success/failure counters
- explicit scope notes

## Interpreting results

Percentiles use nearest-rank semantics over measured iteration durations; `p95_ms` and `p99_ms` are local harness statistics, not production latency guarantees.

Use this output to compare local deterministic runs under controlled conditions.
Do not present this output as production throughput, customer latency, or external certification.

## Current limitations

- Local-only path; no networked provider calls.
- Single-process timing only.
- No cloud deployment contention model.
- No customer workload profile coverage.

## Next measurement targets

- API route latency
- Bind boundary decision latency
- TrustLog append latency, JSONL and PostgreSQL separately
- provider adapter overhead
- one-day PoC end-to-end scenario latency
- cost-per-request estimation when LLM providers are used

## Latest local artifact

- Latest local deterministic artifact:
  - `docs/en/benchmarks/local-performance-metrics.latest.json`
  - `docs/en/benchmarks/local-performance-metrics.latest.md`
- Japanese companion:
  - `docs/ja/benchmarks/local-performance-metrics.latest.md`
- This artifact is local/deterministic only and not a production SLA.
