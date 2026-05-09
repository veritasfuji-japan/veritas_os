# One-Day PoC Evidence Pack

- This is a reviewer-facing evidence pack for a One-Day PoC.
- It summarizes what to inspect, what evidence to collect, and what counts as a successful local/configured PoC walkthrough.
- It is not a production SLA.
- It is not third-party certified.
- It is not a customer environment measurement.
- It does not certify EU AI Act compliance.
- External LLM/provider latency and cost are not measured unless providers are intentionally enabled and separately recorded.

## Purpose

Provide a compact reviewer-facing checklist for One-Day PoC validation so customers, investors, and review teams can quickly assess governance behavior and evidence quality without over-claiming production readiness.

## What this PoC demonstrates

- A regulated or sensitive action can be stopped before commit when required authority/evidence is missing.
- The decision path can remain reviewable through governance/audit traces.
- Reviewer-facing docs distinguish deterministic local metrics from HTTP PoC benchmarks.
- The system can present governance boundaries before claiming production readiness.

## What this PoC does not prove

- It does not prove production latency.
- It does not prove production availability.
- It does not prove customer-environment performance.
- It does not prove legal compliance by itself.
- It does not replace legal, security, or regulatory review.
- It does not certify EU AI Act compliance.
- It does not measure provider latency or cost unless providers are explicitly enabled and separately measured.

## Evidence checklist

| Evidence item | What to inspect | Expected result | Link |
|---|---|---|---|
| Local deterministic performance artifact | Latest deterministic local benchmark markdown snapshot | Local deterministic metrics are visible with explicit non-claim boundaries | [`docs/en/benchmarks/local-performance-metrics.latest.md`](../benchmarks/local-performance-metrics.latest.md) |
| Local deterministic performance summary | Latest deterministic local benchmark JSON snapshot | Machine-readable deterministic metrics and notes are present | [`docs/en/benchmarks/local-performance-metrics.latest.json`](../benchmarks/local-performance-metrics.latest.json) |
| One-Day PoC performance benchmark doc | Local/configured HTTP PoC benchmark guidance and boundaries | Reviewer can separate HTTP PoC benchmark data from deterministic local artifacts | [`docs/en/poc/one-day-poc-performance-report.md`](one-day-poc-performance-report.md) |
| Bind / governance boundary documentation | Governance boundary and bind admissibility explanation | Reviewer can identify pre-commit boundary and policy/evidence expectations | [`docs/en/architecture/bind-boundary-governance-artifacts.md`](../architecture/bind-boundary-governance-artifacts.md) |
| TrustLog / audit trace documentation | Audit and traceability controls for review | Reviewer can trace decisions and audit linkage path | [`docs/en/architecture/authority-evidence-vs-audit-log.md`](../architecture/authority-evidence-vs-audit-log.md) |
| README / README_JP entry points | Top-level reviewer entry points | Reviewer can discover EN/JA PoC evidence resources quickly | [`README.md`](../../../README.md) / [`README_JP.md`](../../../README_JP.md) |
| Documentation map | EN/JA mapping and canonical-language guidance | Reviewer can confirm EN canonical and JA explanatory mapping | [`docs/DOCUMENTATION_MAP.md`](../../DOCUMENTATION_MAP.md) |
| Any demo scenario docs already present in repo | Existing walkthrough and reviewer-pack documents | Reviewer can run scenario walkthrough and compare outcome/evidence paths | [`docs/en/poc/one-day-poc-walkthrough.md`](one-day-poc-walkthrough.md), [`docs/en/poc/one-day-poc-reviewer-pack.md`](one-day-poc-reviewer-pack.md), [`docs/en/poc/sample-one-day-poc-evidence.md`](sample-one-day-poc-evidence.md) |

## Suggested walkthrough scenarios

1. Missing authority/evidence blocks sensitive action before commit.
2. Allowed action proceeds when required policy/evidence is present.
3. Audit/TrustLog path remains reviewable.
4. Reviewer compares deterministic local artifact vs HTTP PoC benchmark.
5. Operator explains non-claim boundaries clearly.

## Success criteria

- The reviewer can identify the commit boundary.
- The reviewer can identify why an action was blocked or allowed.
- The reviewer can locate the relevant evidence/audit path.
- The reviewer can distinguish local deterministic metrics from HTTP PoC benchmark output.
- The reviewer does not leave with an unsupported SLA/compliance/certification claim.

## Failure criteria

- The system appears to claim production SLA from local metrics.
- The system appears to claim third-party certification without evidence.
- The reviewer cannot identify why an action was blocked or allowed.
- The audit trail or evidence path is unclear.
- Provider cost/latency is implied without explicit provider measurement.

## Artifacts to collect

- Screenshots of block/allow decision path.
- Relevant JSON outputs where available.
- Local deterministic metrics artifact.
- One-Day PoC benchmark output if run locally.
- Notes on environment, command, date, commit SHA.
- Any exceptions or failed checks.

## Reviewer notes

Use this pack together with existing validation and walkthrough docs. Keep all conclusions constrained to local/configured PoC evidence and explicitly state non-claims in verbal and written summaries.

## Related documents

- [`docs/en/poc/one-day-poc-reviewer-handoff-template.md`](one-day-poc-reviewer-handoff-template.md)
- [`docs/en/poc/one-day-poc-operator-runbook.md`](one-day-poc-operator-runbook.md) — Use the operator runbook when preparing and packaging reviewer-facing evidence.
- [`docs/en/benchmarks/local-performance-metrics.latest.md`](../benchmarks/local-performance-metrics.latest.md)
- [`docs/en/benchmarks/local-performance-metrics.latest.json`](../benchmarks/local-performance-metrics.latest.json)
- [`docs/en/benchmarks/performance-metrics.md`](../benchmarks/performance-metrics.md)
- [`docs/en/poc/one-day-poc-performance-report.md`](one-day-poc-performance-report.md)
- [`docs/INDEX.md`](../../INDEX.md)
- [`docs/DOCUMENTATION_MAP.md`](../../DOCUMENTATION_MAP.md)
