# Reconciliation-Capable Execution Profile — Reproducible Proof v1

Status: **CONTROLLED PROOF DEFINED / PRODUCTION CLAIM FALSE**

## Purpose

This proof validates the policy-gated execution profile introduced after the
downstream reconciliation capability architecture decision.

It is intentionally separate from the frozen Controlled Execution Proof v1.
The frozen proof remains the baseline claim. This proof demonstrates an
additional profile in which deployment-controlled policy requires authoritative
downstream reconciliation capability before native v2 authorization consumption.

## Dedicated workflow

`.github/workflows/reproducible-reconciliation-capable-execution-profile.yml`

Runtime artifacts:

- `artifacts/reconciliation-capable-execution-profile/report.json`
- `artifacts/reconciliation-capable-execution-profile/evidence.json`

The artifacts are regenerated for the exact source SHA under test and uploaded by
GitHub Actions.

## Positive proof

The workflow proves two full controlled Decision-to-Effect paths with
`AUTHORITATIVE_QUERY` capability required before authorization consumption:

1. normal response observed; and
2. response lost after remote persistence.

For each positive path, the proof binds:

- verified decision lineage;
- exact ExecutionIntent;
- native v2 authorization;
- reconciliation capability policy identifier;
- reconciliation capability evidence digest;
- current endpoint identity;
- current target configuration;
- verifier identity and verifier-policy hash;
- PostgreSQL consumption identity;
- effect-state lineage;
- read-only reconciliation evidence; and
- retrospective BindReceipt / Outcome lineage.

The gate result remains audit context. It does not itself create execution
authority.

## Fail-closed proof

The same workflow demonstrates with real PostgreSQL that a policy requiring
authoritative reconciliation rejects:

- missing capability evidence; and
- `HEURISTIC_ONLY` capability evidence.

For both cases:

- the authorization remains unconsumed;
- no consumption record is stored;
- the transport path is not entered; and
- no sandbox event is added.

The workflow also runs the focused reconciliation-capability gate matrix covering
expiry, endpoint/configuration drift, verifier mismatch, evidence-digest mismatch,
incomplete required policy, and untyped request-like policy downgrade attempts.

## Post-dispatch semantics

The policy-gated profile does not alter the existing uncertainty contract.

The fault path proves:

```text
required authoritative reconciliation capability
-> authorization consumption
-> one TLS POST
-> response loss
-> EFFECT_UNKNOWN
-> lookup outage
-> EFFECT_UNKNOWN
-> retry prohibited
-> lookup recovery
-> CONFIRMED_EFFECT
-> receipt/outcome
```

A second POST is not permitted.

## Machine-readable proof result

The generated report uses:

`CONTROLLED_RECONCILIATION_CAPABLE_EXECUTION_PROFILE_V1`

A passing report requires every member of `proof_conjunction` to be true.

The report explicitly keeps these false:

- `production_claim`
- `production_reconciliation_capability_proven`
- `universal_downstream_reconcilability_proven`
- `exactly_once_external_delivery_proven`
- `production_validation_proven`

## Non-claims

This proof does not establish:

- production readiness;
- customer endpoint interoperability;
- universal downstream reconciliation support;
- exactly-once external delivery;
- independently operated production infrastructure;
- external UTC production trust; or
- regulatory approval/certification.

## Resulting statement

A passing workflow supports the following narrow claim:

> In the controlled VERITAS profile, when deployment policy requires
> authoritative reconciliation capability, missing or heuristic-only capability
> is rejected before authorization consumption, while a current authoritative
> query capability permits the existing fail-closed Decision-to-Effect path to
> proceed without weakening `EFFECT_UNKNOWN`, reconciliation, retry, receipt, or
> recovery semantics.
