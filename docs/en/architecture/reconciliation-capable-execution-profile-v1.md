# Reconciliation-Capable Execution Profile v1

Status: **IMPLEMENTED POLICY-GATED PROFILE / FROZEN V1 UNCHANGED**

## 1. Purpose

This profile implements the architecture decision in
`reconciliation-capability-execution-eligibility-decision-v1.md` without
rewriting the frozen Controlled Execution Proof v1.

The profile adds one optional pre-consumption gate:

> When deployment-controlled policy requires authoritative downstream
> reconciliation, raw capability evidence must first be verified by a
> deployment-controlled verifier and sealed as
> `VerifiedReconciliationCapabilityEvidence` before the native v2 authorization
> may be consumed.

If the policy does not require the gate, the existing native v2 consumption
contract remains unchanged.

## 2. Enforcement point

The gate runs inside `consume_native_bind_authorization(...)` after the existing
current governance / risk / authority / approval rechecks and before
`consumption_store.consume_once(...)`.

The ordering is:

```text
native v2 authorization
-> current governance / risk / authority / approval rechecks
-> deployment-controlled reconciliation-capability policy
-> deployment-controlled capability verifier
-> runtime-sealed verified capability proof
-> current proof / target / trust recheck
-> fail closed if the required capability proof is absent or invalid
-> atomic authorization consumption
-> later pre-effect attempt ownership
-> credential resolution / dispatch path
```

A failed capability gate therefore occurs before the authorization consumption
write and before any external transport path can be entered.

## 3. Deployment-controlled policy

The runtime input is `ReconciliationCapabilityExecutionPolicy`.

When `require_authoritative_reconciliation=true`, the policy must provide:

- a non-empty policy identifier;
- the current target configuration digest;
- expected verifier identity;
- expected verifier policy identity;
- expected verifier policy hash;
- an independently supplied expected evidence digest;
- expected verifier trust-policy identifier; and
- expected verifier trust-policy hash.

The expected evidence digest is required so the capability artifact cannot
authenticate itself merely by repeating the expected verifier labels. The
verifier trust policy is independently bound as well, and the runtime accepts a
required capability only through a helper-created sealed proof. Reconstructing a
lookalike proof from serialized fields does not recreate the runtime seal.

A request or AI output is not a valid source for this policy object. The policy is
an executor/deployment trust input.

When `require_authoritative_reconciliation=false`, the policy carries no
capability trust anchors and the pre-existing consumption behavior is preserved.

## 4. Accepted capability

When the gate is required, raw evidence must first pass the deployment-controlled
verifier seam. The resulting verified proof must then remain structurally valid,
runtime-sealed, trust-policy bound, and currently admissible for the exact target.

The following classes can satisfy the gate:

- `AUTHORITATIVE_QUERY`
- `AUTHORITATIVE_EVIDENCE`

The following cannot:

- `HEURISTIC_ONLY`
- `UNAVAILABLE_OR_UNVERIFIED`

The gate also rejects:

- missing verified capability proof;
- raw evidence presented without a sealed proof;
- caller-constructed proof lookalikes without the runtime seal;
- missing or mismatched verifier trust policy;
- expired evidence;
- future-dated assessment;
- endpoint identity drift;
- target configuration drift;
- verifier / verifier-policy mismatch;
- evidence-digest mismatch; and
- incomplete or malformed required policy anchors.

## 4.1 Verified proof trust boundary

`ReconciliationCapabilityEvidence` remains an untrusted descriptive artifact.
Its embedded verifier fields are declarations, not proof of who performed the
verification.

The trusted path is:

```text
raw ReconciliationCapabilityEvidence
-> deployment-controlled ReconciliationCapabilityEvidenceVerifier
-> independently configured ReconciliationCapabilityVerifierTrustPolicy
-> verify_reconciliation_capability_evidence_to_proof(...)
-> VerifiedReconciliationCapabilityEvidence
-> current-target / trust-policy / runtime-seal validation
-> policy-gated authorization consumption
```

