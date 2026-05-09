# Local Performance Metrics Artifact

- This file summarizes `docs/en/benchmarks/local-performance-metrics.latest.json`.
- This is a deterministic local measurement artifact.
- It does not measure production latency.
- It does not call external LLM/API providers.
- It is not a production SLA.
- It is not third-party certified.
- It is not a customer environment measurement.

## Scope

This artifact records one deterministic local benchmark execution only. It does not represent production latency or customer environment behavior.

## Artifact

- JSON: `docs/en/benchmarks/local-performance-metrics.latest.json`
- Summary (this file): `docs/en/benchmarks/local-performance-metrics.latest.md`

## How it was generated

```bash
python scripts/benchmarks/run_performance_metrics.py --iterations 100 --warmup 10 --output docs/en/benchmarks/local-performance-metrics.latest.json
```

## Metrics summary

Local deterministic artifact only (not production latency):

| Field | Value |
| --- | --- |
| schema_version | performance_metrics.v1 |
| scenario | local_deterministic_smoke |
| iterations | 100 |
| warmup | 10 |
| mean_ms | 0.010114 |
| median_ms | 0.008882 |
| p95_ms | 0.015959 |
| p99_ms | 0.024828 |
| min_ms | 0.008606 |
| max_ms | 0.029875 |
| success | 100 |
| failure | 0 |

## Interpretation boundaries

- Deterministic local benchmark only.
- No external LLM/API calls.
- Not a production SLA.
- Not third-party certified.
- Not a customer environment measurement.

## Next measurement targets

- API route latency
- Bind boundary decision latency
- TrustLog append latency, JSONL and PostgreSQL separately
- one-day PoC end-to-end scenario latency
- provider adapter overhead
- cost-per-request estimation when external LLM providers are intentionally enabled
