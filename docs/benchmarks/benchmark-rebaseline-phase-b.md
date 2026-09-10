# TASK-011 Benchmark Rebaseline — Phase B

## Purpose

Phase B produces a reproducible, source-SHA-bound measurement for the canonical
local deterministic benchmark defined by the Phase A contract.

This phase does not change runtime governance behavior and does not widen the
benchmark claim boundary.

## Baseline

Phase A merged in product PR #2222.

Phase A merge commit:

`ad92ec663b962183327b1b96192378fd562da794`

Frozen controlled Decision-to-Effect anchor:

`ada46f2fe324dd3cbcff6be59d56c4f75c4a6bdc`

## Canonical command

```bash
python scripts/benchmarks/run_performance_metrics.py --iterations 100 --warmup 10 --output docs/en/benchmarks/local-performance-metrics.latest.json
```

The harness now attaches provenance to the existing `performance_metrics.v1`
payload without changing the timed code path. The measured section remains the
same deterministic local fixture path.

## Source identity

Every Phase B artifact records:

- full measured source commit SHA;
- run timestamp;
- exact command;
- Python/platform identity;
- iteration and warmup counts;
- harness path and SHA-256;
- embedded fixture/scenario identity;
- raw metrics/counters and summary;
- failure count;
- claim boundary; and
- reproduction instructions.

The harness resolves the measured SHA from the checked-out Git tree unless an
explicit full SHA is supplied. It fails rather than silently promoting an
unbound result when source identity cannot be resolved.

## CI measurement protocol

`.github/workflows/benchmark-rebaseline-phase-b.yml` runs on pull requests,
pushes to `main`, and manual dispatch.

For pull requests, the workflow checks out and measures the PR head rather than
implicitly relying on the synthetic pull-request merge SHA.

After merge, the push-to-main run measures the exact pushed `main` commit. It
validates the Phase A required fields, source SHA, canonical command, CPython
3.12 runtime family, zero failures, and the non-production claim boundary.

The workflow uploads two files under a source-SHA-specific Actions artifact:

1. `local-performance-metrics.<source-sha>.json`
2. `run-manifest.json`

The manifest additionally records the benchmark artifact SHA-256 and GitHub
Actions run identity.

## Existing committed May 2026 artifact

`docs/en/benchmarks/local-performance-metrics.latest.json` remains the historical
May 2026 pre-rebaseline result in the repository. It lacks measured source SHA
and remains classified as:

`STALE_PRE_REBASELINE_REFERENCE`

It must not be represented as current-head performance.

The authoritative Phase B current-head evidence is the source-bound GitHub
Actions artifact produced by a successful push-to-main workflow run.

## Claim boundary

Phase B measures a lightweight deterministic local function path only.

It does not establish:

- production latency;
- a production SLA;
- customer-environment performance;
- real customer endpoint performance;
- external provider latency;
- third-party certification;
- regulatory approval; or
- superiority over named vendors.

No external LLM/API call is enabled by this benchmark workflow.

## Runtime integrity

No authorization, Bind, external-effect, reconciliation, receipt/outcome,
credential, TrustLog runtime, or network semantics are changed for benchmark
performance.

If the benchmark reveals an optimization opportunity, that optimization must be
a separately reviewed runtime change.

## Exit condition

Phase B is complete only after the workflow is merged and a push-to-main run
successfully produces a source-SHA-bound artifact with zero benchmark failures,
while required repository CI and the frozen Decision-to-Effect proof remain
green.

The next phase is Phase C — Evidence Benchmark Rebaseline.
