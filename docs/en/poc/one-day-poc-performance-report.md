# One-Day PoC Performance Benchmark Report

## Purpose

This document describes how to generate lightweight, reproducible local latency evidence for the One-Day PoC flow.
It is intended for external reviewers, HPAN, enterprise stakeholders, and investor diligence.

## How to run

Recommended command:

```bash
mkdir -p runtime/dev/benchmarks
VERITAS_API_KEY=... python scripts/demo/one_day_poc_benchmark.py \
  --runs 10 \
  --warmup 2 \
  --json \
  --out-json runtime/dev/benchmarks/veritas_poc_benchmark.json \
  --out-md runtime/dev/benchmarks/veritas_poc_benchmark.md
```

## JSON output fields

The script emits a stable benchmark packet shape (`one_day_poc_benchmark.v1`) including:

- scenario and measurement timestamp
- run/warmup/timeout configuration
- sanitized environment metadata
- latency summaries (`min`, `p50`, `p95`, `p99`, `max`, `mean`, `stdev`)
- per-target success/failure counts
- limitations and sanitized failure metadata

## Markdown output

`--out-md` generates a local benchmark report containing:

- Summary
- Environment
- Benchmark results table
- Methodology
- Limitations
- What this does not prove
- Recommended next measurements

## How reviewers should interpret results

- Treat this as **local benchmark evidence**, not production capacity proof.
- Use it to confirm the PoC path can produce measured, reproducible latency data.
- Compare repeated runs in the same environment before discussing trend or drift.

## Limitations

- Local machine/network effects can dominate measured latency.
- Deployment topology and model-provider conditions may change results.
- This script does not perform load, concurrency, or long-duration reliability testing.

## Not a production SLA

These measurements are **not** production SLA commitments.

## Not legal certification

These measurements do **not** certify EU AI Act compliance or any legal/regulatory status.

## Next production measurements

- Staging environment benchmark baselines
- Concurrency and throughput tests
- Tail latency under controlled load
- Regional/network variation analysis
