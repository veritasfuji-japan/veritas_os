# External Proof End-to-End Rehearsal

## Status

Synthetic, non-executing rehearsal only.

This path prepares the first external interoperability proof without claiming
that live NeoMundi interoperability has already been established.

## Purpose

The rehearsal composes the existing NeoMundi RGC v0.2 verification path with
the existing external-measurement governance closure path in one trusted
process:

```text
synthetic signed RGC v0.2
→ NeoMundiRgcV02Verifier
→ provider-neutral ExternalMeasurementEvidence trust boundary
→ runtime-sealed VerifiedExternalMeasurementEvidence
→ independent Policy evaluation
→ independent AuthorityEvidence
→ independent Human Approval
→ CommitBoundaryEvaluator
→ reviewer-facing governance closure packet
```

The key integration property is that the runtime-sealed
`VerifiedExternalMeasurementEvidence` object is forwarded directly to the
closure harness. The JSON representation produced for audit is **not** read
back and treated as trusted runtime state.

## Runtime seam

`verify_neomundi_real_observation_runtime(...)` exposes the same-process
runtime result used by the existing reproducible PoC runner. It contains:

- the sealed `VerifiedExternalMeasurementEvidence` object;
- the exact `ExternalMeasurementTrustPolicy` used to verify it;
- the verification report;
- the audit serialization of the verified evidence;
- the evidence manifest.

`run_neomundi_real_observation_poc(...)` remains backward compatible and emits
the same JSON-compatible output shape as before.

## Rehearsal composition

`run_external_proof_e2e_rehearsal(...)` forwards the sealed proof and exact
trust policy directly into `close_verified_external_measurement_governance(...)`.
It then emits:

1. measurement verification outputs;
2. the non-executing governance closure result;
3. a rehearsal manifest linking the measurement proof hash to the governance
   packet hash through a deterministic chain hash.

## Required independence

External measurement remains evidence only.

```text
ExternalMeasurementEvidence
!= AuthorityEvidence
!= HumanApproval
!= BindAuthorization
!= execution permission
```

The rehearsal therefore requires Policy, AuthorityEvidence, and Human Approval
to be supplied and evaluated independently. A verified measurement cannot
replace any missing governance prerequisite and cannot override a refusing
policy result.

## Fail-closed rehearsal coverage

The synthetic tests cover:

- valid independent Policy + Authority + Human Approval → non-executing commit;
- missing Authority → block;
- missing Human Approval → block;
- independent Policy refusal → refuse;
- tampered signed observation → reject before governance closure;
- stale observation → reject before governance closure;
- replayed observation → reject before governance closure;
- mismatched trusted JWKS → reject before governance closure.

## Non-execution boundary

This rehearsal does not:

- create `BindAuthorization`;
- resolve or access credentials;
- dispatch network traffic;
- perform an external effect;
- publish a production BindReceipt or Outcome;
- change Reconciliation semantics;
- reopen the frozen Decision-to-Effect architecture.

A `commit` result means only non-executing governance admissibility for the
supplied rehearsal inputs.

## Non-claims

Successful rehearsal does **not** establish:

- live NeoMundi interoperability;
- production readiness;
- customer deployment;
- independent third-party validation;
- certification or regulatory approval;
- execution authority;
- a real external effect.

## External PoC #1 transition

When a real partner-produced signed RGC v0.2 observation and matching public
trust material are available, the synthetic observation can be replaced at the
verification input while preserving the same proof and governance boundaries.
The resulting evidence must still be reviewed and preserved before any live
interoperability claim is made.