The runtime seal is intentionally process-local and is not a portable durable
credential. A serialized proof must be re-established through the verifier
boundary before another process relies on it.

## 5. Fail-closed result

A rejected gate produces a stable native consumption error and does not call the
atomic consumption write.

Therefore a rejected prerequisite creates no:

- consumed authorization;
- execution permission;
- retry permission;
- network dispatch;
- terminal effect claim; or
- BindReceipt / Outcome.

Both the raw reconciliation capability artifact and its verified proof remain
evidence, not authority. The verified proof does not create execution permission,
retry permission, or a terminal external-effect claim.

## 6. Successful result

A successful required gate allows the existing atomic consumption step to
proceed. The returned `NativeAuthorizationConsumptionResult` records:

- policy identifier;
- accepted capability evidence digest;
- accepted verification proof hash;
- whether authoritative reconciliation was required; and
- whether the requirement was satisfied.

These fields are audit context only. They are not reusable execution capability.

## 7. Relationship to EFFECT_UNKNOWN

This profile does not change post-dispatch uncertainty semantics.

If a dispatched action becomes ambiguous:

- `EFFECT_UNKNOWN` remains the unresolved state;
- missing / unavailable lookup evidence does not prove no effect;
- blind redispatch remains prohibited;
- replacement authorization does not bypass an unresolved business event; and
- reconciliation remains read-only and independently verified.

A temporary reconciliation outage after dispatch does not retroactively undo a
previously valid capability assessment.

## 8. Frozen proof relationship

The original Controlled Execution Proof v1 remains unchanged.

This PR adds a **policy-gated execution profile** on top of native v2 consumption.
It does not replace the freeze anchor, widen the original production claim, or
claim that every downstream API is safely reconcilable.

The original controlled proof path can continue with the gate disabled. A later
dedicated reproducible proof may choose to exercise this profile with the gate
required.

## 9. Focused proof

The implementation includes focused tests proving:

1. a verifier-sealed current `AUTHORITATIVE_QUERY` passes when required;
2. a verifier-sealed current `AUTHORITATIVE_EVIDENCE` passes when required;
3. raw evidence alone cannot satisfy the required gate;
4. caller-constructed verified-proof lookalikes fail closed;
5. trust-policy mismatch fails closed;
6. policy-not-required preserves the existing consumption contract;
7. `HEURISTIC_ONLY` and `UNAVAILABLE_OR_UNVERIFIED` fail before consumption;
8. expired evidence fails before consumption;
9. endpoint or target-configuration drift fails before consumption;
10. verifier binding mismatch fails before consumption;
11. evidence digest mismatch fails before consumption;
12. incomplete required policy fails before consumption; and
13. untyped request-like policy input cannot downgrade the typed deployment gate.

## 9.1 Dedicated reproducible proof

A dedicated workflow now exercises this profile separately from the frozen
Controlled Execution Proof v1:

`.github/workflows/reproducible-reconciliation-capable-execution-profile.yml`

Validation contract:

`docs/en/validation/reconciliation-capable-execution-profile-proof-v1.md`

The proof requires a runtime-sealed `AUTHORITATIVE_QUERY` proof before
consumption on the positive normal and lost-response paths, and demonstrates
that missing proof or verifier-sealed `HEURISTIC_ONLY` capability remains
unconsumed with no sandbox event.

The workflow also runs the broader focused negative matrix for expiry,
endpoint/configuration drift, verifier mismatch, evidence-digest mismatch,
incomplete policy, and request-like downgrade attempts.

## 10. Non-claims

This profile does not claim:

- exactly-once external delivery;
- universal reconciliation support;
- production readiness;
- that a transient reconciliation endpoint must be reachable immediately before
  dispatch;
- that capability evidence itself creates authority; or
- that all external effects must use this gate.

## 11. Principle

> **When deployment policy requires authoritative reconciliation, an
> unreconcilable or unverified target is not eligible for authorization
> consumption.**

And after dispatch:

> **If external truth cannot be authoritatively established, uncertainty remains
> explicit and does not become retry permission.**
