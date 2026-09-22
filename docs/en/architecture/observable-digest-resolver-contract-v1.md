# Observable Digest Resolver Contract v1

## 1. Status

- **Scope:** contract formalization only.
- **Runtime resolver behavior:** not activated.
- **Network / store access:** not added.
- **Authority / execution semantics:** unchanged.
- **Default operator surface:** unchanged.

This document defines the machine-readable boundary for a future observable-digest resolver. It does not implement or authorize resolver behavior.

The corresponding schema is:

`schemas/observable_digest_resolver_contract_v1.schema.json`

## 2. Core invariant

The resolver boundary must preserve:

```text
Resolution Evidence
!= Boundary Validation
!= Admissibility
!= Authority
!= Execution Permission
```

A resolver may report what it observed while attempting to resolve a locator.

It must not silently manufacture:

- Authority;
- certainty beyond the evidence it actually observed;
- policy admissibility;
- Human Approval;
- execution permission;
- remediation;
- an external-effect claim.

`RESOLVED` means only that the resolver reports a digest value for the supplied locator under the active resolver profile.

`RESOLVED` does **not** mean:

- the digest matches an expected digest;
- the material is fresh;
- the material is authentic;
- boundary validation passed;
- policy admits the action;
- Authority exists;
- Human Approval exists;
- Bind is allowed;
- execution permission changed.

## 3. Relationship to the existing v1 locator contract

The existing v1 rule remains locator-first:

- `observable_digest_ref` is a separate-store locator/reference;
- inline digest payload text is not the canonical meaning of `observable_digest_ref`;
- legacy compatibility behavior does not widen the canonical contract.

The existing helper `_resolve_observable_digest_ref` in `wat_events.py` selects and normalizes locator input. It is **not** the external/store resolver behavior defined by this contract.

Formalizing this contract does not activate any new resolver.

## 4. Request contract

A resolver request contains only explicit caller-supplied context required to identify the resolution attempt:

- `request_id`
- `locator`
- `caller_id_hash`
- `requested_at`
- `resolver_profile`

The resolver request intentionally does **not** contain:

- expected digest;
- policy decision;
- admissibility result;
- execution permission;
- remediation instruction.

Expected-digest comparison and boundary validation remain downstream responsibilities.

The result must echo the same `request_id` and `locator` exactly. A future implementation must not silently substitute either value.

## 5. Result contract

The result has exactly two resolution states:

```text
RESOLVED
UNRESOLVED
```

### RESOLVED

A `RESOLVED` result must include:

- the original `request_id`;
- the original `locator`;
- `resolver_id`;
- `observed_at`;
- one SHA-256 `resolved_digest`;
- optional `evidence_ref`;
- an empty `failure_predicates` list;
- the required non-amplification guarantees.

No other conclusion follows from `RESOLVED`.

### UNRESOLVED

An `UNRESOLVED` result must include:

- the original `request_id`;
- the original `locator`;
- `resolver_id`;
- `observed_at`;
- `resolved_digest = null`;
- optional `evidence_ref`;
- at least one resolver-scoped typed failure predicate;
- the required non-amplification guarantees.

`UNRESOLVED` does not itself authorize retry, escalation, remediation, or execution.

## 6. Resolver-scoped failure predicates

The contract permits only the following existing typed predicates at the resolver boundary:

- `LOCATOR_MISSING`
- `LOCATOR_MALFORMED`
- `RESOLUTION_FAILED`
- `AUTHZ_DENIED`
- `SCHEMA_MISMATCH`
- `UNKNOWN_TRANSIENT`

The resolver contract does **not** emit or assert these downstream validation predicates:

- `DIGEST_MISMATCH`
- `BOUNDARY_VALIDATION_FAILURE`
- `REPLAY_DUPLICATE`
- `STALE_DIGEST`

Those require evidence or comparisons beyond locator resolution and remain separate responsibilities.

