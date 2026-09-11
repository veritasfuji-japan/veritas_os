# External Measurement Governance Closure PoC

## Purpose

This PoC closes the governance path immediately after a runtime-sealed
`VerifiedExternalMeasurementEvidence` object exists, while preserving the
fundamental boundary that external measurement evidence is not execution
authority.

The harness is intentionally non-executing. It revalidates the sealed external
measurement, then evaluates independently supplied Policy, AuthorityEvidence,
and Human Approval through the existing VERITAS commit-boundary machinery. It
emits a deterministic reviewer-facing closure packet.

## Flow

```text
VerifiedExternalMeasurementEvidence
        |
        | revalidate trust / freshness / proof integrity
        v
External measurement evidence reference
        |
        +------------------------------+
        |                              |
        |  independent Policy          |
        |  independent Authority       |
        |  independent Human Approval  |
        |                              |
        +--------------+---------------+
                       |
                       v
              CommitBoundaryEvaluator
                       |
                       v
        non-executing governance result
                       |
                       v
        deterministic closure packet
```

## Core invariant

```text
ExternalMeasurementEvidence
!= AuthorityEvidence
!= HumanApproval
!= BindAuthorization
!= execution permission
```

A valid external signature, a `within_bounds` measurement, or an advisory
recommendation cannot satisfy missing AuthorityEvidence, missing Human Approval,
or an independently refusing policy evaluation.

## What the harness evaluates

The harness accepts:

- one runtime-sealed `VerifiedExternalMeasurementEvidence`;
- the exact `ExternalMeasurementTrustPolicy` used to revalidate it;
- one `ActionClassContract`;
- independently produced `AuthorityEvidence` or no authority;
- independently produced Human Approval state;
- an independent policy evaluation with an explicit `policy_snapshot_id` and
  boolean `admissible` result;
- requested scope and required-evidence presence/freshness metadata.

It then reuses the existing `CommitBoundaryEvaluator` and its
`RuntimeAuthorityValidator` predicates.

A resulting `commit` means only that the supplied governance inputs were
admissible at this non-executing PoC review boundary. It does **not** mean that
VERITAS issued a `BindAuthorization`, resolved credentials, dispatched a
request, or produced an external effect.

## Closure packet

The packet records:

- external measurement evidence ID, provider ID, artifact ID;
- measurement evidence hash and verification proof hash;
- trust policy ID/hash and replay key;
- independent policy evaluation ID, snapshot, result, and reasons;
- AuthorityEvidence ID/hash when supplied;
- Human Approval receipt ID/hash and approval state;
- commit-boundary governance outcome and failure/refusal/escalation basis;
- deterministic packet hash;
- explicit non-execution claim-boundary flags.

The claim-boundary section fixes the following values:

```text
external_measurement_converted_to_authority = false
external_measurement_converted_to_human_approval = false
external_measurement_converted_to_bind_authorization = false
external_measurement_directly_controls_governance_outcome = false
bind_authorization_created = false
credentials_accessed = false
network_dispatch_performed = false
external_effect_performed = false
```

## Runtime-sealed proof boundary

`VerifiedExternalMeasurementEvidence` is intentionally revalidated as a
runtime-sealed object. A JSON serialization of that proof is useful for review
and reproducibility, but this PoC does not reinterpret serialized JSON as
portable trust.

For the first real NeoMundi run, the correct composition is therefore:

```text
real signed RGC v0.2
-> NeoMundi provider verification
-> generic ExternalMeasurementEvidence trust boundary
-> runtime-sealed VerifiedExternalMeasurementEvidence
-> this governance closure harness in the same trusted process
-> reviewer-facing closure packet
```

The checked-in #2227 verification outputs remain reviewer artifacts; they are
not silently promoted back into runtime trust.

## Tests

The deterministic synthetic tests cover:

1. valid independent Policy + Authority + Human Approval -> non-executing
   `commit`;
2. verified external measurement with missing Authority -> `block`;
3. verified external measurement with missing Human Approval -> `block`;
4. independently refusing policy evaluation -> `refuse` even when the external
   measurement is verified;
5. tampered runtime-sealed external measurement proof -> fail closed before
   governance evaluation.

## Non-goals

This PoC does not:

- establish live NeoMundi interoperability;
- issue `BindAuthorization`;
- resolve or use credentials;
- perform Bind execution;
- dispatch network traffic;
- create an external effect;
- change BindReceipt / Outcome / Reconciliation semantics;
- modify the frozen Decision-to-Effect architecture;
- claim production readiness, certification, or third-party validation.

Live interoperability remains unproven until a real partner-produced signed
observation is independently verified and this closure path is executed with
that runtime-sealed proof.
