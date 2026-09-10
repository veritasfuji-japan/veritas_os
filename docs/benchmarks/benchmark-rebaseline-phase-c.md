# TASK-011 Benchmark Rebaseline — Phase C

## Purpose

Phase C regenerates the repository's evidence-axis benchmark under the frozen
TASK-011 contract and binds the resulting evidence package to the exact measured
Git commit.

The canonical benchmark surfaces are unchanged:

- harness: `veritas_os/scripts/evidence_benchmark.py`
- metrics: `veritas_os/benchmarks/evidence/metrics_definition.yaml`
- schema: `veritas_os/benchmarks/evidence/output_schema.json`
- fixture: `veritas_os/benchmarks/evidence/fixtures/sample_cases.jsonl`

Canonical command:

```bash
python -m veritas_os.scripts.evidence_benchmark \
  --fixtures veritas_os/benchmarks/evidence/fixtures/sample_cases.jsonl \
  --output /tmp/veritas-evidence-benchmark.json
```

## What is measured

The two repository-controlled fixture cases are scored on the five existing
axes:

1. auditability
2. fail-closed safety
3. governance change control
4. replay/divergence visibility
5. TrustLog integrity

No external model or provider is invoked by the benchmark workload.

## Source-bound evidence

`.github/workflows/benchmark-rebaseline-phase-c.yml` runs on pull requests,
pushes to `main`, and manual dispatch. It checks out the exact measured source,
runs the canonical harness, validates the raw JSON against the frozen output
schema, records SHA-256 identities for the harness/metrics/schema/fixture, and
uploads both the raw report and a run manifest.

For a merged Phase C baseline, the authoritative current-head evidence is the
GitHub Actions artifact produced by the push-to-main run. A pull-request artifact
is review evidence for the PR head, not the final merged-main baseline.

## Claim boundary

The `veritas` and `generic` entries in `sample_cases.jsonl` are synthetic,
repository-controlled fixtures. The Phase C result may be described as
**synthetic fixture scoring under fixed metric definitions**.

It must not be described as:

- independent competitive validation;
- superiority over a named vendor;
- production readiness;
- production latency or a production SLA;
- customer-environment performance;
- third-party certification or regulatory approval.

The benchmark does not change Authorization, Bind, External Effect,
Reconciliation, BindReceipt, or Outcome runtime semantics.

## Completion

Phase C is complete only after the workflow is merged, the push-to-main run
succeeds, the artifact is bound to that exact main SHA, full required CI remains
green, and the frozen Decision-to-Effect proof remains passing.

After that, TASK-011 can be closed and the roadmap moves to External PoC
packaging/execution.