The existing deterministic failure mapper may later classify typed predicates supplied by a resolver implementation. This contract does not invoke that mapper and does not add retry or remediation behavior.

## 7. Access authorization is not execution Authority

`AUTHZ_DENIED` refers only to authorization to access the resolver/store boundary.

A resolver/store access check is not VERITAS execution Authority.

Therefore:

```text
resolver access authorized
!= execution authorized
```

and:

```text
resolver access denied
!= execution decision
```

The resolver contract cannot create, restore, consume, or transfer Bind authorization.

## 8. Required non-amplification guarantees

Every result must carry the following machine-readable constants:

```json
{
  "authority_created": false,
  "execution_permission_changed": false,
  "digest_match_asserted": false,
  "boundary_validation_asserted": false,
  "uncertainty_erased": false,
  "remediation_executed": false
}
```

These fields are contract invariants, not configurable options.

A future resolver implementation that needs to claim digest match, freshness, authenticity, boundary validation, remediation, or execution effects must do so in a separate downstream contract with separate evidence and review.

## 9. Uncertainty rule

A resolver must not convert missing or ambiguous evidence into certainty.

If the implementation cannot establish a resolved digest under its own bounded contract, it must remain `UNRESOLVED` with typed failure evidence.

Free-text exception messages must not become contract semantics.

A later successful resolution must not silently erase an earlier unresolved or uncertain audit record.

## 10. Evidence reference

`evidence_ref` is an optional reference to evidence supporting the resolver observation.

Its presence does not establish:

- authenticity;
- trustworthiness;
- freshness;
- completeness;
- independent attestation.

Those properties require separate validation under an explicit trust/security contract.

## 11. Security review required before behavioral activation

This document does not approve a runtime resolver.

Before resolver behavior may become active, a separate security review must explicitly cover at least:

- permitted locator schemes;
- SSRF / local-file / loopback / metadata-service protections;
- DNS and redirect handling;
- tenant and scope isolation;
- resolver identity and store-access authorization;
- network egress restrictions;
- timeout and bounded retry policy;
- response-size and resource limits;
- secret handling and redaction;
- trust-root / authenticity handling;
- freshness and replay boundaries;
- evidence-reference validation;
- failure injection and fail-closed behavior;
- audit emission;
- no implicit fallback to unsafe locator types.

Until that review is complete, this contract remains non-behavioral.

The pre-behavior adversarial security review is now frozen at:

`docs/en/security/observable-digest-resolver-security-review-v1.md`

with machine-readable threat matrix:

`security/observable_digest_resolver_security_review_v1.json`

That review currently leaves behavioral activation **BLOCKED**. It does not itself authorize implementation or runtime activation.

## 12. Explicit non-scope

This contract adds no:

- locator fetch implementation;
- HTTP client;
- filesystem resolver;
- object-store resolver;
- database resolver;
- DNS behavior;
- credential lookup;
- retry loop;
- caching;
- deduplication;
- TrustLog write;
- policy decision;
- Human Approval;
- Bind authorization;
- execution permission;
- remediation;
- `/v1/decide` behavior change;
- default operator UI widening.

## 13. Activation gate

Resolver behavior may be added only in a later, separate change after:

1. this contract is reviewed;
2. the security boundary is reviewed;
3. supported locator schemes and trust assumptions are explicitly frozen;
4. negative tests are defined for access, network, scope, timeout, malformed response, and uncertainty handling;
5. activation preserves the invariant that resolution evidence cannot manufacture Authority or execution permission.

## 14. Acceptance criteria for this contract-only step

This contract formalization is complete when:

- the locator-first v1 contract remains unchanged;
- request and result shapes are machine-readable;
- `RESOLVED` remains evidence-only;
- resolver-scoped failure predicates are bounded to existing typed predicates;
- downstream validation predicates remain outside resolver scope;
- non-amplification guarantees are mandatory and false;
- uncertainty cannot be silently erased;
- runtime resolver behavior remains absent;
- existing runtime decisions remain unchanged.
