# Benchmark Rebaseline — Phase A Contract Freeze

Status: **PHASE A / CONTRACT FROZEN**  
Source main: `53e8e2974123024348b92ddfb7155cd645371620`  
Frozen controlled E2E anchor: `ada46f2fe324dd3cbcff6be59d56c4f75c4a6bdc`

Machine-readable contract:
`docs/benchmarks/benchmark-rebaseline-contract-v1.json`

## Purpose

TASK-011 starts by freezing what each benchmark actually measures before any new
performance number is published.

The repository already contains several benchmark-like tools with different
purposes. Treating all of them as one benchmark would create ambiguous claims.
Phase A separates the canonical rebaseline surfaces from supporting or legacy
runners and records the exact claim boundary.

## Canonical surface 1 — local deterministic performance

Harness:

`scripts/benchmarks/run_performance_metrics.py`

Canonical command for Phase B:

```bash
python scripts/benchmarks/run_performance_metrics.py \
  --iterations 100 \
  --warmup 10 \
  --output docs/en/benchmarks/local-performance-metrics.latest.json
```

Input identity:

- embedded deterministic fixture in `_run_iteration`
- scenario: `local_deterministic_smoke`
- canonical JSON serialization
- SHA-256 hashing
- WAT drift scoring
- operator-message construction

Runtime target:

- CPython 3.12
- Linux x86_64 class environment
- exact Python/platform identity must be captured in the generated result

This harness performs no external LLM/API calls and is not an HTTP, production,
customer-environment, or throughput benchmark.

## Canonical surface 2 — evidence-axis benchmark

Harness:

`veritas_os/scripts/evidence_benchmark.py`

Contract inputs:

- `veritas_os/benchmarks/evidence/metrics_definition.yaml`
- `veritas_os/benchmarks/evidence/output_schema.json`
- `veritas_os/benchmarks/evidence/fixtures/sample_cases.jsonl`

Canonical command:

```bash
python -m veritas_os.scripts.evidence_benchmark \
  --fixtures veritas_os/benchmarks/evidence/fixtures/sample_cases.jsonl \
  --output /tmp/veritas-evidence-benchmark.json
```

The current fixture contains two repository-controlled cases and compares labels
named `veritas` and `generic`. That comparison is **synthetic fixture scoring**.
It is not independent competitive testing and must not be described as proof
that VERITAS outperforms a named vendor or third-party system.

## Supporting but non-canonical benchmark surfaces

### One-Day PoC HTTP benchmark

`scripts/demo/one_day_poc_benchmark.py`

This is useful for a configured PoC environment, but it requires
`VERITAS_API_KEY`, performs HTTP calls, and depends on server/environment setup.
It is therefore not the canonical deterministic Phase A/initial Phase B
measurement surface.

### Enhanced YAML /v1/decide runner

`veritas_os/scripts/run_benchmarks_enhanced.py`

This runner posts YAML benchmark requests to `/v1/decide` and writes runtime
logs. It remains useful as an existing maintenance/test tool, but it is not the
canonical deterministic rebaseline harness.

## Existing local metrics artifact

`docs/en/benchmarks/local-performance-metrics.latest.json` was generated on
2026-05-09 and does not record the source commit SHA.

It remains in the repository as a historical local reference, but Phase A marks
it:

**STALE_PRE_REBASELINE_REFERENCE**

It must not be presented as a measurement of the current post-consolidation
head. Phase A intentionally does not replace its numbers.

## Required Phase B artifact identity

Every newly published benchmark artifact must record enough information to
answer:

1. Which source commit was measured?
2. Which harness/schema was used?
3. What exact command was run?
4. What fixture/input was measured?
5. Which Python/platform environment produced the result?
6. How many runs/warmups/failures occurred?
7. What may and may not be concluded from the result?

Phase B must add source-SHA and reproducibility identity before current-head
numbers are treated as publishable.

## Phase B measurement targets

The next phase should measure, without silently enabling external providers:

- local deterministic smoke latency;
- controlled `/v1/decide` route latency;
- Bind-boundary/current-governance-recheck overhead;
- TrustLog append latency, JSONL and PostgreSQL separated where available; and
- controlled Decision-to-Effect timing components.

Each measurement requires its own scope statement. A single local microbenchmark
must not be used as a proxy for the whole Decision-to-Effect path.

## Non-claims

Benchmark Rebaseline does not by itself prove:

- production latency or production SLA;
- customer-environment performance;
- real customer credentials/endpoints;
- independent production infrastructure validation;
- third-party certification;
- regulatory approval; or
- superiority over named vendors.

## Phase A exit

Phase A is complete when this contract and its regression guard pass full CI.
No benchmark value is changed in this phase.

Next:

**Phase B — Current-head deterministic measurements.**
