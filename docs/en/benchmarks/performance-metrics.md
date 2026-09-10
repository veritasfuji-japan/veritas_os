# Performance Metrics

## Purpose

This document defines the deterministic local performance harness for VERITAS OS.
It is intended to make performance measurement reproducible before publishing
business-facing numbers.

TASK-011 Benchmark Rebaseline is now governed by:

`docs/benchmarks/benchmark-rebaseline-contract-v1.json`

Phase A freezes benchmark identity and claim boundaries before current-head
numbers are published.

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

Canonical Phase B command:

```bash
python scripts/benchmarks/run_performance_metrics.py \
  --iterations 100 \
  --warmup 10 \
  --output docs/en/benchmarks/local-performance-metrics.latest.json
```

## JSON output schema

The current harness outputs `performance_metrics.v1` JSON with:

- metadata (`schema_version`, `generated_at`, `scenario`)
- environment details
- run controls (`iterations`, `warmup`)
- aggregate timing metrics (`mean_ms`, `median_ms`, `p95_ms`, `p99_ms`, etc.)
- success/failure counters
- explicit scope notes

TASK-011 Phase B must extend current-head publication identity so the benchmark
artifact also records the measured source commit, exact command, and explicit
claim/reproducibility boundary.

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
- Bind boundary decision latency/current-governance-recheck overhead
- TrustLog append latency, JSONL and PostgreSQL separately
- controlled Decision-to-Effect timing components
- one-day PoC end-to-end scenario latency
- provider adapter overhead where separately scoped
- cost-per-request estimation only when external providers are intentionally enabled

## Existing local artifact during Phase A

The files below remain in the repository:

- `docs/en/benchmarks/local-performance-metrics.latest.json`
- `docs/en/benchmarks/local-performance-metrics.latest.md`
- `docs/ja/benchmarks/local-performance-metrics.latest.md`

However, the current JSON artifact was generated on 2026-05-09 and does not
record the measured source commit. Under the TASK-011 Phase A contract it is
classified as:

**STALE_PRE_REBASELINE_REFERENCE**

It is local/deterministic only and must not be presented as a measurement of the
current post-consolidation head. Phase B will replace/rebaseline it only after
artifact identity requirements are implemented.

## Relationship to One-Day PoC benchmark

- `scripts/benchmarks/run_performance_metrics.py` is the canonical deterministic local performance harness for TASK-011.
- `scripts/demo/one_day_poc_benchmark.py` measures local/configured HTTP PoC endpoints and requires `VERITAS_API_KEY`; it is a supporting PoC benchmark, not the canonical Phase A/initial Phase B harness.
- `veritas_os/scripts/run_benchmarks_enhanced.py` remains a maintenance YAML `/v1/decide` runner and is not the canonical deterministic rebaseline harness.
- None of these benchmark surfaces establishes a production SLA or third-party certification.
