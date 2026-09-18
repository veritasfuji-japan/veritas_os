# Reconciliation-Capable Execution Profile — Reproducible Proof v1

Status: **CONTROLLED PROOF DEFINED / PRODUCTION CLAIM FALSE**

## Purpose

This proof validates the policy-gated execution profile introduced after the
downstream reconciliation capability architecture decision.

It is intentionally separate from the frozen Controlled Execution Proof v1.
The frozen proof remains the baseline claim. This proof demonstrates an
additional profile in which deployment-controlled policy requires authoritative
downstream reconciliation capability, and that capability must be represented by
a runtime-sealed verified proof before native v2 authorization consumption.

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
- verifier-sealed capability proof hash;
- verifier trust-policy identity/hash;
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

- missing verified capability proof;
- raw capability evidence without a sealed proof; and
- verifier-sealed `HEURISTIC_ONLY` capability evidence.

For both cases:

- the authorization remains unconsumed;
- no consumption record is stored;
- the transport path is not entered; and
- no sandbox event is added.

The workflow also runs the verifier trust-boundary tests plus the focused
reconciliation-capability gate matrix covering caller-constructed proof
lookalikes, trust-policy mismatch, expiry, endpoint/configuration drift, verifier
mismatch, evidence-digest mismatch, incomplete required policy, and untyped
request-like policy downgrade attempts.

## Verifier trust-boundary proof

The proof now distinguishes three objects:

1. raw `ReconciliationCapabilityEvidence`, which is descriptive and
   self-non-authenticating;
2. `ReconciliationCapabilityVerifierTrustPolicy`, supplied from the deployment
   trust boundary; and
3. `VerifiedReconciliationCapabilityEvidence`, produced only through
   `verify_reconciliation_capability_evidence_to_proof(...)`.

The focused proof demonstrates that copying the serialized fields of a valid
verified proof does not recreate its process-local runtime seal. The copied
lookalike is rejected before authorization consumption.

This seal is not claimed to be a durable cross-process credential. Another
process must re-establish verification through the deployment-controlled
verifier boundary before relying on the capability.

## Post-dispatch semantics

The policy-gated profile does not alter the existing uncertainty contract.

The fault path proves:

```text
required authoritative reconciliation capability
-> deployment-controlled verifier
-> runtime-sealed verified capability proof
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
> authoritative reconciliation capability, raw or unsealed evidence cannot
> satisfy the gate. A current authoritative query capability must first be
> verified through the deployment-controlled verifier boundary and represented
> by a runtime-sealed proof before the existing fail-closed Decision-to-Effect
> path may proceed, without weakening `EFFECT_UNKNOWN`, reconciliation, retry,
> receipt, or recovery semantics.
