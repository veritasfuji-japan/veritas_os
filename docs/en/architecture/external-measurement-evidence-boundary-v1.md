# External Measurement Evidence Boundary v1

## Status

Provider-neutral interoperability boundary for externally produced measurement evidence.

This boundary is intentionally independent of any one measurement provider or artifact format. Provider-specific adapters are layered on top of this contract in separate changes.

## Purpose

VERITAS needs to consume measurements produced outside its own trust domain without allowing a signed external artifact to become execution authority.

The boundary is:

```text
Untrusted external artifact
        ↓
VERITAS-controlled provider-specific verifier
        ↓
provider / verifier trust-policy binding
        ↓
normalized ExternalMeasurementEvidence
        ↓
freshness + expiry + semantic consistency + replay checks
        ↓
VerifiedExternalMeasurementEvidence
        ↓
separate VERITAS policy / authority / approval / execution evaluation
```

The core invariant is:

```text
ExternalMeasurementEvidence
!= AuthorityEvidence
!= HumanApproval
!= BindAuthorization
!= GovernanceDecision
```

A valid signature proves only what the approved provider-specific verifier and the independently configured VERITAS trust policy establish. It does not grant permission to act.

## Runtime types

`veritas_os.governance.external_measurement_evidence` defines:

- `ExternalMeasurementEvidence`
- `ExternalMeasurementProviderVerificationResult`
- `ExternalMeasurementProviderVerifier`
- `ApprovedExternalMeasurementProvider`
- `ExternalMeasurementTrustPolicy`
- `ExternalMeasurementReplayGuard`
- `VerifiedExternalMeasurementEvidence`
- `verify_external_measurement_artifact_to_evidence(...)`
- `validate_verified_external_measurement_evidence(...)`

## Provider-neutral normalized evidence

The normalized evidence records only measurement-domain facts and provenance:

- VERITAS evidence id
- provider id
- provider artifact id/type/version
- verified payload hash
- observation / issuance / expiry timestamps
- replay token
- measured scope
- optional measurement coverage
- provider-specific semantic facts represented as data
- provenance
- non-authoritative metadata

No field in this object grants authority, satisfies human approval, creates a Bind authorization, or makes an ALLOW/DENY governance decision.

## Provider-specific verifier seam

A provider adapter implements `ExternalMeasurementProviderVerifier`.

The verifier is responsible for native-format concerns such as:

- provider schema/version validation
- canonicalization rules
- payload reconstruction
- payload/hash verification
- provider signature verification
- provider key selection
- provider-specific semantic consistency

Those concerns do not belong in the provider-neutral boundary.

The generic boundary does not trust an artifact-supplied public key or trust declaration. The verifier result must match an independently configured `ExternalMeasurementTrustPolicy` entry for the provider/verifier pair.

## VERITAS-controlled checks

After provider-specific verification succeeds, the generic boundary independently requires:

1. approved provider/verifier binding;
2. exact verifier trust-level / policy identity match;
3. non-empty evidence, provider, artifact, version, and replay identities;
4. SHA-256-shaped payload identity;
5. non-empty measured scope;
6. measurement coverage in `[0.0, 1.0]` when coverage is supplied;
7. timezone-aware observation / issuance / expiry timestamps;
8. observation and issuance not beyond configured future skew;
9. issuance not before observation;
10. observation not older than the configured maximum age;
11. expiry present when policy requires it and not expired;
12. provider-specific semantic consistency explicitly verified;
13. atomic replay consumption through `ExternalMeasurementReplayGuard`.

Any failure is fail-closed and no verified evidence object is emitted.

## Replay semantics

Replay protection uses an atomic `consume_once(...)` seam. The replay key binds:

- provider id
- artifact id
- payload hash
- provider replay token

The production replay implementation is intentionally outside this first provider-neutral slice. A provider adapter or deployment composition must supply a durable implementation appropriate to its execution environment.

## Verified proof semantics

`VerifiedExternalMeasurementEvidence` binds the normalized evidence to:

- evidence content hash
- signature key / algorithm identity reported by the approved verifier
- verifier id / trust level / policy identity
- VERITAS trust-policy identity and hash
- verification timestamp and reason
- replay key
- deterministic verification proof hash

A serialized or caller-constructed verified object is not portable trust. Runtime revalidation checks both the proof hash and the process-local sealed-proof registry, following the same defensive pattern used by other strict VERITAS proof boundaries.

## Explicit non-goals for PR1

This first slice does **not** implement:

- a NeoMundi-specific adapter
- RGC schema fields or status mapping
- JWKS lookup
- any provider-specific signature backend
- external network calls
- AuthorityEvidence conversion
- HumanApproval satisfaction
- Bind authorization issuance
- direct ALLOW/DENY mapping
- changes to the frozen Decision-to-Effect execution semantics

Provider-specific integration belongs in a separate PR.

## Frozen execution boundary

This module is an evidence-ingress boundary only. It does not modify:

- native v2 authorization
- single-use authorization consumption
- current governance rechecks
- credential resolution
- durable dispatch intent
- external-effect retry semantics
- `EFFECT_UNKNOWN`
- read-only reconciliation
- BindReceipt / Outcome publication
- crash recovery

The controlled Decision-to-Effect Architecture Freeze remains intact.

## Next step

After this provider-neutral boundary is reviewed and merged, the next isolated change is a concrete provider adapter that converts one provider's independently verified native measurement artifact into `ExternalMeasurementEvidence` without expanding execution authority.
